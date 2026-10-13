"""推理服务：模型路由分发核心逻辑。

本文件是整个项目的"大脑"，负责把一次用户提问变成一次真正的大模型调用。
可以把它类比为"总台接线员背后的调度中心"：
接口层（inference.py）只负责收发，真正"该找哪家模型、带什么钥匙（API Key）、
用什么参数去问"的决策，全部在这里完成。

处理链路::

    请求(mode/prompt/...)
        -> 路由表匹配 mode            （这次该用哪个模型？）
        -> 注册表获取厂商适配器        （该用哪个"翻译官"去对接厂商？）
        -> 按提供方类型解析鉴权凭证    （带哪把 API Key 钥匙？）
        -> 分层合并推理参数（显式入参 > 模型级默认值 > 系统兜底）
        -> 适配器执行推理              （真正发请求给大模型）
        -> 标准化结果封装              （把各家不同的返回格式统一起来）

设计要点（供初学者理解）：
- "适配器"模式：每家大模型厂商的接口格式都不一样，本项目为每家厂商写一个
  "适配器"（翻译官），把厂商的方言翻译成统一格式。本服务只跟适配器打交道，
  完全不关心背后是哪家厂商——新增厂商时只需新增一个适配器，本文件不用改。
- "无状态"：本类不保存任何一次请求的数据，所有信息都通过参数传入传出，
  因此可以安全地在整个程序里只创建一个实例（单例）供所有请求共享。
"""
import time  # 用于生成响应里的"创建时间"（Unix 时间戳）
import uuid  # 用于在上游没返回 ID 时，自行生成一个唯一 ID
from typing import Any, Optional

# 适配器抽象基类 + 两个"厂商无关"的标准数据结构：
#   GenerationParams：发给适配器的统一入参（模型名、消息列表、采样参数）
#   ModelOutput：适配器返回的统一结果（回答文本、token 用量等）
from app.adapters.base import BaseAdapter, GenerationParams, ModelOutput

# ModelRoute：一条路由配置（provider 大类 / vendor 厂商 / model 模型名 ...）
# RouteTable：路由表，mode -> ModelRoute 的字典，从 config/routes.json 加载
# Settings：全局配置（各类 API Key、超时时间等）
from app.core.config import ModelRoute, RouteTable, Settings

# 消息角色枚举（构造响应时，AI 的回答要标记为 assistant 角色）
from app.core.enums import RoleType

# 适配器注册表：一个全局字典，记录 "(提供方大类, 厂商) -> 适配器类"，
# 相当于"翻译官花名册"，需要谁就从里面查谁
from app.core.registry import adapter_registry

# 导入适配器包以触发全部适配器的注册。
# 注意：这一行看起来"没被使用"，但它的作用是——导入 app/adapters/__init__.py 时，
# 会连带导入每个厂商适配器模块，而那些模块里写着 @register_adapter 装饰器，
# 导入的瞬间就会自动把适配器登记进上面的注册表。
# 如果没有这行 import，注册表会是空的，查任何厂商都会报"未注册"。
# noqa / pylint 注释是告诉代码检查工具："这个未使用的导入是有意为之，别报警告"
import app.adapters  # noqa: F401  pylint: disable=unused-import

# 业务异常：功能未支持（流式）、提供方配置错误（缺 API Key）
from app.exceptions import FeatureNotSupportedError, ProviderConfigError

# 请求/响应的数据模型（Schema），见 app/schemas/ 目录
from app.schemas.chat import ChatCompletionRequest, Message
from app.schemas.common import ChatCompletionData, Choice, UsageInfo

# 日志工具：按模块名创建日志记录器，输出的日志会带上本文件的名字
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 系统兜底推理参数（仅在请求与模型级默认值均未指定时生效）。
# temperature（采样温度）必须有一个最终值，如果请求没传、路由配置里也没配，
# 就用这个 1.0 作为最后的保底。常量名开头加下划线是 Python 约定，
# 表示"这是模块内部私有变量，外部请勿使用"
_FALLBACK_TEMPERATURE = 1.0


class InferenceService:
    """推理编排服务，无状态、可在应用启动时构建为单例。

    "编排"（Orchestration）指的是：本类自己不直接跟任何大模型通信，
    而是像指挥家一样，把路由表、注册表、适配器、配置等部件协调起来，
    按固定流程完成一次推理。

    :param settings: 全局配置对象（含 API Key、超时时间等）
    :param route_table: 已加载完成的模型路由表
    """

    def __init__(self, settings: Settings, route_table: RouteTable) -> None:
        # __init__ 是"构造函数"：创建实例时传入依赖并保存为属性，
        # 之后的每次请求都复用这两个对象，无需重复加载
        self.settings = settings
        self.route_table = route_table

    async def chat(self, request: ChatCompletionRequest) -> ChatCompletionData:
        """执行一次完整的路由分发与模型推理。

        这是本类唯一对外公开的方法，接口层调用它即可完成整个推理流程。

        :param request: 已通过 Pydantic 校验的请求对象
                        （保证 mode 非空、prompt/messages 至少其一）
        :return: 标准化的对话补全结果（将被接口层装进统一响应信封）
        :raises FeatureNotSupportedError: 请求要求流式输出时抛出
        """
        # 前置守卫：当前版本只支持"一次性返回完整答案"，
        # 不支持"打字机式逐字返回"（流式）。遇到 stream=true 直接拒绝，
        # 抛出的异常会被全局异常处理器转成标准的错误响应信封
        if request.stream:
            raise FeatureNotSupportedError(
                "当前版本暂不支持 stream=true 流式输出"
            )

        # 1. 按 mode 匹配模型路由。
        # 例如请求传 mode="default"，就在路由表里查到对应配置：
        # provider=domestic、vendor=deepseek、model=deepseek-chat 等。
        # 查不到时 route_table.get() 内部会抛出"不支持的 mode"异常
        route = self.route_table.get(request.mode)

        # 2. 装配对应厂商的适配器：
        # 从注册表查出适配器类，解析 API Key，创建出可用的适配器实例
        adapter = self._build_adapter(route)

        # 3. 分层合并推理参数：把"请求显式传的参数"和"路由表里的默认值"
        # 按优先级合并，打包成适配器能理解的统一入参
        params = self._build_generation_params(request, route)

        # 记录一条信息级日志：本次请求被路由到了哪个厂商、哪个模型，
        # 方便事后排查问题（%s 是日志的占位符写法，参数按顺序填入）
        logger.info(
            "路由分发 mode=%s provider=%s vendor=%s upstream_model=%s",
            request.mode,
            route.provider.value,
            route.vendor,
            route.model,
        )

        # 4. 执行推理并标准化输出。
        # await 异步等待适配器把请求发给大模型并拿到结果（等待期间
        # 服务器可以处理其他请求）；拿到结果后转换成统一的数据结构返回
        output = await adapter.chat(params)
        return self._to_response_data(request.mode, output)

    # ------------------------------------------------------------------
    # 适配器装配与凭证解析
    # ------------------------------------------------------------------
    def _build_adapter(self, route: ModelRoute) -> BaseAdapter:
        """根据路由从注册表创建适配器实例。

        :param route: 本次请求命中的路由配置
        :return: 可直接调用 chat() 的适配器实例
        """
        # 从"花名册"查出适配器类（注意是类本身，还未创建实例）。
        # 例如 (provider=domestic, vendor=deepseek) -> DeepseekAdapter 类；
        # 查不到会抛出 AdapterNotFoundError
        adapter_cls = adapter_registry.get(route.provider, route.vendor)

        # 按提供方类型（国内/国外/本地）取出对应的 API Key
        api_key = self._resolve_api_key(route)

        # 决定上游服务地址，优先级与 _resolve_api_key 对称：
        #   路由表显式配置 > .env 中按提供方类型配置的地址 > 适配器自带默认地址
        # 例如国外厂商会取 .env 中的 ROUTER_BASE_URL，本地取 LOCAL_BASE_URL，
        # 国内厂商 _resolve_base_url 返回 None，最终走适配器的 default_base_url
        base_url = (
            route.base_url
            or self._resolve_base_url(route)
            or adapter_cls.default_base_url
        )

        # 用"类名(...)"创建实例，把钥匙、地址、超时时间交给它
        return adapter_cls(
            api_key=api_key,
            base_url=base_url,
            timeout=self.settings.request_timeout,
        )

    def _resolve_base_url(self, route: ModelRoute) -> Optional[str]:
        """按提供方类型解析上游服务地址。

        与 _resolve_api_key 对称，三类提供方各有配置来源：
        - 国内厂商：返回 None，由调用方走适配器自带的 default_base_url（各厂商官方地址）
        - 国外厂商：使用 .env 中的 ROUTER_BASE_URL（第三方 Router 统一地址）
        - 本地模型：使用 .env 中的 LOCAL_BASE_URL

        :param route: 本次请求命中的路由配置
        :return: 上游服务地址字符串；国内厂商返回 None 以使用适配器默认值
        """
        if route.provider.value == "overseas":
            return self.settings.router_base_url
        if route.provider.value == "local":
            return self.settings.local_base_url
        return None

    def _resolve_api_key(self, route: ModelRoute) -> Optional[str]:
        """按三类提供方分别解析鉴权凭证。

        项目硬性规定三类模型的鉴权方式完全不同：
        - 国内厂商：每家用各自独立的官方 API Key
        - 国外厂商：统一走第三方 Router，用全局 Router Key
        - 本地模型：私有化部署，默认不需要密钥

        :param route: 本次请求命中的路由配置
        :return: API Key 字符串；本地模型返回 None
        :raises ProviderConfigError: 需要的 Key 未配置时抛出
        """
        if route.provider.value == "domestic":
            # 国内厂商：settings.domestic_api_keys 是一个字典，
            # 键是厂商名（如 "deepseek"），值是从环境变量读到的 Key。
            # .get(vendor, "") 查不到时返回空字符串而不是报错，
            # 由下面的 if 统一判断并抛出带排查提示的友好异常
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
            # 国外厂商：所有国外模型共用一把第三方 Router 的全局 Key，
            # 配置一次即可，无需为每家厂商单独申请
            if not self.settings.router_api_key:
                raise ProviderConfigError(
                    "未配置第三方 Router 的 API Key",
                    details={"env_key": "ROUTER_API_KEY"},
                )
            return self.settings.router_api_key

        # 走到这里说明是本地私有化模型：默认无鉴权，返回 None
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

        举例（以 temperature 为例）：
        - 请求传了 0.7 → 最终用 0.7（用户意愿优先）；
        - 请求没传，但 routes.json 里该模型配了 0.5 → 用 0.5；
        - 都没配 → 用系统兜底值 1.0。

        注意这里刻意不用 dict.setdefault 之类的"隐式合并"，而是逐个参数
        显式判断——这是项目约定，避免上游默认值被意外覆盖。

        :param request: 已通过校验的请求对象
        :param route: 本次请求命中的路由配置
        :return: 打包好的标准推理入参，可直接交给任何厂商的适配器
        """
        # 路由表里该模型配置的默认参数（一个普通字典，可能没有某些键，
        # 所以下面统一用 .get() 取值，取不到得到 None）
        model_defaults = route.defaults
        return GenerationParams(
            # 实际要调用的上游模型名，以路由表配置为准（而非请求直传模型名），
            # 这样前端只需要知道 mode，无需关心背后用的是哪个具体模型
            model=route.model,
            # 把 prompt/messages 统一归一化成上游要求的 messages 列表格式
            messages=request.normalized_messages(),
            # 以下四个参数都走同一套三层优先级规则，由 _effective() 解析
            temperature=self._effective(
                request.temperature,
                model_defaults.get("temperature"),
                _FALLBACK_TEMPERATURE,
            ),
            # max_tokens/top_p/stop 没有系统兜底值（第三层传 None），
            # 都没配时保持 None，让上游模型用自己的默认值
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
            # 终端用户标识不参与合并，原样透传给上游做审计
            user=request.user,
        )

    @staticmethod
    def _effective(
        explicit: Any,
        model_default: Any,
        fallback: Any,
    ) -> Any:
        """解析单个参数的最终生效值。

        @staticmethod 表示这是一个"静态方法"：它不读写实例属性（self），
        只是一个挂在类上的纯工具函数——进什么参数、出什么结果，一目了然。

        判断依据是"是否为 None"：None 代表"这一层没配置"，
        就继续往下一层找；一旦某层有值（即使是 0 或空列表）立即采用。

        :param explicit: 请求显式传入的值（最高优先级）
        :param model_default: 路由表模型级默认值（次优先级）
        :param fallback: 系统兜底值（最低优先级，可以是 None）
        :return: 三层中第一个非 None 的值
        """
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
        """将适配器标准输出转换为统一响应数据模型。

        适配器返回的 ModelOutput 已经是"厂商无关"的中间格式，
        本方法再把它装进最终对外响应的 ChatCompletionData 结构中
        （该结构与 OpenAI 官方接口风格保持一致，方便前端复用成熟生态）。

        :param mode: 请求传入的路由标识，原样回填到响应中
        :param output: 适配器返回的标准化推理结果
        :return: 可直接放入统一信封 data 字段的响应数据
        """
        return ChatCompletionData(
            # 本次推理的唯一 ID：上游返回了就用上游的，
            # 没返回（如某些本地服务）就自己生成一个 "chatcmpl-随机串"
            id=output.id or f"chatcmpl-{uuid.uuid4().hex}",
            mode=mode,
            # 实际模型名：上游返回了真实模型名就用它，否则回填 mode 兜底
            model=output.model or mode,
            # 候选回答列表。当前只返回一条回答，index 固定为 0；
            # AI 说的话统一包装成 role=assistant 的消息（与多轮对话格式一致）
            choices=[
                Choice(
                    index=0,
                    message=Message(
                        role=RoleType.ASSISTANT,
                        # 上游偶尔返回空内容（如 Anthropic 仅返回工具调用块、
                        # 或模型触发了安全过滤），用兜底文本避免 Message
                        # 的 min_length=1 校验失败导致 500 错误
                        content=output.content or "(模型未返回文本内容)",
                    ),
                    # 结束原因：如 stop（正常结束）/ length（达到长度上限）
                    finish_reason=output.finish_reason,
                )
            ],
            # token 用量统计（计费/监控用）
            usage=UsageInfo(
                prompt_tokens=output.prompt_tokens,
                completion_tokens=output.completion_tokens,
                total_tokens=output.total_tokens,
            ),
            # 创建时间：取当前时间的 Unix 时间戳（秒），int() 去掉小数部分
            created=int(time.time()),
        )
