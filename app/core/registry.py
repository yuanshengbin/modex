"""模型适配器注册表。

各厂商适配器通过 ``@register_adapter`` 装饰器自行注册，
核心业务逻辑只依赖注册表，不感知任何具体厂商，符合开闭原则。
"""
from typing import TYPE_CHECKING, Dict, Tuple, Type

from app.core.enums import ProviderType
from app.exceptions import AdapterNotFoundError

if TYPE_CHECKING:
    from app.adapters.base import BaseAdapter


class AdapterRegistry:
    """``(provider, vendor) -> 适配器类`` 的全局注册表。"""

    def __init__(self) -> None:
        self._registry: Dict[Tuple[str, str], Type["BaseAdapter"]] = {}

    def register(
        self,
        provider: ProviderType,
        vendor: str,
    ) -> Type["BaseAdapter"]:
        """类装饰器：注册一个适配器类。"""

        def decorator(
            adapter_cls: Type["BaseAdapter"],
        ) -> Type["BaseAdapter"]:
            key = self._build_key(provider, vendor)
            if key in self._registry:
                raise ValueError(f"适配器重复注册: {key}")
            self._registry[key] = adapter_cls
            return adapter_cls

        return decorator

    def get(
        self,
        provider: ProviderType,
        vendor: str,
    ) -> Type["BaseAdapter"]:
        """获取适配器类，未注册时抛出 :class:`AdapterNotFoundError`。"""
        key = self._build_key(provider, vendor)
        adapter_cls = self._registry.get(key)
        if adapter_cls is None:
            raise AdapterNotFoundError(
                f"未注册 provider={provider.value}, vendor={vendor} 的模型适配器",
                details={"registered": self.list_keys()},
            )
        return adapter_cls

    def list_keys(self) -> list[str]:
        """列出所有已注册键，便于排查配置问题。"""
        return [f"{provider}:{vendor}" for provider, vendor in self._registry]

    @staticmethod
    def _build_key(provider: ProviderType, vendor: str) -> Tuple[str, str]:
        return ProviderType(provider).value, vendor


# 全局单例
adapter_registry = AdapterRegistry()
