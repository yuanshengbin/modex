"""模型适配器抽象基类与通用数据结构。

所有厂商（国内 / 国外 Router / 本地）的适配器都必须实现 :class:`BaseAdapter`，
服务层只依赖该抽象，不感知具体厂商协议。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.enums import ProviderType


@dataclass
class GenerationParams:
    """厂商无关的推理入参（已合并模型级默认值）。"""

    model: str
    messages: List[Dict[str, str]]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stop: Optional[List[str]] = None
    user: Optional[str] = None


@dataclass
class ModelOutput:
    """厂商无关的标准化推理结果。"""

    id: str
    model: str
    content: str
    finish_reason: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    raw: Optional[Dict[str, Any]] = None


class BaseAdapter(ABC):
    """模型适配器抽象基类。

    :param api_key: 上游服务鉴权密钥（本地服务可为 None）
    :param base_url: 上游服务基础地址
    :param timeout: HTTP 请求超时时间（秒）
    """

    #: 提供方大类，子类必须覆盖
    provider: ProviderType
    #: 厂商标识，子类必须覆盖
    vendor: str
    #: 默认上游地址，子类可覆盖；也可被路由表中的 base_url 覆盖
    default_base_url: str = ""

    def __init__(
        self,
        *,
        api_key: Optional[str],
        base_url: str,
        timeout: float = 300.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @abstractmethod
    async def chat(self, params: GenerationParams) -> ModelOutput:
        """执行一次对话推理，返回标准化结果。"""
        raise NotImplementedError
