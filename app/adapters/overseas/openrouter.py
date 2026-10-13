"""第三方 Router（OpenRouter）统一适配器。

所有国外厂商模型（OpenAI / Anthropic / Google 等）统一通过该 Router 调用，
使用全局的 ROUTER_API_KEY 完成鉴权，路由表中 vendor 统一登记为 ``router``，
上游模型名使用 Router 要求的 ``厂商/模型`` 格式（如 openai/gpt-4o）。
"""
import os
from typing import Dict

from app.adapters.openai_compatible import OpenAICompatibleAdapter
from app.core.enums import ProviderType
from app.core.registry import adapter_registry


@adapter_registry.register(ProviderType.OVERSEAS, "router")
class OpenRouterAdapter(OpenAICompatibleAdapter):
    """OpenRouter 统一路由适配器。"""

    provider = ProviderType.OVERSEAS
    vendor = "router"
    default_base_url = "https://api.nonelinear.com.cn/v1"

    def build_headers(self) -> Dict[str, str]:
        """在 Bearer 鉴权之外追加 OpenRouter 可选的归因请求头。"""
        headers = super().build_headers()
        # 可选归因信息直接从环境变量读取，保持适配器构造签名统一
        site_url = os.getenv("ROUTER_SITE_URL", "")
        site_name = os.getenv("ROUTER_SITE_NAME", "")
        if site_url:
            headers["HTTP-Referer"] = site_url
        if site_name:
            headers["X-Title"] = site_name
        return headers
