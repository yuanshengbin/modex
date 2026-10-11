"""统一响应封装与推理结果数据模型。"""
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

from app.schemas.chat import Message

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应信封。

    成功::

        {"code": 0, "message": "success", "data": {...}, "request_id": "..."}

    失败::

        {"code": 4040, "message": "...", "data": null, "request_id": "..."}
    """

    code: int = Field(default=0, description="业务状态码，0 表示成功")
    message: str = Field(default="success", description="状态描述")
    data: Optional[T] = Field(default=None, description="业务数据")
    request_id: str = Field(default="", description="请求追踪 ID")

    @classmethod
    def ok(cls, data: T, request_id: str = "") -> "ApiResponse[T]":
        """构造成功响应。"""
        return cls(code=0, message="success", data=data, request_id=request_id)

    @classmethod
    def error(
        cls,
        code: int,
        message: str,
        request_id: str = "",
        data: Any = None,
    ) -> "ApiResponse[Any]":
        """构造错误响应。"""
        return cls(code=code, message=message, data=data, request_id=request_id)


class UsageInfo(BaseModel):
    """Token 用量信息。"""

    prompt_tokens: int = Field(default=0, description="输入 token 数")
    completion_tokens: int = Field(default=0, description="生成 token 数")
    total_tokens: int = Field(default=0, description="总 token 数")


class Choice(BaseModel):
    """单条候选结果。"""

    index: int = Field(default=0, description="候选序号")
    message: Message = Field(..., description="生成的消息")
    finish_reason: Optional[str] = Field(
        default=None,
        description="结束原因，如 stop/length/tool_calls",
    )


class ChatCompletionData(BaseModel):
    """对话补全业务数据（与主流 OpenAI 风格保持一致）。"""

    id: str = Field(..., description="本次推理的唯一 ID")
    mode: str = Field(..., description="请求传入的路由模式")
    model: str = Field(..., description="实际使用的上游模型名")
    choices: List[Choice] = Field(default_factory=list, description="候选结果列表")
    usage: UsageInfo = Field(default_factory=UsageInfo, description="Token 用量")
    created: int = Field(..., description="创建时间（Unix 时间戳）")
