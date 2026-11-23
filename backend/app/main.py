"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    files,
    generation,
    health,
    projects,
    retake,
    settings as settings_api,
    tasks,
)
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.paths import ensure_directories
from app.db.database import init_db
from app.services.task_queue import queue_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    ensure_directories()
    init_db()
    logger.info("=" * 60)
    logger.info("%s 启动中", settings.app_name)
    logger.info("项目根目录：%s", settings.root)
    logger.info("输出目录：%s", settings.outputs)
    logger.info("离线模式：%s", settings.hf_hub_offline)
    logger.info("=" * 60)

    await queue_manager.start()
    try:
        yield
    finally:
        await queue_manager.stop()
        logger.info("%s 已停止", settings.app_name)


app = FastAPI(
    title="LTX Local Studio API",
    version="1.0.0",
    description="LTX-2.3 本地视频生成工作台后端",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Content-Length", "Accept-Ranges"],
)

app.include_router(health.router, prefix="/api")
app.include_router(generation.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(retake.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    messages = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", []) if part != "body")
        messages.append(f"{location}: {error.get('msg', '参数错误')}")
    return JSONResponse(
        status_code=422,
        content={"detail": "；".join(messages) or "请求参数无效"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "服务内部错误，请查看日志"})


# ---- 可选：静态托管前端构建产物（单入口模式）----
_FRONTEND_DIST = settings.root / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():

    class SpaStaticFiles(StaticFiles):
        """静态资源优先，未命中的非 /api 路径回退到 index.html（前端路由）。"""

        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except Exception as exc:
                from starlette.exceptions import HTTPException as StarletteHTTPException

                if (
                    isinstance(exc, StarletteHTTPException)
                    and exc.status_code == 404
                    and "." not in Path(path).name
                ):
                    return await super().get_response("index.html", scope)
                raise

    app.mount(
        "/", SpaStaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend"
    )
    logger.info("已挂载前端静态资源：%s", _FRONTEND_DIST)
