# MODEX 接口文档说明书

> AI 模型统一调度后端 API 标准参考文档。本文档作为前后端联调、第三方系统对接的唯一标准依据。

---

## 文档版本说明

| 版本   | 发布日期   | 说明                                         | 维护人     |
| ------ | ---------- | -------------------------------------------- | ---------- |
| v1.0.0 | 2026-10-16 | 初始版本，包含系统模块与模型推理模块全部接口 | MODEX 团队 |

**文档维护约定**：

- 接口发生任何变更（新增字段、修改取值范围、废弃接口等）必须同步更新本文档并递增版本号；
- 版本号遵循语义化版本规范（SemVer）：不兼容变更升级主版本号，向下兼容的功能新增升级次版本号，问题修正升级修订号；
- 每次变更必须在文末[更新日志](#五更新日志)中记录。

---

## 一、接口通用说明

### 1.1 服务基本信息

| 项目              | 说明                                                         |
| ----------------- | ------------------------------------------------------------ |
| 服务名称          | MODEX AI Backend                                             |
| 本地开发 Base URL | `http://localhost:8000`                                      |
| API 版本前缀      | `/api/v1`                                                    |
| 交互协议          | HTTP / HTTPS                                                 |
| 数据格式          | JSON（UTF-8 编码）                                           |
| 在线调试文档      | `http://localhost:8000/docs`（Swagger UI，服务启动后可访问） |

### 1.2 请求方式

| 接口类型 | 请求方法 | 说明                                           |
| -------- | -------- | ---------------------------------------------- |
| 查询类   | `GET`    | 参数通过 Query String 传递                     |
| 提交类   | `POST`   | 参数通过请求体（Request Body）以 JSON 格式传递 |

### 1.3 请求头规范

所有 `POST` 请求必须携带以下请求头：

| 请求头         | 必填 | 取值               | 说明                                           |
| -------------- | ---- | ------------------ | ---------------------------------------------- |
| `Content-Type` | 是   | `application/json` | 声明请求体为 JSON 格式，缺失将导致参数解析失败 |

**说明**：

- 本服务为内部调度网关，**不要求调用方携带鉴权请求头**；上游模型厂商的 API Key 由服务端在 `.env` 配置文件中统一管理；
- 若后续网关开启调用方鉴权，将在此处补充 `Authorization` 请求头规范。

### 1.4 请求体编写注意事项

调用方手工构造 JSON 请求体时，需特别注意以下三点（高频出错点）：

1. **多行文本必须使用转义符**：JSON 字符串内不允许出现真实的换行符、制表符等控制字符，多行内容必须写作 `\n`、`\t`；
2. **字符串内的双引号必须转义**：字段值中嵌套的双引号需写作 `\"`；
3. **数组/对象类型字段不得加引号**：如 `messages` 字段的值是数组 `[...]`，不能用引号包成字符串 `"[...]"`。

建议使用 `json.dumps()`（Python）或 `JSON.stringify()`（JavaScript）序列化生成请求体，避免手工拼接出错。

### 1.5 统一响应格式

所有接口（无论成功或失败）均返回**统一标准 JSON 信封**，结构如下：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "request_id": "4ffabb87595b495bbd455eaf5d037ade"
}
```

| 字段         | 类型                  | 是否必返 | 说明                                                                                 |
| ------------ | --------------------- | -------- | ------------------------------------------------------------------------------------ |
| `code`       | int                   | 是       | 业务状态码。`0` 表示成功，非 `0` 表示失败（详见 1.6 错误码定义）                     |
| `message`    | string                | 是       | 状态描述。成功时为 `"success"`，失败时为具体错误描述                                 |
| `data`       | object / array / null | 是       | 业务数据。成功时为接口返回的具体内容；失败时为错误详情（可能为 `null`）              |
| `request_id` | string                | 是       | 请求追踪 ID。每次请求由服务端自动生成，用于日志排查与问题定位，反馈问题时请提供此 ID |

**调用方处理约定**：请先判断 HTTP 状态码，再判断 `code` 字段。仅当 `code === 0` 时按成功逻辑解析 `data`。

### 1.6 通用错误码定义

| 业务码 code | HTTP 状态码 | 含义                    | 触发场景                                                                             | 处理建议                                    |
| ----------- | ----------- | ----------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------- |
| `0`         | 200         | 成功                    | 请求正常处理                                                                         | —                                           |
| `4000`      | 400 / 422   | 请求参数错误 / 校验失败 | 请求体非法 JSON、缺必填字段、字段类型错误、取值越界、`prompt` 与 `messages` 同时为空 | 按 `data` 中的校验明细修正请求参数          |
| `4040`      | 404         | 不支持的模型调用模式    | 传入的 `mode` 未在路由表 `config/routes.json` 中配置                                 | 参照 `data.available_modes` 选择合法 `mode` |
| `5010`      | 501         | 暂不支持的功能          | 使用了当前版本未实现的特性（如流式输出 `stream=true`）                               | 关闭该特性后重试                            |
| `5000`      | 500         | 服务内部错误            | 未预期的服务端异常                                                                   | 携带 `request_id` 联系服务端排查            |
| `5001`      | 500         | 模型适配器未注册        | 路由表指向的适配器未在代码中注册（服务端配置错误）                                   | 联系服务端检查适配器注册配置                |
| `5002`      | 500         | 模型提供方配置缺失      | 目标厂商的 API Key 未在服务端 `.env` 中配置                                          | 联系服务端补全 API Key 配置                 |
| `5021`      | 502         | 上游模型服务认证失败    | 上游厂商返回 401/403，API Key 无效或已过期                                           | 联系服务端更新 API Key                      |
| `5022`      | 502         | 上游模型服务调用失败    | 上游厂商返回其他错误状态码（如模型名不存在、额度不足）                               | 查看 `data` 中的上游原始错误信息            |
| `5030`      | 503         | 上游模型服务暂不可用    | 上游服务网络不可达或请求超时                                                         | 稍后重试；持续失败请联系服务端              |

**错误响应示例**：

```json
{
  "code": 4040,
  "message": "未找到 mode='xxx' 对应的模型路由",
  "data": {
    "available_modes": ["deepseek-flash", "gpt-4o", "qwen-plus"]
  },
  "request_id": "4ffabb87595b495bbd455eaf5d037ade"
}
```

---

## 二、系统模块

### 2.1 健康检查

查询服务存活状态及当前已注册的模型路由与适配器清单，可用于部署探活与联调前的可用性确认。

#### 接口信息

| 项目     | 内容             |
| -------- | ---------------- |
| 接口路径 | `/api/v1/health` |
| 请求方法 | `GET`            |
| 请求头   | 无特殊要求       |
| 请求参数 | 无               |

#### 响应字段说明

`data` 字段结构：

| 字段                  | 类型                | 说明                                                                           |
| --------------------- | ------------------- | ------------------------------------------------------------------------------ |
| `status`              | string              | 服务状态，固定返回 `"ok"`                                                      |
| `app`                 | string              | 应用名称，取自服务端配置 `APP_NAME`                                            |
| `registered_modes`    | array&lt;string&gt; | 已注册的模型路由标识（`mode`）列表，可用于对话补全接口的 `mode` 参数取值参考   |
| `registered_adapters` | array&lt;string&gt; | 已注册的模型适配器清单，格式为 `提供方大类:厂商标识`（如 `domestic:deepseek`） |

#### 请求示例

```bash
curl -X GET http://localhost:8000/api/v1/health
```

#### 响应示例

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "ok",
    "app": "MODEX AI Backend",
    "registered_modes": [
      "claude-opus-5.5",
      "deepseek-flash",
      "gemini-3.8-flash",
      "glm-5.3-flash",
      "gpt-4o",
      "grok-4.6",
      "kimi-k2.6",
      "local-deepseek-r1",
      "qwen-plus"
    ],
    "registered_adapters": [
      "domestic:deepseek",
      "domestic:moonshot",
      "domestic:qwen",
      "domestic:zhipu",
      "overseas:anthropic",
      "overseas:router",
      "local:ollama"
    ]
  },
  "request_id": "019a9bca14d64c7bb5363f540c86b0be"
}
```

---

## 三、模型推理模块

### 3.1 对话补全

核心接口。调用方提交问题，服务端根据 `mode` 路由到对应的大模型厂商完成推理，并将异构的上游响应归一化为统一格式返回。

#### 接口信息

| 项目     | 内容                             |
| -------- | -------------------------------- |
| 接口路径 | `/api/v1/chat/completions`       |
| 请求方法 | `POST`                           |
| 请求头   | `Content-Type: application/json` |
| 内容类型 | JSON                             |

#### 请求参数说明

| 参数          | 类型                 | 必填     | 取值约束     | 说明                                                                                                        |
| ------------- | -------------------- | -------- | ------------ | ----------------------------------------------------------------------------------------------------------- |
| `mode`        | string               | **是**   | 长度 ≥ 1     | 模型路由标识，对应服务端路由表 `config/routes.json` 中的 key。可选值见健康检查接口返回的 `registered_modes` |
| `prompt`      | string               | 条件必填 | —            | 单轮提示词。与 `messages` **至少提供一个**；同时提供时 `messages` 优先                                      |
| `messages`    | array&lt;Message&gt; | 条件必填 | —            | 多轮对话消息列表（结构见下表）。与 `prompt` 至少提供一个                                                    |
| `temperature` | float                | 否       | 0.0 ~ 2.0    | 采样温度。值越低回答越稳定，越高越发散。不传时使用路由配置的模型级默认值                                    |
| `max_tokens`  | int                  | 否       | ≥ 1          | 最大生成 token 数。不传时使用上游模型默认值                                                                 |
| `top_p`       | float                | 否       | 0.0 ~ 1.0    | 核采样概率阈值                                                                                              |
| `stop`        | array&lt;string&gt;  | 否       | —            | 停止词列表，模型生成内容命中任一停止词即终止输出                                                            |
| `stream`      | bool                 | 否       | 默认 `false` | 是否流式返回。**当前版本仅支持非流式**，传 `true` 将返回 `5010` 错误                                        |
| `user`        | string               | 否       | —            | 终端用户标识，供上游厂商审计与防滥用                                                                        |

**Message 对象结构**（`messages` 数组元素）：

| 参数      | 类型   | 必填   | 取值约束                                 | 说明                                                                                   |
| --------- | ------ | ------ | ---------------------------------------- | -------------------------------------------------------------------------------------- |
| `role`    | string | **是** | `system` / `user` / `assistant` / `tool` | 消息角色：`system`=系统指令，`user`=用户发言，`assistant`=AI 历史回答，`tool`=工具结果 |
| `content` | string | **是** | 长度 ≥ 1                                 | 消息文本内容，不允许为空字符串                                                         |

**当前已配置的 `mode` 取值参考**（以健康检查接口实时返回为准）：

| mode                | 提供方                | 实际模型         |
| ------------------- | --------------------- | ---------------- |
| `deepseek-flash`    | 国内 / DeepSeek       | deepseek-flash   |
| `kimi-k2.6`         | 国内 / Moonshot       | kimi-k2.6        |
| `qwen-plus`         | 国内 / 阿里云通义千问 | qwen-plus        |
| `glm-5.3-flash`     | 国内 / 智谱 AI        | glm-5.3-flash    |
| `gpt-4o`            | 国外 / Router 代理    | gpt-4o           |
| `gemini-3.8-flash`  | 国外 / Router 代理    | gemini-3.8-flash |
| `grok-4.6`          | 国外 / Router 代理    | grok-4.6         |
| `claude-opus-5.5`   | 国外 / Anthropic 协议 | claude-opus-5.5  |
| `local-deepseek-r1` | 本地 / Ollama         | deepseek-r1:1.5b |

#### 响应字段说明

`data` 字段结构（`ChatCompletionData`）：

| 字段      | 类型                | 说明                                    |
| --------- | ------------------- | --------------------------------------- |
| `id`      | string              | 本次推理的唯一 ID（由上游模型服务生成） |
| `mode`    | string              | 请求传入的路由模式标识                  |
| `model`   | string              | 实际执行推理的上游模型名                |
| `choices` | array&lt;Choice&gt; | 候选结果列表（当前固定返回 1 条）       |
| `usage`   | object              | Token 用量统计                          |
| `created` | int                 | 创建时间（Unix 秒级时间戳）             |

**Choice 对象结构**：

| 字段            | 类型          | 说明                                                                                                |
| --------------- | ------------- | --------------------------------------------------------------------------------------------------- |
| `index`         | int           | 候选序号，从 0 开始                                                                                 |
| `message`       | Message       | 模型生成的消息，`role` 固定为 `assistant`，`content` 为回答文本                                     |
| `finish_reason` | string / null | 结束原因。常见值：`stop`（正常结束）、`length`（达到 token 上限）、`end_turn`（Anthropic 正常结束） |

**usage 对象结构**：

| 字段                | 类型 | 说明                         |
| ------------------- | ---- | ---------------------------- |
| `prompt_tokens`     | int  | 输入消耗的 token 数          |
| `completion_tokens` | int  | 生成消耗的 token 数          |
| `total_tokens`      | int  | 总 token 数（= 输入 + 生成） |

#### 请求示例

**示例 1：单轮对话（使用 `prompt`）**

```bash
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "gpt-4o",
    "prompt": "一句话介绍你是谁",
    "max_tokens": 100
  }'
```

**示例 2：多轮对话（使用 `messages`）**

```bash
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "deepseek-flash",
    "messages": [
      {"role": "system", "content": "你是一个资深足球记者"},
      {"role": "user", "content": "梅西获得过几次金球奖？"}
    ],
    "temperature": 0.3,
    "max_tokens": 1000
  }'
```

**示例 3：Python 调用**

```python
import httpx

response = httpx.post(
    "http://localhost:8000/api/v1/chat/completions",
    json={
        "mode": "claude-opus-5.5",
        "prompt": "用一句话介绍你自己",
        "max_tokens": 100,
    },
    timeout=300.0,
)
result = response.json()

if result["code"] == 0:
    print(result["data"]["choices"][0]["message"]["content"])
else:
    print(f"调用失败 [{result['code']}]: {result['message']}")
```

#### 响应示例

**成功响应**（HTTP 200，`code = 0`）：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "chatcmpl-Cc7vHk8xYz9QwErTyUiOp",
    "mode": "gpt-4o",
    "model": "gpt-4o",
    "choices": [
      {
        "index": 0,
        "message": {
          "role": "assistant",
          "content": "我是由 OpenAI 开发的人工智能助手，可以回答问题、协助写作、编程、翻译等多种任务。"
        },
        "finish_reason": "stop"
      }
    ],
    "usage": {
      "prompt_tokens": 18,
      "completion_tokens": 36,
      "total_tokens": 54
    },
    "created": 1760590200
  },
  "request_id": "7f2c9e1a4b3d4e5f8a0b1c2d3e4f5a6b"
}
```

**失败响应示例 1 — 参数校验失败**（HTTP 422，`code = 4000`）：

```json
{
  "code": 4000,
  "message": "请求参数校验失败",
  "data": [
    {
      "type": "value_error",
      "loc": ["body", "temperature"],
      "msg": "Input should be less than or equal to 2",
      "input": 5.0
    }
  ],
  "request_id": "a1b2c3d4e5f64a7b8c9d0e1f2a3b4c5d"
}
```

**失败响应示例 2 — mode 不存在**（HTTP 404，`code = 4040`）：

```json
{
  "code": 4040,
  "message": "未找到 mode='gpt-99' 对应的模型路由",
  "data": {
    "available_modes": [
      "claude-opus-5.5",
      "deepseek-flash",
      "gemini-3.8-flash",
      "glm-5.3-flash",
      "gpt-4o",
      "grok-4.6",
      "kimi-k2.6",
      "local-deepseek-r1",
      "qwen-plus"
    ]
  },
  "request_id": "b2c3d4e5f6a75b8c9d0e1f2a3b4c5d6e"
}
```

**失败响应示例 3 — 上游服务错误**（HTTP 502，`code = 5022`）：

```json
{
  "code": 5022,
  "message": "router 返回错误状态码 422",
  "data": {
    "raw_text": "model_id错误或不支持或已下线"
  },
  "request_id": "c3d4e5f6a7b86c9d0e1f2a3b4c5d6e7f"
}
```

---

## 四、预留接口（待扩展）

> 以下条目为后续版本规划的接口占位，尚未实现。新增接口时请在本章节补充完整定义，并在[更新日志](#五更新日志)中登记。

### 4.1 流式对话补全（规划中）

| 项目         | 内容                                                           |
| ------------ | -------------------------------------------------------------- |
| 接口路径     | `/api/v1/chat/completions`（复用现有接口，`stream=true` 触发） |
| 请求方法     | `POST`                                                         |
| 状态         | 待实现。当前传 `stream=true` 返回 `5010` 错误                  |
| 预期响应格式 | SSE（Server-Sent Events）流式推送                              |

### 4.2 模型路由管理接口（规划中）

| 项目     | 内容                                                                    |
| -------- | ----------------------------------------------------------------------- |
| 接口路径 | `/api/v1/routes`                                                        |
| 请求方法 | `GET` / `POST` / `PUT` / `DELETE`                                       |
| 状态     | 待实现。提供路由表的在线增删改查能力，替代手工编辑 `config/routes.json` |

### 4.3 调用日志查询接口（规划中）

| 项目     | 内容                                                                      |
| -------- | ------------------------------------------------------------------------- |
| 接口路径 | `/api/v1/logs`                                                            |
| 请求方法 | `GET`                                                                     |
| 状态     | 待实现。按 `request_id` / 时间范围 / `mode` 查询历史调用记录与 token 用量 |

---

## 五、更新日志

### v1.0.0（2026-10-16）

- 初始版本发布
- 新增系统模块：`GET /api/v1/health` 健康检查接口
- 新增模型推理模块：`POST /api/v1/chat/completions` 对话补全接口
- 支持国内厂商（DeepSeek / Moonshot / 通义千问 / 智谱）、国外厂商（Router 代理 / Anthropic 原生协议）、本地模型（Ollama）三类接入方式
- 定义统一响应信封与 11 个业务错误码

---

**文档说明**：如对接过程中发现文档与实际响应不一致，请以实际响应为准并反馈服务端维护人修正文档。
