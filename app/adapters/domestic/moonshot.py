"""Moonshot（Kimi 月之暗面）适配器。

平台文档：https://platform.moonshot.cn
鉴权方式：独立的 MOONSHOT_API_KEY（Bearer Token）
"""
from app.adapters.openai_compatible import OpenAICompatibleAdapter
from app.core.enums import ProviderType
from app.core.registry import adapter_registry


@adapter_registry.register(ProviderType.DOMESTIC, "moonshot")
class MoonshotAdapter(OpenAICompatibleAdapter):
    """Moonshot Kimi 官方 OpenAI 兼容接口适配器。"""

    provider = ProviderType.DOMESTIC
    vendor = "moonshot"
    default_base_url = "https://api.moonshot.cn/v1"
