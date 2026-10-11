"""全局枚举定义。"""
from enum import Enum


class ProviderType(str, Enum):
    """模型提供方大类。

    - ``DOMESTIC``：国内厂商，每家使用各自独立的官方 API Key
    - ``OVERSEAS``：国外厂商，统一通过第三方 Router 调用
    - ``LOCAL``：本地私有化部署的模型服务
    """

    DOMESTIC = "domestic"
    OVERSEAS = "overseas"
    LOCAL = "local"


class RoleType(str, Enum):
    """对话消息角色。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
