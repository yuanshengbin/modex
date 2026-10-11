"""本地 Ollama 模型服务适配器。

Ollama 从 v0.1.14 起内置 OpenAI 兼容接口（默认 http://localhost:11434/v1），
本地服务默认无需鉴权。

由于 vLLM、LocalAI、Xinference 等本地推理框架同样暴露 OpenAI 兼容接口，
路由表中可通过 ``base_url`` 覆盖指向这些服务，无需新增适配器：

    {"provider": "local", "vendor": "ollama",
     "model": "Qwen2.5-7B-Instruct",
     "base_url": "http://localhost:8000/v1"}

若本地服务开启了 Token 鉴权，在 :meth:`build_headers` 中补充即可。
"""
from typing import Dict

from app.adapters.openai_compatible import OpenAICompatibleAdapter
from app.core.enums import ProviderType
from app.core.registry import adapter_registry


@adapter_registry.register(ProviderType.LOCAL, "ollama")
class OllamaAdapter(OpenAICompatibleAdapter):
    """本地 Ollama / 兼容 OpenAI 协议的私有模型服务适配器。"""

    provider = ProviderType.LOCAL
    vendor = "ollama"
    default_base_url = "http://localhost:11434/v1"

    def build_headers(self) -> Dict[str, str]:
        """本地服务默认无鉴权，仅保留内容类型头。"""
        return {"Content-Type": "application/json"}
