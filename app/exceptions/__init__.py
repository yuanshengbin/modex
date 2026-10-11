"""自定义业务异常体系。

所有异常均继承 :class:`AppException`，由统一的异常处理器转换为标准 JSON 响应。
"""
from typing import Any, Optional


class AppException(Exception):
    """业务异常基类。

    :param message: 面向用户的错误描述
    :param status_code: 对应的 HTTP 状态码
    :param code: 业务错误码（默认与 HTTP 状态码一致）
    :param details: 附加调试信息
    """

    status_code: int = 500
    code: int = 5000
    message: str = "服务内部错误"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        details: Optional[Any] = None,
    ) -> None:
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)


class ClientRequestError(AppException):
    """客户端请求参数错误。"""

    status_code = 400
    code = 4000
    message = "请求参数错误"


class UnsupportedModeError(AppException):
    """传入的 mode 在路由表中不存在。"""

    status_code = 404
    code = 4040
    message = "不支持的模型调用模式"


class FeatureNotSupportedError(AppException):
    """当前模型/服务暂不支持该特性（如流式输出）。"""

    status_code = 501
    code = 5010
    message = "暂不支持的功能"


class AdapterNotFoundError(AppException):
    """路由表指向的适配器未注册（通常是配置错误）。"""

    status_code = 500
    code = 5001
    message = "模型适配器未注册"


class ProviderConfigError(AppException):
    """提供方配置缺失，例如未配置对应厂商的 API Key。"""

    status_code = 500
    code = 5002
    message = "模型提供方配置缺失"


class UpstreamAuthenticationError(AppException):
    """调用上游模型服务时认证失败（API Key 无效或过期）。"""

    status_code = 502
    code = 5021
    message = "上游模型服务认证失败"


class UpstreamAPIError(AppException):
    """上游模型服务返回了非预期的错误状态码。"""

    status_code = 502
    code = 5022
    message = "上游模型服务调用失败"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        upstream_status: Optional[int] = None,
        details: Optional[Any] = None,
    ) -> None:
        self.upstream_status = upstream_status
        super().__init__(message, details=details)


class UpstreamUnavailableError(AppException):
    """上游模型服务网络不可达或超时。"""

    status_code = 503
    code = 5030
    message = "上游模型服务暂不可用"
