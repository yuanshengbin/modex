"""FastAPI 全局异常处理器注册。

将业务异常、参数校验异常以及未预期异常统一转换为 :class:`ApiResponse` 信封。
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.exceptions import AppException
from app.schemas.common import ApiResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _request_id(request: Request) -> str:
    """从请求上下文中读取中间件注入的 request_id。"""
    return getattr(request.state, "request_id", "")


def register_exception_handlers(app: FastAPI) -> None:
    """向应用注册全部异常处理器。"""

    @app.exception_handler(AppException)
    async def handle_app_exception(
        request: Request, exc: AppException
    ) -> JSONResponse:
        logger.warning(
            "业务异常: %s (code=%s, path=%s)",
            exc.message,
            exc.code,
            request.url.path,
        )
        body = ApiResponse.error(
            code=exc.code,
            message=exc.message,
            request_id=_request_id(request),
            data=exc.details,
        ).model_dump()
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.info("参数校验失败: %s", exc.errors())
        body = ApiResponse.error(
            code=4000,
            message="请求参数校验失败",
            request_id=_request_id(request),
            data=exc.errors(),
        ).model_dump()
        return JSONResponse(status_code=422, content=body)

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("未预期的服务异常: %s", exc)
        body = ApiResponse.error(
            code=5000,
            message="服务内部错误",
            request_id=_request_id(request),
        ).model_dump()
        return JSONResponse(status_code=500, content=body)
