"""模型适配器包。

导入本包即触发全部适配器的装饰器注册，确保路由分发时可从注册表命中。
新增厂商适配器后，只需在此处追加一行 import，核心业务逻辑无需改动。
"""
from app.adapters.base import BaseAdapter, GenerationParams, ModelOutput
from app.adapters.openai_compatible import OpenAICompatibleAdapter

# 国内厂商（每家独立 API Key）
from app.adapters.domestic import deepseek  # noqa: F401
from app.adapters.domestic import moonshot  # noqa: F401
from app.adapters.domestic import qwen  # noqa: F401
from app.adapters.domestic import zhipu  # noqa: F401

# 国外厂商（统一第三方 Router）
from app.adapters.overseas import openrouter  # noqa: F401

# 本地私有化模型
from app.adapters.local import ollama  # noqa: F401

__all__ = [
    "BaseAdapter",
    "OpenAICompatibleAdapter",
    "GenerationParams",
    "ModelOutput",
]
