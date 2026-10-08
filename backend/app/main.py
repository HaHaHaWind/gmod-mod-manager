"""FastAPI 应用入口。

- 统一错误结构:{code, message, request_id, details};绝不泄露堆栈。
- 启动:建表(开发便利;生产用 alembic upgrade head)→ 启动恢复 → 后台 worker。
- 静态:存在 frontend/dist 时托管前端(SPA 回退 index.html)。
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routers import ALL_ROUTERS
from .config import get_settings
from .db import Base, get_engine
from .errors import ApiError

log = logging.getLogger("gmm.main")

_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from . import models  # noqa: F401 注册实体
    from .workers.runner import get_worker, startup_recovery

    settings = get_settings()
    settings.ensure_data_dir()
    Base.metadata.create_all(get_engine())  # 幂等;生产迁移以 alembic 为准
    recovery = startup_recovery(settings)
    if recovery["interrupted_tasks"] or recovery["recovery_plans"]:
        log.warning("存在待恢复内容:%s", recovery)
    worker = get_worker()
    if not worker.is_alive():  # 进程内多次进入 lifespan(测试/重载)不会重复启动
        worker.start()
    try:
        yield
    finally:
        worker.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="GMod Workshop Mod 管理面板", version="1.0.0",
                  lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url="/api/openapi.json")

    if settings.cors_dev_origins:
        origins = [o.strip() for o in settings.cors_dev_origins.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_credentials=True,
            allow_methods=["*"], allow_headers=["*"],
            expose_headers=["x-request-id"])

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status,
            content={"code": exc.code, "message": exc.message,
                     "request_id": getattr(request.state, "request_id", ""),
                     "details": exc.details},
            headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"code": "validation_error", "message": "请求参数不合法",
                     "request_id": getattr(request.state, "request_id", ""),
                     "details": exc.errors()[:20]})

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, exc: Exception):
        log.exception("未处理异常 path=%s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": "服务器内部错误,详情见服务端日志",
                     "request_id": getattr(request.state, "request_id", ""),
                     "details": None})

    for r in ALL_ROUTERS:
        app.include_router(r)

    if _FRONTEND_DIST.is_dir():
        assets = _FRONTEND_DIST / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            if full_path.startswith("api/"):
                from .errors import not_found
                raise not_found()
            candidate = (_FRONTEND_DIST / full_path).resolve()
            if candidate.is_file() and str(candidate).startswith(str(_FRONTEND_DIST)):
                return FileResponse(candidate)
            return FileResponse(_FRONTEND_DIST / "index.html")

    return app


app = create_app()
