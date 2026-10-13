"""OpenAI Chat Completions 协议通用适配基类。

背景知识（写给初学者）：
OpenAI 公司定义的 "/chat/completions" 接口格式已经成了行业事实标准——
请求里传 model（模型名）和 messages（消息列表），响应里返回 choices（回答列表）
和 usage（token 用量）。很多厂商为了兼容生态，都照抄了这套格式。

DeepSeek、Moonshot、通义千问兼容模式、智谱 GLM、OpenRouter、Ollama、vLLM
等均提供 OpenAI 兼容接口，它们的请求/响应格式几乎一样，只有地址、密钥等
细节不同。所以把公共的"请求构造 / 发送 / 响应解析"逻辑收敛到本类中，
具体厂商的适配器只需继承本类、声明自己的差异点（厂商名、默认地址等），
不用重复写这些代码——这就是"模板方法"式的代码复用。

若后续接入使用非 OpenAI 私有协议的厂商（如百度文心的 OAuth 协议），
直接继承 :class:`BaseAdapter` 并实现 ``chat`` 即可，无需改动本类与服务层。

本类每个方法的职责（一次调用的完整流程）：
    chat()                     —— 总流程：拼地址 → 造请求头 → 造请求体 → 发送 → 解析
    ├── build_headers()        —— 构造请求头（带 API Key）
    ├── build_payload()        —— 构造请求体（模型、消息、采样参数）
    ├── _raise_upstream_error()—— 上游返回错误时，翻译成对应的业务异常
    └── parse_response()       —— 把上游的 JSON 翻译成统一的 ModelOutput
"""
from typing import Any, Dict, Optional

# httpx：Python 的异步 HTTP 客户端库，相当于代码版的"浏览器"，
# 用来向大模型厂商的服务器发送 HTTP 请求并接收响应
import httpx

# 适配器抽象基类（规定所有适配器必须有 chat 方法）
# 以及两个标准数据结构：统一入参 GenerationParams、统一结果 ModelOutput
from app.adapters.base import BaseAdapter, GenerationParams, ModelOutput

# 三种"上游出错"的业务异常，分别对应不同故障场景：
#   UpstreamAuthenticationError —— 密钥不对/过期（上游返回 401/403）
#   UpstreamAPIError            —— 上游返回了其他错误状态码，或响应格式不对
#   UpstreamUnavailableError    —— 根本连不上上游服务器（断网/超时/地址错）
# 这些异常最终会被全局异常处理器转成统一格式的错误响应信封
from app.exceptions import (
    UpstreamAPIError,
    UpstreamAuthenticationError,
    UpstreamUnavailableError,
)


class OpenAICompatibleAdapter(BaseAdapter):
    """``/chat/completions`` 协议适配器通用实现。

    继承自 :class:`BaseAdapter`，意味着自动拥有 api_key、base_url、timeout
    三个属性（在基类的构造函数里赋值），并且必须实现 chat() 方法。

    本类一般不直接注册使用，而是作为各具体厂商适配器的"父类"：
    子类只需声明 vendor（厂商标识）和 default_base_url（默认地址）即可。
    """

    #: 对话补全接口路径。与 base_url 拼接后就是完整请求地址，
    #: 例如 base_url="https://api.deepseek.com/v1" 时，
    #: 完整地址为 "https://api.deepseek.com/v1/chat/completions"。
    #: 定义为类属性，个别厂商路径不同时可在子类中覆盖
    chat_path: str = "/chat/completions"

    def build_headers(self) -> Dict[str, str]:
        """构造请求头，默认使用 Bearer Token 鉴权。

        "请求头"相当于寄快递时贴在包裹外的面单，告诉对方一些附加信息：
        - Content-Type: application/json 表示"包裹里装的是 JSON 格式数据"；
        - Authorization: Bearer <密钥> 是行业通用的身份凭证写法，
          服务器凭它确认"这个请求有合法身份"。

        :return: 请求头字典
        """
        headers = {"Content-Type": "application/json"}
        # 本地模型（如自建 vLLM）通常不配置密钥，此时不加 Authorization 头；
        # 如果不管有没有都加上 "Bearer None"，某些服务器会直接拒绝
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def build_payload(self, params: GenerationParams) -> Dict[str, Any]:
        """构造请求体。

        "请求体"相当于包裹里的货物清单，是发给上游的真正内容。

        入参在服务层已按「显式请求参数 > 模型级默认值」合并完成，
        此处仅做一次性写入，避免默认值覆盖顺序错误：
        参数为 None 表示"调用方和配置都没指定"，就直接不写进请求体，
        让上游模型用它自己的默认值——注意绝不能写成 None 发过去，
        否则上游可能把 None 当成"显式置空"而报错或行为异常。

        :param params: 服务层合并完成的统一推理入参
        :return: 符合 OpenAI 协议格式的请求体字典
        """
        # model 和 messages 是协议的必填项，无条件写入
        payload: Dict[str, Any] = {
            "model": params.model,
            "messages": params.messages,
        }
        # 以下可选参数逐个判断"是否为 None"，有值才写入请求体
        if params.temperature is not None:
            payload["temperature"] = params.temperature
        if params.max_tokens is not None:
            payload["max_tokens"] = params.max_tokens
        if params.top_p is not None:
            payload["top_p"] = params.top_p
        if params.stop is not None:
            payload["stop"] = params.stop
        if params.user is not None:
            payload["user"] = params.user
        return payload

    def parse_response(self, data: Dict[str, Any]) -> ModelOutput:
        """将上游响应解析为标准化 :class:`ModelOutput`。

        上游返回的 JSON 大致长这样（OpenAI 协议格式）::

            {
              "id": "chatcmpl-xxx",
              "model": "deepseek-chat",
              "choices": [
                {"index": 0, "message": {"role": "assistant", "content": "你好"},
                 "finish_reason": "stop"}
              ],
              "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                        "total_tokens": 15}
            }

        本方法做的就是从这个"大字典"里把关键字段摘出来，
        装进项目内部统一的 ModelOutput 盒子里。

        :param data: 上游响应 JSON 解析成的字典
        :return: 标准化推理结果
        :raises UpstreamAPIError: 响应中缺少 choices（协议不符）时抛出
        """
        # data.get("choices") or []：取不到 choices 或它是 None/空时用空列表兜底，
        # 避免下一步取 choices[0] 时报"索引越界"的底层错误
        choices = data.get("choices") or []
        if not choices:
            # choices 是协议的核心字段，缺了它说明上游返回了不符合协议的数据，
            # 属于异常情况。把原始响应一并放进 details，方便排查
            raise UpstreamAPIError(
                "上游响应中缺少 choices 字段",
                details={"upstream_response": data},
            )

        # 当前版本只取第一条候选回答（本项目不支持一次生成多个候选）
        first_choice = choices[0]
        # 每一层都用 "get + or {}" 兜底，防止上游返回 message: null 之类
        # 的奇葩数据导致下一步取字段时报错
        message = first_choice.get("message") or {}
        usage = data.get("usage") or {}

        return ModelOutput(
            # str() 强转：防止上游把 id 返回成数字等意外类型
            id=str(data.get("id", "")),
            model=str(data.get("model", "")),
            # content 可能为 null（如工具调用场景），统一兜底成空字符串
            content=message.get("content", "") or "",
            # 结束原因允许为 None，所以不做兜底处理
            finish_reason=first_choice.get("finish_reason"),
            # token 用量：int() 强转 + 默认 0，上游不返回用量信息时按 0 计
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            total_tokens=int(usage.get("total_tokens", 0)),
            # 保留上游原始响应，便于调试和审计（标准字段里丢掉的细节都在里面）
            raw=data,
        )

    async def chat(self, params: GenerationParams) -> ModelOutput:
        """通过 HTTP POST 调用上游对话补全接口。

        这是适配器对外的"总入口"（基类规定必须实现的方法），
        把上面几个小方法串成完整流程：拼地址 → 造头 → 造体 → 发送 → 解析。

        :param params: 统一推理入参
        :return: 标准化推理结果
        :raises UpstreamUnavailableError: 网络层面连不上上游时抛出
        :raises UpstreamAuthenticationError: 上游返回 401/403 时抛出
        :raises UpstreamAPIError: 上游返回其他错误或响应格式异常时抛出
        """
        # f-string 拼字符串：把花括号里的变量值嵌入文本，
        # 得到完整请求地址，如 "https://api.deepseek.com/v1/chat/completions"
        url = f"{self.base_url}{self.chat_path}"
        headers = self.build_headers()
        payload = self.build_payload(params)

        try:
            # async with ... as client：创建异步 HTTP 客户端并自动管理生命周期，
            # 离开 with 代码块时连接会被自动关闭（类似用完文件自动保存关闭）；
            # timeout 限制整个请求的最长等待时间，防止上游卡死拖垮本服务
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # await：等待网络往返期间不阻塞服务器处理其他请求；
                # json=payload 表示把字典自动序列化成 JSON 作为请求体发送
                print(f"url: {url}")
                print(f"headers: {headers}")
                print(f"payload: {payload}")
                response = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as exc:
            # httpx.RequestError 涵盖所有"网络层面"的失败：DNS 解析失败、
            # 连接被拒绝、读取超时等（注意：上游返回 500 错误不属于此类，
            # 因为网络通信本身成功了）。统一翻译成"上游不可用"异常。
            # "raise ... from exc" 保留原始异常链，排查时能看到底层原因
            raise UpstreamUnavailableError(
                f"无法连接上游模型服务 {self.vendor}: {exc.__class__.__name__}",
                details={"base_url": self.base_url},
            ) from exc

        # response.is_error：httpx 提供的便捷属性，状态码 >= 400 时为 True
        if response.is_error:
            self._raise_upstream_error(response)

        try:
            # response.json() 把响应文本解析成字典，再交给 parse_response
            # 翻译成标准结果，直接返回给服务层
            return self.parse_response(response.json())
        except ValueError as exc:
            # ValueError 说明响应根本不是合法 JSON（比如上游网关出错
            # 返回了 HTML 错误页）。截取前 1000 个字符放进异常详情，
            # 既方便排查又避免把超大响应全塞进日志
            raise UpstreamAPIError(
                "上游响应不是合法的 JSON",
                details={"raw_text": response.text[:1000]},
            ) from exc

    def _raise_upstream_error(self, response: httpx.Response) -> None:
        """根据上游状态码抛出对应业务异常。

        方法名以下划线开头，是 Python 的命名约定，表示"内部使用"，
        只在 chat() 出错分支中被调用，外部不应直接调用。

        :param response: 上游返回的错误响应
        :raises UpstreamAuthenticationError: 状态码为 401/403 时抛出
        :raises UpstreamAPIError: 其他错误状态码时抛出
        """
        detail = self._extract_error_body(response)
        if response.status_code in (401, 403):
            # 401 = 未认证（密钥缺失/错误）；403 = 无权限（密钥有效但被禁用/欠费）。
            # 这两类都归结为"密钥问题"，提示语直接告诉运维去检查 API Key
            raise UpstreamAuthenticationError(
                f"{self.vendor} 鉴权失败，请检查 API Key 是否正确或已过期",
                details=detail,
            )
        # 其余状态码（400 参数错、429 限流、500 上游内部错误等）
        # 统一归为"上游调用失败"，并带上上游状态码便于定位
        raise UpstreamAPIError(
            f"{self.vendor} 返回错误状态码 {response.status_code}",
            upstream_status=response.status_code,
            details=detail,
        )

    @staticmethod
    def _extract_error_body(response: httpx.Response) -> Dict[str, Any]:
        """尽力提取上游错误详情。

        "尽力"的意思是：上游的错误响应体通常是 JSON（里面写着错误原因），
        就解析出来；万一不是 JSON（如 HTML 错误页），就退回截取原始文本。
        总之保证一定返回一个字典，绝不让"提取错误信息"这一步本身再报错。

        :param response: 上游返回的错误响应
        :return: 错误详情字典，供放进异常 details 中
        """
        try:
            return response.json()
        except ValueError:
            return {"raw_text": response.text[:1000]}
