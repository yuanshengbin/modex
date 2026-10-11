"""通义千问 Qwen（阿里云百炼 DashScope）适配器。

平台文档：https://help.aliyun.com/zh/dashscope/
鉴权方式：独立的 QWEN_API_KEY（即 DASHSCOPE_API_KEY，Bearer Token）
接入方式：DashScope 提供的 OpenAI 兼容模式（compatible-mode）
"""
from app.adapters.openai_compatible import OpenAICompatibleAdapter
from app.core.enums import ProviderType
from app.core.registry import adapter_registry


@adapter_registry.register(ProviderType.DOMESTIC, "qwen")
class QwenAdapter(OpenAICompatibleAdapter):
    """通义千问 DashScope 兼容模式适配器。"""

    provider = ProviderType.DOMESTIC
    vendor = "qwen"
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
