"""DeepSeek 深度求索适配器。

平台文档：https://platform.deepseek.com
鉴权方式：独立的 DEEPSEEK_API_KEY（Bearer Token）
"""
from app.adapters.openai_compatible import OpenAICompatibleAdapter
from app.core.enums import ProviderType
from app.core.registry import adapter_registry


@adapter_registry.register(ProviderType.DOMESTIC, "deepseek")
class DeepSeekAdapter(OpenAICompatibleAdapter):
    """DeepSeek 官方 OpenAI 兼容接口适配器。"""

    provider = ProviderType.DOMESTIC
    vendor = "deepseek"
    default_base_url = "https://api.deepseek.com/v1"
