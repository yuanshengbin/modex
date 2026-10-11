"""模型推理接口。"""
from fastapi import APIRouter, Depends, Request

from app.api.deps import get_inference_service
from app.schemas.chat import ChatCompletionRequest
from app.schemas.common import ApiResponse, ChatCompletionData
from app.services.inference_service import InferenceService

router = APIRouter(prefix="/chat", tags=["模型推理"])


@router.post(
    "/completions",
    summary="统一对话补全（按 mode 路由到对应大模型）",
    response_model=ApiResponse[ChatCompletionData],
)
async def create_chat_completion(
    body: ChatCompletionRequest,
    request: Request,
    service: InferenceService = Depends(get_inference_service),
) -> ApiResponse[ChatCompletionData]:
    """接收前端推理参数，按 ``mode`` 路由至国内 / 国外 / 本地模型并返回结果。"""
    request_id = getattr(request.state, "request_id", "")
    data = await service.chat(body)
    return ApiResponse.ok(data, request_id)
