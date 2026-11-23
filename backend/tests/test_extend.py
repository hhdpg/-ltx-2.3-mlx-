"""V1.1 连续续写测试：Prompt 组合、extend 命令构造、视频校验、版本链。"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings
from app.db.models import GenerationProject, GenerationTask, TaskType
from app.services import project_service, video_service
from app.services.video_service import VideoError
from app.utils.command_builder import CommandBuildError, build_extend_command


# ---------- Prompt 组合 ----------
def _project(**kwargs) -> GenerationProject:
    base = dict(
        id=str(uuid.uuid4()),
        name="test",
        character_setting=None,
        scene_setting=None,
        style_setting=None,
        continuity_rules=None,
        story_summary=None,
        append_project_prompt=True,
    )
    base.update(kwargs)
    return GenerationProject(**base)


def test_compose_prompt_without_project_settings() -> None:
    project = _project()
    assert (
        project_service.compose_final_prompt("人物向前走", project, True)
        == "人物向前走"
    )


def test_compose_prompt_ignores_append_flag() -> None:
    project = _project(character_setting="成年男性")
    result = project_service.compose_final_prompt("人物向前走", project, False)
    assert result == "人物向前走"


def test_compose_prompt_sections() -> None:
    project = _project(
        character_setting="成年男性",
        scene_setting="日落海边",
        style_setting="写实电影",
        continuity_rules="保持服装一致",
    )
    result = project_service.compose_final_prompt("人物向前走", project, True)
    assert result.startswith("Project continuity:")
    assert "Characters: 成年男性" in result
    assert "Setting: 日落海边" in result
    assert "Visual style: 写实电影" in result
    assert "Continuity requirements: 保持服装一致" in result
    assert result.rstrip().endswith("Next action:\n人物向前走")


def test_compose_prompt_skips_empty_sections() -> None:
    project = _project(character_setting="成年男性")
    result = project_service.compose_final_prompt("人物向前走", project, True)
    assert "Setting:" not in result
    assert "Visual style:" not in result


def test_compose_prompt_excludes_story_summary() -> None:
    """剧情摘要不是视觉条件，不得进入最终 Prompt。"""
    project = _project(story_summary="前情提要：他刚失恋")
    result = project_service.compose_final_prompt("人物向前走", project, True)
    assert "失恋" not in result


def test_compose_prompt_rejects_empty_action() -> None:
    with pytest.raises(project_service.ProjectError):
        project_service.compose_final_prompt("   ", _project(), True)


# ---------- extend 命令构造 ----------
def _extend_task(**kwargs) -> GenerationTask:
    base = dict(
        id=str(uuid.uuid4()),
        task_type=TaskType.EXTEND.value,
        prompt="人物向前走",
        final_prompt="人物向前走",
        image_path=None,
        model_path="/models/q4",
        mode="distilled",
        width=512,
        height=320,
        frames=33,
        frame_rate=24,
        status="QUEUED",
        source_video_path="/outputs/src.mp4",
        extend_frames=1,
    )
    base.update(kwargs)
    return GenerationTask(**base)


@pytest.fixture()
def extend_settings() -> Settings:
    return Settings(ltx_executable="/opt/fake/ltx-2-mlx")


def test_build_extend_command_basics(extend_settings: Settings) -> None:
    task = _extend_task()
    cmd = build_extend_command(
        task,
        extend_settings,
        output_path="/out/new.mp4",
        model_path="/models/q4",
        low_ram=False,
    )
    assert cmd[0] == "/opt/fake/ltx-2-mlx"
    assert cmd[1] == "extend"
    assert "--distilled" in cmd
    assert cmd[cmd.index("--prompt") + 1] == "人物向前走"
    assert cmd[cmd.index("--video") + 1] == "/outputs/src.mp4"
    assert cmd[cmd.index("--extend-frames") + 1] == "1"
    assert cmd[cmd.index("--model") + 1] == "/models/q4"
    assert cmd[cmd.index("-o") + 1] == "/out/new.mp4"


def test_build_extend_command_never_has_generate_flags(
    extend_settings: Settings,
) -> None:
    """distilled extend 不接受 -H/-W/-f/--frame-rate 与 CFG 参数。"""
    task = _extend_task()
    cmd = build_extend_command(
        task, extend_settings, output_path="/o.mp4", model_path="/m", low_ram=False
    )
    for forbidden in (
        "-H",
        "--height",
        "-W",
        "--width",
        "-f",
        "--frames",
        "--frame-rate",
        "--steps",
        "--cfg-scale",
        "--stg-scale",
        "--negative-prompt",
        "--direction",
    ):
        assert forbidden not in cmd, f"{forbidden} 不应出现在 distilled extend 命令中"


def test_build_extend_command_low_ram_toggle(extend_settings: Settings) -> None:
    task = _extend_task()
    on = build_extend_command(
        task, extend_settings, output_path="/o.mp4", model_path="/m", low_ram=True
    )
    assert "--low-ram" in on
    off = build_extend_command(
        task, extend_settings, output_path="/o.mp4", model_path="/m", low_ram=False
    )
    assert "--low-ram" not in off


def test_build_extend_command_seed(extend_settings: Settings) -> None:
    task = _extend_task(seed=777)
    cmd = build_extend_command(
        task, extend_settings, output_path="/o.mp4", model_path="/m", low_ram=False
    )
    assert cmd[cmd.index("--seed") + 1] == "777"


def test_build_extend_command_rejects_bad_extend_frames(
    extend_settings: Settings,
) -> None:
    task = _extend_task(extend_frames=3)  # 不在白名单 1/2/4
    with pytest.raises(CommandBuildError):
        build_extend_command(
            task, extend_settings, output_path="/o.mp4", model_path="/m"
        )


def test_build_extend_command_requires_source_video(
    extend_settings: Settings,
) -> None:
    task = _extend_task(source_video_path=None)
    with pytest.raises(CommandBuildError):
        build_extend_command(
            task, extend_settings, output_path="/o.mp4", model_path="/m"
        )


def test_build_extend_command_anchor(extend_settings: Settings) -> None:
    task = _extend_task(anchor_image_path="/anchors/a.png", anchor_frame=0)
    cmd = build_extend_command(
        task, extend_settings, output_path="/o.mp4", model_path="/m", low_ram=False
    )
    idx = cmd.index("--image")
    assert cmd[idx + 1] == "/anchors/a.png"
    assert cmd[idx + 2] == "0"


def test_build_extend_command_prompt_as_single_arg(
    extend_settings: Settings,
) -> None:
    """含 shell 元字符的 Prompt 必须是单个数组元素。"""
    task = _extend_task(final_prompt="动作；rm -rf / && echo hi")
    cmd = build_extend_command(
        task, extend_settings, output_path="/o.mp4", model_path="/m", low_ram=False
    )
    assert cmd[cmd.index("--prompt") + 1] == "动作；rm -rf / && echo hi"


# ---------- 参数与视频校验 ----------
def test_validate_extend_frames_whitelist() -> None:
    for value in (1, 2, 4, 8, 12):
        assert video_service.validate_extend_frames(value) == value
    for value in (0, 3, 5, 6, 16, 24):
        with pytest.raises(VideoError):
            video_service.validate_extend_frames(value)


def test_probe_rejects_missing_file(tmp_path) -> None:
    with pytest.raises(VideoError) as exc:
        video_service.probe_video(tmp_path / "nope.mp4")
    assert exc.value.code == "video_missing"


def test_probe_rejects_empty_file(tmp_path) -> None:
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(VideoError) as exc:
        video_service.probe_video(empty)
    assert exc.value.code == "video_empty"


def test_probe_rejects_non_video(tmp_path) -> None:
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"not a video at all")
    with pytest.raises(VideoError):
        video_service.probe_video(fake)


def test_estimate_added_frames_and_seconds() -> None:
    info = video_service.VideoInfo(
        path=__import__("pathlib").Path("/tmp/x.mp4"),
        width=512,
        height=320,
        frame_rate=24.0,
        duration=1.04,
        frame_count=25,
        has_audio=True,
    )
    est = video_service.estimate_added(info, 1)
    assert est["added_frames"] == 8
    assert est["added_seconds"] == pytest.approx(0.333, abs=0.001)
    assert est["total_frames"] == 33

    est4 = video_service.estimate_added(info, 4)
    assert est4["added_frames"] == 32
    assert est4["added_seconds"] == pytest.approx(1.333, abs=0.001)


def test_estimate_uses_source_fps() -> None:
    """时长必须按源视频真实 FPS 计算，不能写死 24。"""
    info = video_service.VideoInfo(
        path=__import__("pathlib").Path("/tmp/x.mp4"),
        width=512,
        height=320,
        frame_rate=30.0,
        duration=1.0,
        frame_count=30,
        has_audio=False,
    )
    est = video_service.estimate_added(info, 4)
    assert est["added_seconds"] == pytest.approx(32 / 30, abs=0.001)


def test_size_multiple_validation() -> None:
    ok = video_service.VideoInfo(
        path=__import__("pathlib").Path("/tmp/x.mp4"),
        width=512,
        height=320,
        frame_rate=24.0,
        duration=1.0,
        frame_count=25,
        has_audio=True,
    )
    assert ok.size_ok is True
    bad = video_service.VideoInfo(
        path=__import__("pathlib").Path("/tmp/x.mp4"),
        width=510,
        height=320,
        frame_rate=24.0,
        duration=1.0,
        frame_count=25,
        has_audio=True,
    )
    assert bad.size_ok is False


# ---------- 版本链 ----------
def test_segment_lineage_children_map() -> None:
    from app.db.models import GenerationSegment

    def seg(seg_id: str, parent: str | None, index: int) -> GenerationSegment:
        return GenerationSegment(
            id=seg_id,
            project_id="p",
            task_id="t" + seg_id,
            parent_segment_id=parent,
            segment_index=index,
            video_path="/o.mp4",
            prompt="x",
            task_type="EXTEND",
        )

    segments = [seg("a", None, 1), seg("b", "a", 2), seg("c", "a", 3), seg("d", "b", 4)]
    children = project_service.segment_lineage(segments)
    assert children["a"] == ["b", "c"]
    assert children["b"] == ["d"]
    assert children["c"] == []
    assert children["d"] == []


# ---------- 局部重拍（Retake）----------
from app.utils.command_builder import build_retake_command  # noqa: E402


def _retake_task(**kwargs) -> GenerationTask:
    base = dict(
        id=str(uuid.uuid4()),
        task_type=TaskType.RETAKE.value,
        prompt="改成下雨",
        final_prompt="改成下雨",
        image_path=None,
        model_path="/models/q4",
        mode="distilled",
        width=512,
        height=320,
        frames=25,
        frame_rate=24,
        status="QUEUED",
        source_video_path="/outputs/src.mp4",
        retake_start=0,
        retake_end=2,
    )
    base.update(kwargs)
    return GenerationTask(**base)


def test_build_retake_command_basics(extend_settings: Settings) -> None:
    task = _retake_task()
    cmd = build_retake_command(
        task, extend_settings, output_path="/out/new.mp4", model_path="/m", low_ram=False
    )
    assert cmd[1] == "retake"
    assert "--distilled" in cmd
    assert cmd[cmd.index("--start") + 1] == "0"
    assert cmd[cmd.index("--end") + 1] == "2"
    assert cmd[cmd.index("--video") + 1] == "/outputs/src.mp4"
    assert cmd[cmd.index("-o") + 1] == "/out/new.mp4"


def test_build_retake_command_forbidden_flags(extend_settings: Settings) -> None:
    task = _retake_task()
    cmd = build_retake_command(
        task, extend_settings, output_path="/o.mp4", model_path="/m", low_ram=False
    )
    for forbidden in (
        "-H", "--height", "-W", "--width", "-f", "--frames",
        "--frame-rate", "--steps", "--cfg-scale", "--stg-scale",
        "--negative-prompt", "--extend-frames",
    ):
        assert forbidden not in cmd


def test_build_retake_command_keep_audio(extend_settings: Settings) -> None:
    task = _retake_task(keep_audio=True)
    cmd = build_retake_command(
        task, extend_settings, output_path="/o.mp4", model_path="/m", low_ram=False
    )
    assert "--no-regen-audio" in cmd


def test_build_retake_command_rejects_bad_range(extend_settings: Settings) -> None:
    for start, end in ((2, 2), (3, 1), (5, 2)):
        task = _retake_task(retake_start=start, retake_end=end)
        with pytest.raises(CommandBuildError):
            build_retake_command(
                task, extend_settings, output_path="/o.mp4", model_path="/m"
            )


def test_build_retake_command_requires_source(extend_settings: Settings) -> None:
    task = _retake_task(source_video_path=None)
    with pytest.raises(CommandBuildError):
        build_retake_command(
            task, extend_settings, output_path="/o.mp4", model_path="/m"
        )


def test_latent_frame_conversion() -> None:
    assert video_service.frames_to_latent(25) == 4
    assert video_service.frames_to_latent(33) == 5
    assert video_service.frames_to_latent(121) == 16
    assert video_service.latent_to_frames(4) == 25
    assert video_service.latent_to_frames(16) == 121
    assert video_service.frames_to_latent(0) == 0


def test_latent_window_to_seconds() -> None:
    start, end = video_service.latent_window_to_seconds(0, 2, 24)
    assert start == 0.0
    assert end == pytest.approx(0.667, abs=0.001)
    start, end = video_service.latent_window_to_seconds(1, 3, 24)
    assert start == pytest.approx(0.333, abs=0.001)
    assert end == pytest.approx(1.0, abs=0.001)


def test_validate_retake_range() -> None:
    from pathlib import Path

    info = video_service.VideoInfo(
        path=Path("/tmp/x.mp4"), width=512, height=320,
        frame_rate=24.0, duration=1.04, frame_count=25, has_audio=True,
    )
    assert video_service.validate_retake_range(info, 0, 4) == (0, 4)
    with pytest.raises(VideoError):
        video_service.validate_retake_range(info, 0, 5)   # 超出 total_latent=4
    with pytest.raises(VideoError):
        video_service.validate_retake_range(info, 2, 2)   # 空区间
    with pytest.raises(VideoError):
        video_service.validate_retake_range(info, -1, 2)  # 负数


def test_retake_preview_payload() -> None:
    from pathlib import Path

    info = video_service.VideoInfo(
        path=Path("/tmp/x.mp4"), width=512, height=320,
        frame_rate=24.0, duration=1.041667, frame_count=25, has_audio=True,
    )
    payload = video_service.retake_preview(info, 0, 2)
    assert payload["total_latent"] == 4
    assert payload["start_frame"] == 0
    assert payload["end_frame"] == 16
    assert payload["duration_seconds"] == pytest.approx(0.667, abs=0.001)
