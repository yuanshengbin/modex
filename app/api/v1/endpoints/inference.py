"""模型推理接口。

本文件的作用：对外提供一个 HTTP 接口 ``POST /api/v1/chat/completions``，
让前端（或任何调用方）把"用户想问的问题"发过来，由后端转发给对应的大模型，
再把模型的回答按统一格式返回给调用方。

可以用"总台接线员"来理解这个文件：
- 调用方打来电话（HTTP 请求）；
- 接线员（本文件的接口函数）记录来电编号（request_id）；
- 把问题转交给后台的推理服务（InferenceService）去真正联系大模型；
- 拿到答复后，装进统一的"信封"（ApiResponse）里寄回给调用方。

本文件只负责"接收请求"和"封装响应"，真正的路由分发、调用大模型等
复杂逻辑都在 app/services/inference_service.py 中完成。
"""

# ---------------- 导入部分：把需要用到的"工具"拿进来 ----------------

# APIRouter：FastAPI 提供的"路由分组器"，用来把一组相关的接口注册到一起
# Depends：FastAPI 的"依赖注入"标记，告诉框架"这个参数请自动帮我准备好"
# Request：代表本次 HTTP 请求本身，可以从中取到请求 ID 等附加信息
from fastapi import APIRouter, Depends, Request

# 从应用状态里取出"推理服务单例"的工具函数（在 app/api/deps.py 中定义）
from app.api.deps import get_inference_service

# 请求体的数据模型：规定了调用方必须传哪些字段（mode、prompt/messages 等），
# FastAPI 会自动校验传入的 JSON 是否符合这个格式，不符合就直接报 422 错误
from app.schemas.chat import ChatCompletionRequest

# 响应体的数据模型：ApiResponse 是统一响应信封（code/message/data/request_id），
# ChatCompletionData 是信封里 data 部分装的具体内容（模型回答、token 用量等）
from app.schemas.common import ApiResponse, ChatCompletionData

# 推理服务的类型标注，仅用于类型提示，让编辑器和读者知道 service 是什么
from app.services.inference_service import InferenceService

# ---------------- 创建路由器：本文件中所有接口的"总入口" ----------------

# prefix="/chat" 表示本文件里所有接口的 URL 都以 /chat 开头；
# tags=["模型推理"] 用于自动生成的接口文档（Swagger UI）中对接口进行分组展示。
# 加上外层 v1 路由的前缀后，完整路径为：POST /api/v1/chat/completions
router = APIRouter(prefix="/chat", tags=["模型推理"])


# ---------------- 接口定义：统一对话补全 ----------------

# @router.post(...) 是一个"装饰器"，作用是告诉 FastAPI：
# "下面这个函数用来处理 POST 请求，URL 路径是 /chat/completions"
#   - summary：显示在接口文档里的一句话说明
#   - response_model：声明返回值结构，FastAPI 会用它自动过滤/校验响应数据，
#     并据此生成接口文档中的响应示例
@router.post(
    "/completions",
    summary="统一对话补全（按 mode 路由到对应大模型）",
    response_model=ApiResponse[ChatCompletionData],
)
async def create_chat_completion(
    body: ChatCompletionRequest,
    request: Request,
    service: InferenceService = Depends(get_inference_service),
) -> ApiResponse[ChatCompletionData]:
    """接收前端推理参数，按 ``mode`` 路由至国内 / 国外 / 本地模型并返回结果。

    三个参数分别由 FastAPI 自动填充，调用方无需关心：

    :param body: 请求体（JSON），会被自动解析并校验成 ChatCompletionRequest 对象。
        必须包含 ``mode``（模型路由标识，对应 config/routes.json 中的 key），
        以及 ``prompt``（单轮问题）或 ``messages``（多轮对话）至少其一；
        还可以选择性传 temperature、max_tokens 等采样参数。
    :param request: 本次 HTTP 请求对象，用来取"请求 ID"（由中间件生成，
        用于全链路日志追踪，方便排查问题）。
    :param service: 推理服务单例。``Depends(get_inference_service)`` 的意思是：
        FastAPI 在处理请求前，先调用 get_inference_service() 拿到
        应用启动时就创建好的推理服务，再作为参数传进来——这就是"依赖注入"。

    :return: 统一响应信封，成功时形如::

        {
          "code": 0,
          "message": "success",
          "data": {"id": "...", "model": "...", "choices": [...], "usage": {...}},
          "request_id": "..."
        }
    """

    # 第 1 步：取出本次请求的追踪 ID。
    # request_id 由请求入口处（中间件）生成并存放在 request.state 中；
    # 用 getattr 加默认值 "" 是为了防止某些情况下（如单元测试绕过中间件）
    # request_id 不存在而报错。
    request_id = getattr(request.state, "request_id", "")

    # 第 2 步：把请求体交给推理服务，执行真正的核心业务。
    # service.chat() 内部会依次完成：
    #   1) 根据 body.mode 在路由表中查找应该调用哪个模型；
    #   2) 找到对应厂商（国内 / 国外 / 本地）的适配器；
    #   3) 合并参数、组装上游请求、调用大模型接口；
    #   4) 把上游返回的结果转换成统一的 ChatCompletionData 结构。
    # await 表示这是一次"异步等待"：在等待大模型返回期间，
    # 服务器可以去处理其他请求，不会卡住。
    data = await service.chat(body)

    # 第 3 步：把业务数据装进统一响应信封并返回。
    # ApiResponse.ok() 会自动补全 code=0、message="success"，
    # 并带上请求 ID，最终由 FastAPI 序列化成 JSON 发给调用方。
    # 如果前面任何一步出错，全局异常处理器会捕获异常，
    # 自动转换成 ApiResponse.error() 的错误信封，这里的代码无需处理异常。
    return ApiResponse.ok(data, request_id)
