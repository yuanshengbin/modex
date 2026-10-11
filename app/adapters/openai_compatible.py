"""OpenAI Chat Completions 协议通用适配基类。

DeepSeek、Moonshot、通义千问兼容模式、智谱 GLM、OpenRouter、Ollama、vLLM
等均提供 OpenAI 兼容接口，公共的请求构造 / 发送 / 响应解析逻辑收敛于此，
具体厂商只需声明地址、鉴权方式等差异点。

若后续接入使用非 OpenAI 私有协议的厂商（如百度文心的 OAuth 协议），
直接继承 :class:`BaseAdapter` 并实现 ``chat`` 即可，无需改动本类与服务层。
"""
from typing import Any, Dict, Optional

import httpx

from app.adapters.base import BaseAdapter, GenerationParams, ModelOutput
from app.exceptions import (
    UpstreamAPIError,
    UpstreamAuthenticationError,
    UpstreamUnavailableError,
)


class OpenAICompatibleAdapter(BaseAdapter):
    """``/chat/completions`` 协议适配器通用实现。"""

    #: 对话补全接口路径
    chat_path: str = "/chat/completions"

    def build_headers(self) -> Dict[str, str]:
        """构造请求头，默认使用 Bearer Token 鉴权。"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def build_payload(self, params: GenerationParams) -> Dict[str, Any]:
        """构造请求体。

        入参在服务层已按「显式请求参数 > 模型级默认值」合并完成，
        此处仅做一次性写入，避免默认值覆盖顺序错误。
        """
        payload: Dict[str, Any] = {
            "model": params.model,
            "messages": params.messages,
        }
        if params.temperature is not None:
            payload["temperature"] = params.temperature
        if params.max_tokens is not None:
            payload["max_tokens"] = params.max_tokens
        if params.top_p is not None:
            payload["top_p"] = params.top_p
        if params.stop is not None:
            payload["stop"] = params.stop
        if params.user is not None:
            payload["user"] = params.user
        return payload

    def parse_response(self, data: Dict[str, Any]) -> ModelOutput:
        """将上游响应解析为标准化 :class:`ModelOutput`。"""
        choices = data.get("choices") or []
        if not choices:
            raise UpstreamAPIError(
                "上游响应中缺少 choices 字段",
                details={"upstream_response": data},
            )

        first_choice = choices[0]
        message = first_choice.get("message") or {}
        usage = data.get("usage") or {}

        return ModelOutput(
            id=str(data.get("id", "")),
            model=str(data.get("model", "")),
            content=message.get("content", "") or "",
            finish_reason=first_choice.get("finish_reason"),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
            raw=data,
        )

    async def chat(self, params: GenerationParams) -> ModelOutput:
        """通过 HTTP POST 调用上游对话补全接口。"""
        url = f"{self.base_url}{self.chat_path}"
        headers = self.build_headers()
        payload = self.build_payload(params)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            raise UpstreamUnavailableError(
                f"无法连接上游模型服务 {self.vendor}: {exc.__class__.__name__}",
                details={"base_url": self.base_url},
            ) from exc

        if response.is_error:
            self._raise_upstream_error(response)

        try:
            return self.parse_response(response.json())
        except ValueError as exc:
            raise UpstreamAPIError(
                "上游响应不是合法的 JSON",
                details={"raw_text": response.text[:1000]},
            ) from exc

    def _raise_upstream_error(self, response: httpx.Response) -> None:
        """根据上游状态码抛出对应业务异常。"""
        detail = self._extract_error_body(response)
        if response.status_code in (401, 403):
            raise UpstreamAuthenticationError(
                f"{self.vendor} 鉴权失败，请检查 API Key 是否正确或已过期",
                details=detail,
            )
        raise UpstreamAPIError(
            f"{self.vendor} 返回错误状态码 {response.status_code}",
            upstream_status=response.status_code,
            details=detail,
        )

    @staticmethod
    def _extract_error_body(response: httpx.Response) -> Dict[str, Any]:
        """尽力提取上游错误详情。"""
        try:
            return response.json()
        except ValueError:
            return {"raw_text": response.text[:1000]}
