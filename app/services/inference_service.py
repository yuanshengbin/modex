"""推理服务：模型路由分发核心逻辑。

处理链路::

    请求(mode/prompt/...)
        -> 路由表匹配 mode
        -> 注册表获取厂商适配器
        -> 按提供方类型解析鉴权凭证
        -> 分层合并推理参数（显式入参 > 模型级默认值 > 系统兜底）
        -> 适配器执行推理
        -> 标准化结果封装
"""
import time
import uuid
from typing import Any, Optional

from app.adapters.base import BaseAdapter, GenerationParams, ModelOutput
from app.core.config import ModelRoute, RouteTable, Settings
from app.core.enums import RoleType
from app.core.registry import adapter_registry

# 导入适配器包以触发全部适配器的注册
import app.adapters  # noqa: F401  pylint: disable=unused-import

from app.exceptions import FeatureNotSupportedError, ProviderConfigError
from app.schemas.chat import ChatCompletionRequest, Message
from app.schemas.common import ChatCompletionData, Choice, UsageInfo
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 系统兜底推理参数（仅在请求与模型级默认值均未指定时生效）
_FALLBACK_TEMPERATURE = 1.0


class InferenceService:
    """推理编排服务，无状态、可在应用启动时构建为单例。"""

    def __init__(self, settings: Settings, route_table: RouteTable) -> None:
        self.settings = settings
        self.route_table = route_table

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionData:
        """执行一次完整的路由分发与模型推理。"""
        if request.stream:
            raise FeatureNotSupportedError(
                "当前版本暂不支持 stream=true 流式输出"
            )

        # 1. 按 mode 匹配模型路由
        route = self.route_table.get(request.mode)

        # 2. 装配对应厂商的适配器
        adapter = self._build_adapter(route)

        # 3. 分层合并推理参数
        params = self._build_generation_params(request, route)

        logger.info(
            "路由分发 mode=%s provider=%s vendor=%s upstream_model=%s",
            request.mode,
            route.provider.value,
            route.vendor,
            route.model,
        )

        # 4. 执行推理并标准化输出
        output = await adapter.chat(params)
        return self._to_response_data(request.mode, output)

    # ------------------------------------------------------------------
    # 适配器装配与凭证解析
    # ------------------------------------------------------------------
    def _build_adapter(self, route: ModelRoute) -> BaseAdapter:
        """根据路由从注册表创建适配器实例。"""
        adapter_cls = adapter_registry.get(route.provider, route.vendor)
        api_key = self._resolve_api_key(route)
        base_url = route.base_url or adapter_cls.default_base_url
        return adapter_cls(
            api_key=api_key,
            base_url=base_url,
            timeout=self.settings.request_timeout,
        )

    def _resolve_api_key(self, route: ModelRoute) -> Optional[str]:
        """按三类提供方分别解析鉴权凭证。"""
        if route.provider.value == "domestic":
            # 国内厂商：每家独立的官方 API Key
            api_key = self.settings.domestic_api_keys.get(route.vendor, "")
            if not api_key:
                raise ProviderConfigError(
                    f"未配置国内厂商 {route.vendor} 的 API Key",
                    details={
                        "vendor": route.vendor,
                        "env_key": f"{route.vendor.upper()}_API_KEY",
                    },
                )
            return api_key

        if route.provider.value == "overseas":
            # 国外厂商：统一的第三方 Router 全局 Key
            if not self.settings.router_api_key:
                raise ProviderConfigError(
                    "未配置第三方 Router 的 API Key",
                    details={"env_key": "ROUTER_API_KEY"},
                )
            return self.settings.router_api_key

        # 本地私有化模型：默认无鉴权
        return None

    # ------------------------------------------------------------------
    # 参数合并与结果封装
    # ------------------------------------------------------------------
    def _build_generation_params(
        self,
        request: ChatCompletionRequest,
        route: ModelRoute,
    ) -> GenerationParams:
        """按优先级合并参数并构造厂商无关的推理入参。

        优先级：请求显式传入 > 路由表模型级 defaults > 系统兜底默认值。
        """
        model_defaults = route.defaults
        return GenerationParams(
            model=route.model,
            messages=request.normalized_messages(),
            temperature=self._effective(
                request.temperature,
                model_defaults.get("temperature"),
                _FALLBACK_TEMPERATURE,
            ),
            max_tokens=self._effective(
                request.max_tokens,
                model_defaults.get("max_tokens"),
                None,
            ),
            top_p=self._effective(
                request.top_p,
                model_defaults.get("top_p"),
                None,
            ),
            stop=self._effective(
                request.stop,
                model_defaults.get("stop"),
                None,
            ),
            user=request.user,
        )

    @staticmethod
    def _effective(
        explicit: Any,
        model_default: Any,
        fallback: Any,
    ) -> Any:
        """解析单个参数的最终生效值。"""
        if explicit is not None:
            return explicit
        if model_default is not None:
            return model_default
        return fallback

    @staticmethod
    def _to_response_data(
        mode: str,
        output: ModelOutput,
    ) -> ChatCompletionData:
        """将适配器标准输出转换为统一响应数据模型。"""
        return ChatCompletionData(
            id=output.id or f"chatcmpl-{uuid.uuid4().hex}",
            mode=mode,
            model=output.model or mode,
            choices=[
                Choice(
                    index=0,
                    message=Message(
                        role=RoleType.ASSISTANT,
                        content=output.content,
                    ),
                    finish_reason=output.finish_reason,
                )
            ],
            usage=UsageInfo(
                prompt_tokens=output.prompt_tokens,
                completion_tokens=output.completion_tokens,
                total_tokens=output.total_tokens,
            ),
            created=int(time.time()),
        )
