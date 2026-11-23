"""生成请求相关模型（multipart 表单由 API 层解析，这里定义结果结构）。"""

from __future__ import annotations

from pydantic import BaseModel

from app.utils.validators import (
    validate_frame_rate,
    validate_frames,
    validate_mode,
    validate_prompt,
    validate_resolution,
    validate_seed,
    validate_task_type,
)


class GenerationParams(BaseModel):
    """已校验的生成参数（不含文件）。"""

    task_type: str
    prompt: str
    width: int
    height: int
    frames: int
    frame_rate: int
    mode: str = "distilled"
    seed: int | None = None

    @classmethod
    def validated(
        cls,
        *,
        task_type: str,
        prompt: str,
        width: int,
        height: int,
        frames: int,
        frame_rate: int,
        mode: str = "distilled",
        seed: int | None = None,
    ) -> "GenerationParams":
        return cls(
            task_type=validate_task_type(task_type),
            prompt=validate_prompt(prompt),
            width=validate_resolution(width, height)[0],
            height=validate_resolution(width, height)[1],
            frames=validate_frames(frames),
            frame_rate=validate_frame_rate(frame_rate),
            mode=validate_mode(mode),
            seed=validate_seed(seed),
        )
