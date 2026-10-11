"""对话推理相关的请求 Schema。"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.core.enums import RoleType


class Message(BaseModel):
    """多轮对话中的单条消息。"""

    role: RoleType = Field(..., description="消息角色：system/user/assistant/tool")
    content: str = Field(..., min_length=1, description="消息文本内容")

    def to_upstream(self) -> dict:
        """转换为上游接口所需的字典格式。"""
        return {"role": self.role.value, "content": self.content}


class ChatCompletionRequest(BaseModel):
    """统一对话补全请求。

    ``prompt`` 与 ``messages`` 至少提供一个：
    提供 ``messages`` 时支持多轮对话；仅提供 ``prompt`` 时自动包装为单轮用户消息。
    """

    mode: str = Field(
        ...,
        min_length=1,
        description="模型路由标识，对应路由表(config/routes.json)中的 key",
    )
    prompt: Optional[str] = Field(
        default=None,
        description="单轮提示词，与 messages 二选一或同时提供（messages 优先）",
    )
    messages: Optional[List[Message]] = Field(
        default=None,
        description="多轮对话消息列表，与 prompt 二选一或同时提供（messages 优先）",
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="采样温度，范围 0~2；不传时使用路由配置的模型级默认值",
    )
    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        description="最大生成 token 数；不传时使用上游模型默认值",
    )
    top_p: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="核采样概率阈值，范围 0~1",
    )
    stop: Optional[List[str]] = Field(
        default=None,
        description="停止词列表",
    )
    stream: bool = Field(
        default=False,
        description="是否流式返回（当前版本仅支持非流式）",
    )
    user: Optional[str] = Field(
        default=None,
        description="终端用户标识，用于上游侧的审计与滥用监控",
    )

    @model_validator(mode="after")
    def _validate_content(self) -> "ChatCompletionRequest":
        """确保 prompt 与 messages 至少提供一个。"""
        if not self.prompt and not self.messages:
            raise ValueError("prompt 与 messages 不能同时为空")
        return self

    def normalized_messages(self) -> List[dict]:
        """归一化为上游统一的 messages 结构。"""
        if self.messages:
            return [message.to_upstream() for message in self.messages]
        return [{"role": "user", "content": self.prompt}]
