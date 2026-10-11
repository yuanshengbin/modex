"""FastAPI 应用入口。

启动方式::

    python run.py
    # 或
    uvicorn app.main:app --reload
"""
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import RouteTable, get_settings
from app.exceptions.handlers import register_exception_handlers
from app.services.inference_service import InferenceService
from app.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)

# 模块级加载一次配置（环境变量 / .env）
settings = get_settings()
setup_logging("DEBUG" if settings.debug else "INFO")


@asynccontextmanager
async def lifespan(app: FastAPI) -> None:
    """应用生命周期：启动时加载路由表并装配服务，关闭时释放资源。"""
    route_table = RouteTable()
    route_table.load(settings.resolve_routes_path())

    app.state.settings = settings
    app.state.route_table = route_table
    app.state.inference_service = InferenceService(settings, route_table)

    logger.info(
        "应用启动完成：加载 %d 条模型路由 -> %s",
        len(route_table),
        ", ".join(route_table.list_modes()),
    )
    yield
    logger.info("应用正在关闭")


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "统一 AI 后端支持服务：按 mode 路由至国内厂商（独立 Key）、"
        "国外厂商（第三方 Router 全局 Key）或本地私有化模型。"
    ),
    lifespan=lifespan,
)

# CORS 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局异常处理
register_exception_handlers(app)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """为每个请求注入/透传 request_id，并回写到响应头。"""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# 业务路由
app.include_router(api_router)
