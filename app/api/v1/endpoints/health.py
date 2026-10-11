"""健康检查与服务信息接口。"""
from fastapi import APIRouter, Request

from app.core.registry import adapter_registry
from app.schemas.common import ApiResponse

router = APIRouter(tags=["系统"])


@router.get(
    "/health",
    summary="健康检查",
    response_model=ApiResponse[dict],
)
async def health_check(request: Request) -> ApiResponse[dict]:
    """返回服务存活状态、已注册的模型 mode 与适配器清单。"""
    request_id = getattr(request.state, "request_id", "")
    data = {
        "status": "ok",
        "app": request.app.state.settings.app_name,
        "registered_modes": request.app.state.route_table.list_modes(),
        "registered_adapters": adapter_registry.list_keys(),
    }
    return ApiResponse.ok(data, request_id)
