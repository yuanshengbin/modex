"""Anthropic（Claude）Messages API 适配器。

背景知识（写给初学者）：
Anthropic 公司的 Claude 系列模型使用自己的一套 API 协议（Messages API），
与 OpenAI 的 /chat/completions 协议在请求格式和响应格式上都有差异，
不能直接复用 OpenAICompatibleAdapter 的 build_payload / parse_response。

NoneLinear Router 平台为 Anthropic 模型提供了独立的协议端点：
    https://api.nonelinear.com.cn/anthropic/v1/messages

与 OpenAI 端点的主要差异：
    请求端点：/v1/messages（而非 /chat/completions）
    请求头：需额外附带 anthropic-version 头
    请求体：max_tokens 为必填字段；停止词字段名为 stop_sequences（而非 stop）
    响应体：content 是块数组（每块含 type + text），而非 choices[0].message.content
    响应体：用量字段为 input_tokens / output_tokens（无 total_tokens）

本适配器继承 OpenAICompatibleAdapter，仅复用其 HTTP 发送 + 错误处理管线
（chat / _raise_upstream_error / _extract_error_body），协议相关的三个方法
（build_headers / build_payload / parse_response）和端点路径全部重写。
"""
from typing import Any, Dict

from app.adapters.openai_compatible import OpenAICompatibleAdapter
from app.core.enums import ProviderType
from app.core.registry import adapter_registry


@adapter_registry.register(ProviderType.OVERSEAS, "anthropic")
class AnthropicAdapter(OpenAICompatibleAdapter):
    """Anthropic Messages API 适配器（经 NoneLinear Router 代理）。

    继承自 OpenAICompatibleAdapter 仅为复用 HTTP 发送和错误处理逻辑，
    协议相关的 build_headers / build_payload / parse_response 全部重写。
    """

    provider = ProviderType.OVERSEAS
    vendor = "anthropic"

    #: NoneLinear 平台 Anthropic 协议端点的基础地址
    default_base_url = "https://api.nonelinear.com.cn/anthropic"

    #: Anthropic Messages API 路径，与 base_url 拼接后为完整请求地址
    chat_path = "/v1/messages"

    #: Anthropic API 协议版本号（Anthropic 要求请求头中携带此值）
    anthropic_version = "2023-06-01"

    #: max_tokens 在 Anthropic 协议中是必填字段，请求未指定时用此值兜底
    _DEFAULT_MAX_TOKENS = 4096

    def build_headers(self) -> Dict[str, str]:
        """构造请求头：在 Bearer 鉴权基础上追加 anthropic-version。"""
        headers = super().build_headers()
        headers["anthropic-version"] = self.anthropic_version
        return headers

    def build_payload(self, params: Any) -> Dict[str, Any]:
        """构造 Anthropic Messages API 请求体。

        与 OpenAI 协议的差异：
        - max_tokens 必填：无值时用 _DEFAULT_MAX_TOKENS 兜底；
        - 停止词字段名为 stop_sequences（而非 stop）；
        - 不传 user（Anthropic 用 metadata.user_id，当前暂不支持）。
        """
        payload: Dict[str, Any] = {
            "model": params.model,
            "messages": params.messages,
            "max_tokens": (
                params.max_tokens
                if params.max_tokens is not None
                else self._DEFAULT_MAX_TOKENS
            ),
        }
        if params.temperature is not None:
            payload["temperature"] = params.temperature
        if params.top_p is not None:
            payload["top_p"] = params.top_p
        if params.stop is not None:
            payload["stop_sequences"] = params.stop
        return payload

    def parse_response(self, data: Dict[str, Any]) -> Any:
        """将 Anthropic 响应解析为标准化 ModelOutput。

        Anthropic 响应结构示例::

            {
              "id": "msg_xxx",
              "model": "claude-3.5-sonnet",
              "content": [
                {"type": "text", "text": "你好，我是 Claude"}
              ],
              "stop_reason": "end_turn",
              "usage": {"input_tokens": 10, "output_tokens": 5}
            }

        与 OpenAI 的关键差异：
        - content 是块数组，每块有 type + text，需按顺序拼接文本块；
        - stop_reason 对应 finish_reason（值如 end_turn / max_tokens / stop_sequence）；
        - usage 无 total_tokens，需由 input + output 自行计算。
        """
        from app.adapters.base import ModelOutput

        content_blocks = data.get("content") or []
        text_parts = [
            block.get("text", "")
            for block in content_blocks
            if block.get("type") == "text"
        ]
        content = "".join(text_parts)

        usage = data.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))

        return ModelOutput(
            id=str(data.get("id", "")),
            model=str(data.get("model", "")),
            content=content,
            finish_reason=data.get("stop_reason"),
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            raw=data,
        )
