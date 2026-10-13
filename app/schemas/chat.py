"""对话推理相关的请求 Schema。

"Schema" 可以通俗地理解为"数据表格的模板"：它用代码的方式规定了一份数据
应该有哪些字段、每个字段是什么类型、是否必填、取值范围是多少。

本文件定义了两个模板：
- ``Message``：一条聊天消息长什么样（谁说的 + 说了什么）；
- ``ChatCompletionRequest``：前端发起一次"AI 问答"请求时，请求体 JSON
  必须长什么样。

它们都继承自 Pydantic 的 ``BaseModel``。Pydantic 是一个数据校验库，
FastAPI 借助它实现"自动安检"：当请求到达接口时，FastAPI 会自动把请求里的
JSON 按这些模板进行检查——
- 字段类型不对（比如把温度传成了字符串）→ 直接拒绝，返回 422 错误；
- 缺少必填字段 → 直接拒绝；
- 取值越界（比如 temperature 传了 5.0）→ 直接拒绝。
只有通过"安检"的数据才会被送到业务代码手中，因此业务代码里
不再需要写一大堆 ``if`` 去检查参数合法性。
"""

# typing 模块提供"类型标注"工具，用来告诉 Python（和阅读代码的人）
# 某个字段/变量应该是什么类型的数据：
#   - List[X]：一个列表，里面每个元素都是 X 类型
#   - Optional[X]：可以是 X 类型，也可以是 None（即"可选项"）
#   - Literal：限定只能取某几个固定的字面值
from typing import List, Literal, Optional

# Pydantic 提供的三样核心工具：
#   - BaseModel：所有数据模板的"基类"，继承它就自动获得校验能力
#   - Field：给字段附加详细信息（是否必填、默认值、取值范围、说明文字）
#   - model_validator：定义"整体验证器"，用于跨字段的联合校验
from pydantic import BaseModel, Field, model_validator

# 消息角色的枚举（在 app/core/enums.py 中定义），取值只能是：
# system（系统设定）/ user（用户）/ assistant（AI 助手）/ tool（工具）
# 使用枚举而不是裸字符串，可以避免把 "user" 误写成 "usr" 这类拼写错误
from app.core.enums import RoleType


class Message(BaseModel):
    """多轮对话中的单条消息。

    一条消息 = "谁说的" + "说了什么"。例如::

        {"role": "user", "content": "请帮我写一首关于秋天的诗"}

    常见的角色（role）有四种：
    - ``system``：系统指令，用来给 AI 设定人设/规则，如"你是一名医生"；
    - ``user``：用户说的话；
    - ``assistant``：AI 之前的回答（多轮对话时把历史回答也带上）；
    - ``tool``：工具调用的结果（本项目暂未使用）。
    """

    # Field(..., description=...) 中的三个点 ``...`` 表示"必填字段"：
    # 调用方不传这个字段，请求就会在校验阶段被拒绝
    role: RoleType = Field(..., description="消息角色：system/user/assistant/tool")

    # min_length=1 表示消息内容至少是 1 个字符，不允许发空消息
    content: str = Field(..., min_length=1, description="消息文本内容")

    def to_upstream(self) -> dict:
        """转换为上游接口所需的字典格式。

        "上游"指真正的大模型厂商接口（如 OpenAI、国内厂商 API）。
        本类中的 role 是枚举类型（RoleType.USER），而上游接口只认
        普通字符串（"user"），所以这里用 ``self.role.value`` 取出
        枚举对应的字符串值，组装成上游接口要求的普通字典。
        """
        return {"role": self.role.value, "content": self.content}


class ChatCompletionRequest(BaseModel):
    """统一对话补全请求。

    这是前端调用 ``POST /api/v1/chat/completions`` 接口时，
    请求体 JSON 必须遵守的格式。

    ``prompt`` 与 ``messages`` 至少提供一个：
    提供 ``messages`` 时支持多轮对话；仅提供 ``prompt`` 时自动包装为单轮用户消息。
    """

    # ---------- 必填字段 ----------

    # mode：告诉后端"这次要用哪个模型通道"。
    # 它的值对应路由表 config/routes.json 里配置的某个 key，
    # 后端据此决定把请求转发给国内厂商、国外厂商还是本地模型。
    # min_length=1：不允许传空字符串
    mode: str = Field(
        ...,
        min_length=1,
        description="模型路由标识，对应路由表(config/routes.json)中的 key",
    )

    # ---------- 内容字段（二选一或同时提供，messages 优先） ----------

    # Optional[str] + default=None：这个字段可以不传，不传时值为 None。
    # prompt 适合简单的单轮提问，例如："讲一个笑话"
    prompt: Optional[str] = Field(
        default=None,
        description="单轮提示词，与 messages 二选一或同时提供（messages 优先）",
    )

    # messages 是 Message 对象的列表，适合多轮对话，
    # 把之前的问答历史一起带上，AI 才能"记得"上下文
    messages: Optional[List[Message]] = Field(
        default=None,
        description="多轮对话消息列表，与 prompt 二选一或同时提供（messages 优先）",
    )

    # ---------- 可选的采样参数（不传时使用路由表里的默认配置） ----------

    # 采样温度：控制 AI 回答的"随机性/创造性"。
    # 值越低回答越稳定保守，越高越发散。ge=0.0 / le=2.0 表示
    # 取值必须大于等于 0、小于等于 2，超出范围会被校验拦截
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="采样温度，范围 0~2；不传时使用路由配置的模型级默认值",
    )

    # 最大生成 token 数：限制 AI 回答的最大长度
    # （token 可粗略理解为"字/词片段"，是模型计费的单位）。ge=1：至少生成 1 个
    max_tokens: Optional[int] = Field(
        default=None,
        ge=1,
        description="最大生成 token 数；不传时使用上游模型默认值",
    )

    # 核采样概率阈值：另一种控制随机性的方式，与 temperature 类似
    top_p: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="核采样概率阈值，范围 0~1",
    )

    # 停止词列表：AI 生成内容时一旦遇到这些词就立即停止输出
    stop: Optional[List[str]] = Field(
        default=None,
        description="停止词列表",
    )

    # 是否流式返回。流式 = 像打字机一样逐字返回；非流式 = 全部生成完一次性返回。
    # 这是一个 bool（布尔）字段，只能取 True/False，默认 False
    stream: bool = Field(
        default=False,
        description="是否流式返回（当前版本仅支持非流式）",
    )

    # 终端用户标识：标注"是哪位最终用户在用"，供上游厂商做审计和防滥用
    user: Optional[str] = Field(
        default=None,
        description="终端用户标识，用于上游侧的审计与滥用监控",
    )

    # ---------- 跨字段联合校验 ----------

    # @model_validator(mode="after") 装饰器表示：
    # "所有字段各自校验通过后，再执行一次整体检查"。
    # 因为"prompt 和 messages 至少给一个"这个规则涉及两个字段的关系，
    # 单个 Field 无法表达，所以需要在这里统一检查。
    @model_validator(mode="after")
    def _validate_content(self) -> "ChatCompletionRequest":
        """确保 prompt 与 messages 至少提供一个。"""
        # not self.prompt 在 prompt 为 None 或空字符串时都为 True，
        # messages 同理（None 或空列表）。两个都为空说明调用方
        # 根本没有提供要问的内容，属于无效请求，直接抛出错误。
        # Pydantic 会捕获 ValueError 并转换成 422 校验错误响应
        if not self.prompt and not self.messages:
            raise ValueError("prompt 与 messages 不能同时为空")
        # 校验通过：按约定必须返回自身（self），表示"这份数据没问题"
        return self

    # ---------- 数据归一化方法 ----------

    def normalized_messages(self) -> List[dict]:
        """归一化为上游统一的 messages 结构。

        无论调用方传的是 ``prompt``（单轮）还是 ``messages``（多轮），
        最终发给大模型厂商的格式统一都是 messages 列表，例如::

            [{"role": "user", "content": "你好"}]

        本方法就是做这个"统一化"处理：
        - 传了 messages（多轮对话）→ 逐条转成上游字典格式，直接使用；
        - 只传了 prompt（单轮提问）→ 自动包装成一条 role=user 的消息。
        """
        if self.messages:
            # 列表推导式：对列表里的每一条 Message 调用 to_upstream()，
            # 把结果收集成一个新列表（等价于 for 循环逐个 append）
            return [message.to_upstream() for message in self.messages]
        # 走到这里说明 messages 为空（联合校验已保证 prompt 此时必有值），
        # 把单轮 prompt 包装成标准的单元素 messages 列表
        return [{"role": "user", "content": self.prompt}]
