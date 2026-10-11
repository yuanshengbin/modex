"""智谱 AI（GLM 系列）适配器。

平台文档：https://open.bigmodel.cn
鉴权方式：独立的 ZHIPU_API_KEY（Bearer Token）
"""
from app.adapters.openai_compatible import OpenAICompatibleAdapter
from app.core.enums import ProviderType
from app.core.registry import adapter_registry


@adapter_registry.register(ProviderType.DOMESTIC, "zhipu")
class ZhipuAdapter(OpenAICompatibleAdapter):
    """智谱 GLM 官方 OpenAI 兼容接口适配器。"""

    provider = ProviderType.DOMESTIC
    vendor = "zhipu"
    default_base_url = "https://open.bigmodel.cn/api/paas/v4"
