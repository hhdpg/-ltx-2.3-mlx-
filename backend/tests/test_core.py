"""后端测试：参数校验、命令构造、路径安全、上传校验、队列状态流转。"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import Settings, settings
from app.core.paths import UnsafePathError, safe_join
from app.db.models import GenerationTask
from app.services import file_service
from app.utils import validators
from app.utils.command_builder import build_command, describe_command
from app.utils.validators import ValidationError


# ---------- 帧数 8k+1 ----------
@pytest.mark.parametrize("frames", [9, 25, 41, 49, 65, 81, 97, 121])
def test_valid_frame_counts(frames: int) -> None:
    assert validators.is_valid_frame_count(frames)
    assert validators.validate_frames(frames) == frames


@pytest.mark.parametrize("frames", [0, 8, 24, 26, 100, 122])
def test_invalid_frame_counts(frames: int) -> None:
    assert not validators.is_valid_frame_count(frames)
    with pytest.raises(ValidationError):
        validators.validate_frames(frames)


def test_frame_193_matches_rule_but_not_v1_whitelist() -> None:
    """193 = 8*24+1 符合数学规则，但 V1 白名单不开放。"""
    assert validators.is_valid_frame_count(193)
    with pytest.raises(ValidationError):
        validators.validate_frames(193)


def test_frame_count_rule_math() -> None:
    for k in range(0, 30):
        assert validators.is_valid_frame_count(8 * k + 1)


# ---------- 提示词 ----------
def test_prompt_trim_and_limit() -> None:
    assert validators.validate_prompt("  hello  ") == "hello"
    with pytest.raises(ValidationError):
        validators.validate_prompt("   ")
    with pytest.raises(ValidationError):
        validators.validate_prompt("x" * (settings.max_prompt_length + 1))
    assert len(validators.validate_prompt("x" * settings.max_prompt_length)) == (
        settings.max_prompt_length
    )


# ---------- 分辨率 / 帧率 / 模式 ----------
def test_resolution_whitelist() -> None:
    assert validators.validate_resolution(512, 320) == (512, 320)
    with pytest.raises(ValidationError):
        validators.validate_resolution(1024, 1024)


def test_frame_rate_whitelist() -> None:
    assert validators.validate_frame_rate(24) == 24
    with pytest.raises(ValidationError):
        validators.validate_frame_rate(30)


def test_mode_and_task_type() -> None:
    assert validators.validate_mode("Distilled") == "distilled"
    with pytest.raises(ValidationError):
        validators.validate_mode("two-stage")
    assert validators.validate_task_type("i2v") == "I2V"
    with pytest.raises(ValidationError):
        validators.validate_task_type("A2V")


def test_seed_bounds() -> None:
    assert validators.validate_seed(None) is None
    assert validators.validate_seed(0) == 0
    assert validators.validate_seed(12345) == 12345
    with pytest.raises(ValidationError):
        validators.validate_seed(-5)
    with pytest.raises(ValidationError):
        validators.validate_seed(2**63)


# ---------- 命令构造 ----------
def _make_task(task_type: str = "T2V", image_path: str | None = None) -> GenerationTask:
    return GenerationTask(
        id=str(uuid.uuid4()),
        task_type=task_type,
        prompt="a cinematic sunset",
        image_path=image_path,
        model_path="/models/ltx",
        mode="distilled",
        width=512,
        height=320,
        frames=25,
        frame_rate=24,
        status="QUEUED",
    )


@pytest.fixture()
def cli_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """为命令构造测试提供一个假的 CLI 路径。"""
    fake = Settings(
        ltx_executable="/opt/fake/ltx-2-mlx",
        ltx_project_root="/opt/fake/ltx-2-mlx",
    )
    return fake


def test_build_command_t2v(cli_settings: Settings) -> None:
    task = _make_task()
    cmd = build_command(
        task,
        cli_settings,
        output_path="/out/a.mp4",
        model_path="/models/ltx",
        low_ram=False,
    )
    assert cmd[0] == "/opt/fake/ltx-2-mlx"
    assert cmd[1] == "generate"
    assert "--distilled" in cmd
    assert cmd[cmd.index("-H") + 1] == "320"
    assert cmd[cmd.index("-W") + 1] == "512"
    assert cmd[cmd.index("-f") + 1] == "25"
    assert cmd[cmd.index("--frame-rate") + 1] == "24"
    assert cmd[cmd.index("--model") + 1] == "/models/ltx"
    assert cmd[cmd.index("-o") + 1] == "/out/a.mp4"
    assert "--image" not in cmd
    assert "--low-ram" not in cmd


def test_build_command_i2v_includes_image_args(cli_settings: Settings) -> None:
    task = _make_task("I2V", image_path="/uploads/abc.png")
    cmd = build_command(
        task,
        cli_settings,
        output_path="/out/a.mp4",
        model_path="/models/ltx",
        low_ram=False,
    )
    idx = cmd.index("--image")
    assert cmd[idx + 1] == "/uploads/abc.png"
    assert cmd[idx + 2] == str(cli_settings.image_frame)
    assert cmd[idx + 3] == f"{cli_settings.image_strength:g}"
    assert cmd[idx + 4] == cli_settings.image_mode


def test_build_command_low_ram_toggle(cli_settings: Settings) -> None:
    task = _make_task()
    cmd = build_command(
        task, cli_settings, output_path="/out/a.mp4", model_path="/m", low_ram=True
    )
    assert "--low-ram" in cmd


def test_build_command_requires_executable() -> None:
    bare = Settings(ltx_executable=None)
    task = _make_task()
    with pytest.raises(Exception):
        build_command(task, bare, output_path="/out/a.mp4", model_path="/m")


def test_build_command_seed_only_when_supported(cli_settings: Settings) -> None:
    task = _make_task()
    task.seed = 42
    no_seed = build_command(
        task,
        cli_settings.model_copy(update={"seed_supported": False}),
        output_path="/o.mp4",
        model_path="/m",
        low_ram=False,
    )
    assert "--seed" not in no_seed
    with_seed = build_command(
        task,
        cli_settings.model_copy(update={"seed_supported": True}),
        output_path="/o.mp4",
        model_path="/m",
        low_ram=False,
    )
    assert with_seed[with_seed.index("--seed") + 1] == "42"


def test_command_never_uses_shell_metacharacters_as_single_string(
    cli_settings: Settings,
) -> None:
    task = _make_task()
    task.prompt = "hello; rm -rf /"
    cmd = build_command(
        task, cli_settings, output_path="/out/a.mp4", model_path="/m", low_ram=False
    )
    # prompt 必须作为一个独立数组元素，而不是被拼接
    assert "hello; rm -rf /" in cmd
    assert cmd[cmd.index("--prompt") + 1] == "hello; rm -rf /"
    assert cmd[1] == "generate"


def test_describe_command_quotes_spaces() -> None:
    text = describe_command(["cli", "generate", "--prompt", "a b c"])
    assert "'a b c'" in text


# ---------- 路径安全 ----------
def test_safe_join_blocks_traversal(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError):
        safe_join(tmp_path, "../etc/passwd")
    with pytest.raises(UnsafePathError):
        safe_join(tmp_path, "/etc/passwd")
    assert safe_join(tmp_path, "ok.png").name == "ok.png"


# ---------- 上传校验 ----------
def _png_bytes(size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (20, 30, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_upload_accepts_png() -> None:
    stored = file_service.save_upload(_png_bytes(), "photo.png")
    assert stored.path.exists()
    assert stored.width == 64 and stored.height == 48
    assert stored.path.suffix == ".png"
    stored.path.unlink(missing_ok=True)


def test_upload_rejects_fake_image() -> None:
    with pytest.raises(file_service.UploadError):
        file_service.save_upload(b"<html><script>alert(1)</script>", "evil.png")


def test_upload_rejects_svg() -> None:
    with pytest.raises(file_service.UploadError):
        file_service.save_upload(b"<svg></svg>", "evil.svg")


def test_upload_rejects_oversized() -> None:
    payload = b"\x89PNG\r\n\x1a\n" + b"0" * (settings.max_upload_mb * 1024 * 1024 + 10)
    with pytest.raises(file_service.UploadError) as exc:
        file_service.save_upload(payload, "big.png")
    assert exc.value.error_code == "file_too_large"


def test_upload_uses_uuid_name() -> None:
    stored = file_service.save_upload(_png_bytes(), "my vacation photo.png")
    assert "my vacation photo" not in stored.path.name
    assert len(stored.path.stem) == 32
    stored.path.unlink(missing_ok=True)


# ---------- 输出文件检查 ----------
def test_output_ready_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "output_dir", tmp_path)
    assert file_service.output_ready(None)[0] is False
    missing = tmp_path / "none.mp4"
    assert file_service.output_ready(str(missing))[0] is False
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    assert file_service.output_ready(str(empty))[0] is False
    good = tmp_path / "good.mp4"
    good.write_bytes(b"fake video bytes")
    ok, err = file_service.output_ready(str(good))
    assert ok and err is None
    outside = Path("/tmp/outside.mp4")
    outside.write_bytes(b"x")
    assert file_service.output_ready(str(outside))[0] is False
    outside.unlink(missing_ok=True)


def test_tail_lines(tmp_path: Path) -> None:
    log = tmp_path / "t.log"
    log.write_text("\n".join(f"line{i}" for i in range(1, 101)), encoding="utf-8")
    tail = file_service.tail_lines(log, limit=5)
    assert tail == ["line96", "line97", "line98", "line99", "line100"]


# ---------- 设置校验 ----------
def test_settings_rejects_bad_mode() -> None:
    with pytest.raises(Exception):
        Settings(ltx_mode="two-stage")
