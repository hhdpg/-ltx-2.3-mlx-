"""CLI 命令构造器：所有参数由后端统一生成，前端无法注入。"""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.db.models import GenerationTask, TaskType

logger = logging.getLogger(__name__)


class CommandBuildError(RuntimeError):
    """无法构造合法命令。"""


def _require(value, name: str):
    if value is None or (isinstance(value, str) and not value.strip()):
        raise CommandBuildError(f"缺少必要配置：{name}")
    return value


def build_command(
    task: GenerationTask,
    settings: Settings,
    *,
    output_path: str,
    model_path: str,
    low_ram: bool | None = None,
) -> list[str]:
    """构造 ltx-2-mlx generate 命令数组。

    约定（与 4.5 / 4.6 一致）：
      * 一律显式传 --distilled（V1 唯一模式）
      * 一律显式传 -f/--frames
      * I2V 追加：--image PATH FRAME STRENGTH MODE
      * 仅当 settings.ltx_low_ram 为真时追加 --low-ram
    不支持的扩展参数一律不拼接，避免静默忽略。
    """
    executable = _require(settings.ltx_executable, "LTX_EXECUTABLE")
    model_path = _require(model_path, "模型本地路径")
    output_path = _require(output_path, "输出路径")

    cmd: list[str] = [
        str(executable),
        "generate",
        "--prompt",
        task.prompt,
        "--distilled",
        "-H",
        str(task.height),
        "-W",
        str(task.width),
        "-f",
        str(task.frames),
        "--frame-rate",
        str(task.frame_rate),
        "--model",
        str(model_path),
        "-o",
        str(output_path),
    ]

    if task.task_type == TaskType.I2V.value:
        image_path = _require(task.image_path, "I2V 输入图片路径")
        cmd.extend(
            [
                "--image",
                str(image_path),
                str(settings.image_frame),
                f"{settings.image_strength:g}",
                settings.image_mode,
            ]
        )

    effective_low_ram = settings.ltx_low_ram if low_ram is None else low_ram
    if effective_low_ram:
        cmd.append("--low-ram")

    # 仅在 CLI 明确支持 --seed 时才传（默认关闭，避免未知参数导致失败）
    if settings.seed_supported and task.seed is not None:
        cmd.extend(["--seed", str(task.seed)])

    logger.info(
        "构造命令 type=%s size=%sx%s frames=%s fps=%s",
        task.task_type,
        task.width,
        task.height,
        task.frames,
        task.frame_rate,
    )
    return cmd


def build_extend_command(
    task: GenerationTask,
    settings: Settings,
    *,
    output_path: str,
    model_path: str,
    low_ram: bool | None = None,
) -> list[str]:
    """构造 ltx-2-mlx extend 命令数组。

    以本机 v0.18.0 `extend --help` 为准：
      * 必须显式传 --model（CLI 默认 Q8，本机使用 Q4）
      * distilled 只支持 --direction after，不传 --direction 即默认 after
      * distilled 拒绝 --steps / --cfg-scale / --stg-scale / --negative-prompt
      * 不传 generate 专属的 -H / -W / -f / --frame-rate
      * --image 的 FRAME_IDX 仅针对新增帧计数
    """
    executable = _require(settings.ltx_executable, "LTX_EXECUTABLE")
    model_path = _require(model_path, "模型本地路径")
    output_path = _require(output_path, "输出路径")
    source_video = _require(task.source_video_path, "源视频路径")
    final_prompt = _require(task.final_prompt, "最终提示词")

    if task.extend_frames is None:
        raise CommandBuildError("缺少必要参数：extend_frames")
    if task.extend_frames not in settings.allowed_extend_frames:
        allowed = "、".join(str(v) for v in settings.allowed_extend_frames)
        raise CommandBuildError(f"续写长度不合法，允许值：{allowed}")

    cmd: list[str] = [
        str(executable),
        "extend",
        "--distilled",
        "--prompt",
        final_prompt,
        "--video",
        str(source_video),
        "--extend-frames",
        str(task.extend_frames),
        "--model",
        str(model_path),
        "-o",
        str(output_path),
    ]

    if settings.seed_supported and task.seed is not None:
        cmd.extend(["--seed", str(task.seed)])

    effective_low_ram = settings.ltx_low_ram if low_ram is None else low_ram
    if effective_low_ram:
        cmd.append("--low-ram")

    if task.anchor_image_path:
        anchor_cmd = [
            "--image",
            str(task.anchor_image_path),
        ]
        if task.anchor_frame is not None or task.anchor_strength is not None:
            frame = task.anchor_frame if task.anchor_frame is not None else 0
            strength = (
                task.anchor_strength
                if task.anchor_strength is not None
                else settings.anchor_default_strength
            )
            anchor_cmd.extend([str(frame), f"{strength:g}"])
        cmd.extend(anchor_cmd)

    logger.info(
        "构造 Extend 命令 source=%s extend_frames=%s anchor=%s",
        source_video,
        task.extend_frames,
        bool(task.anchor_image_path),
    )
    return cmd


def build_retake_command(
    task: GenerationTask,
    settings: Settings,
    *,
    output_path: str,
    model_path: str,
    low_ram: bool | None = None,
) -> list[str]:
    """构造 ltx-2-mlx retake 命令数组（改写已有视频的指定区间）。

    以本机 v0.18.0 `retake --help` 为准：
      * --start / --end 是 latent 帧索引，左闭右开
      * 必须显式传 --model（CLI 默认 Q8，本机是 Q4）
      * distilled 拒绝 --cfg-scale / --stg-scale / --negative-prompt
      * 不传 generate 专属的 -H / -W / -f / --frame-rate
      * 可选 --no-regen-audio 保留原音轨
    """
    executable = _require(settings.ltx_executable, "LTX_EXECUTABLE")
    model_path = _require(model_path, "模型本地路径")
    output_path = _require(output_path, "输出路径")
    source_video = _require(task.source_video_path, "源视频路径")
    final_prompt = _require(task.final_prompt, "最终提示词")

    if task.retake_start is None or task.retake_end is None:
        raise CommandBuildError("缺少必要参数：retake 起止帧")
    if task.retake_end <= task.retake_start:
        raise CommandBuildError("重拍区间的结束帧必须大于开始帧")

    cmd: list[str] = [
        str(executable),
        "retake",
        "--distilled",
        "--prompt",
        final_prompt,
        "--video",
        str(source_video),
        "--start",
        str(task.retake_start),
        "--end",
        str(task.retake_end),
        "--model",
        str(model_path),
        "-o",
        str(output_path),
    ]

    if settings.seed_supported and task.seed is not None:
        cmd.extend(["--seed", str(task.seed)])

    effective_low_ram = settings.ltx_low_ram if low_ram is None else low_ram
    if effective_low_ram:
        cmd.append("--low-ram")

    if task.keep_audio:
        cmd.append("--no-regen-audio")

    logger.info(
        "构造 Retake 命令 source=%s range=[%s, %s) keep_audio=%s",
        source_video,
        task.retake_start,
        task.retake_end,
        bool(task.keep_audio),
    )
    return cmd


def describe_command(cmd: list[str]) -> str:
    """用于日志/详情展示的脱敏命令字符串（保持可读）。"""
    return " ".join(_quote(part) for part in cmd)


def _quote(part: str) -> str:
    if not part:
        return "''"
    if any(ch in part for ch in " \t\"'\\$&|;<>()*?[]{}!#"):
        escaped = part.replace("'", "'\\''")
        return f"'{escaped}'"
    return part
