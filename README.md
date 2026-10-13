# MODEX — AI 模型统一调度后端

MODEX 是一个基于 FastAPI 构建的 AI 模型统一调度服务，通过一套标准 API 接口聚合国内外多家大模型厂商，让前端只需对接一个后端即可按需调用不同模型。

## 项目概述

### 定位

MODEX 充当"模型路由网关"：接收前端的标准对话请求，根据 `mode` 参数将请求路由到对应的大模型厂商，将厂商返回的异构响应归一化为统一格式后返回给调用方。

### 核心功能

- **统一接口**：一套 `POST /api/v1/chat/completions` 接口对接所有模型
- **三类分区接入**：国内厂商（独立 API Key）、国外厂商（统一 Router）、本地模型（Ollama / vLLM）
- **适配器自动注册**：新增厂商只需编写适配器模块并配置路由表，无需改动核心逻辑
- **统一响应信封**：所有响应包含 `code` / `message` / `data` / `request_id` 四字段标准格式
- **双协议适配**：同时支持 OpenAI 兼容协议和 Anthropic 原生 Messages 协议

### 应用场景

- 前端应用需要灵活切换不同大模型但不想对接多家 SDK
- 团队内部搭建统一的 AI 网关，集中管理 API Key 和调用策略
- 对接本地私有化部署模型（如 Ollama），与云端模型统一调度

## 技术栈

| 技术 | 用途 | 版本要求 |
|------|------|---------|
| [FastAPI](https://fastapi.tiangolo.com/) | Web 框架，接口定义与自动校验 | >= 0.115.0 |
| [Uvicorn](https://www.uvicorn.org/) | ASGI 服务器 | >= 0.30.0 |
| [httpx](https://www.python-httpx.org/) | 异步 HTTP 客户端，调用上游模型 API | >= 0.27.0 |
| [Pydantic](https://docs.pydantic.dev/) | 数据模型与请求参数校验 | >= 2.7.0 |
| [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | 环境变量配置管理 | >= 2.3.0 |

**运行环境**：Python 3.11+

## 快速开始

### 1. 克隆项目

```bash
git clone <仓库地址>
cd modex
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

复制 `.env.example` 为 `.env` 并填写 API Key：

```bash
cp .env.example .env
```

关键配置项说明：

```ini
# 国内厂商（各自独立 API Key）
DEEPSEEK_API_KEY=sk-xxx
MOONSHOT_API_KEY=sk-xxx
QWEN_API_KEY=sk-xxx
ZHIPU_API_KEY=xxx.xxx

# 国外厂商（统一 Router）
ROUTER_API_KEY=sk-xxx
ROUTER_BASE_URL=https://api.nonelinear.com.cn/v1

# 本地模型
LOCAL_BASE_URL=http://localhost:11434/v1
```

### 5. 启动服务

```bash
python run.py
```

启动后可访问：

- API 文档（Swagger UI）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/v1/health

## 使用说明

### 对话补全接口

```
POST /api/v1/chat/completions
```

**请求体参数**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `mode` | string | 是 | 模型路由标识，如 `deepseek-flash`、`gpt-4o`、`claude-opus-5.5` |
| `prompt` | string | 否 | 用户提示词（与 `messages` 二选一） |
| `messages` | array | 否 | 多轮对话消息列表（与 `prompt` 二选一） |
| `temperature` | float | 否 | 采样温度，范围 0.0 ~ 2.0 |
| `max_tokens` | int | 否 | 最大生成 token 数 |
| `top_p` | float | 否 | 核采样概率 |
| `stop` | array | 否 | 停止词列表 |
| `user` | string | 否 | 用户标识 |

**示例 — 单轮对话**：

```bash
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"mode": "gpt-4o", "prompt": "一句话介绍你是谁", "max_tokens": 100}'
```

**示例 — 多轮对话**：

```bash
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "deepseek-flash",
    "messages": [
      {"role": "user", "content": "你好"},
      {"role": "assistant", "content": "你好！有什么可以帮你的？"},
      {"role": "user", "content": "介绍一下你自己"}
    ]
  }'
```

**成功响应**：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "chatcmpl-xxx",
    "model": "gpt-4o",
    "choices": [
      {
        "index": 0,
        "message": {"role": "assistant", "content": "我是一个 AI 助手..."},
        "finish_reason": "stop"
      }
    ],
    "usage": {
      "prompt_tokens": 10,
      "completion_tokens": 20,
      "total_tokens": 30
    }
  },
  "request_id": "a1b2c3d4"
}
```

**错误响应**：

```json
{
  "code": 5001,
  "message": "未找到 mode='xxx' 对应的模型路由",
  "data": {"available_modes": ["deepseek-flash", "gpt-4o"]},
  "request_id": "a1b2c3d4"
}
```

### 错误码

| 错误码 | 含义 |
|--------|------|
| 0 | 成功 |
| 4001 | 请求参数校验失败 |
| 5001 | 不支持的模型 mode |
| 5002 | 厂商配置缺失（API Key 未配置） |
| 5021 | 上游服务不可用（网络错误） |
| 5022 | 上游鉴权失败或返回错误状态码 |
| 9999 | 未预期的服务异常 |

### 新增模型路由

在 `config/routes.json` 中添加一条路由即可，无需改动代码：

```json
{
  "my-new-model": {
    "provider": "domestic",
    "vendor": "deepseek",
    "model": "deepseek-chat"
  }
}
```

- `mode`（键名）：前端传入的模型标识，自定义命名
- `provider`：提供方大类 — `domestic` / `overseas` / `local`
- `vendor`：厂商标识 — 需与已注册适配器的 vendor 一致
- `model`：上游实际模型名 — 需使用厂商平台支持的名称
- `base_url`（可选）：覆盖默认上游地址

### 新增模型厂商

1. 在 `app/adapters/` 对应分区下新建适配器文件，继承 `OpenAICompatibleAdapter`（OpenAI 协议）或 `BaseAdapter`（自定义协议），用 `@adapter_registry.register(provider, vendor)` 注册
2. 在 `app/adapters/__init__.py` 中添加导入
3. 在 `config/routes.json` 中配置路由映射
4. 如为国内厂商，在 `.env` 和 `Settings.domestic_api_keys` 中注册 API Key 字段

### 常见问题

**Q: 调用返回 404 / 5022？**
A: 检查 `routes.json` 中的 `model` 字段是否使用了厂商平台实际支持的模型名。模型名错误时上游会返回 404。

**Q: 调用返回 5002？**
A: 对应厂商的 API Key 未在 `.env` 中配置。国内厂商需各自配置独立 Key。

**Q: Anthropic 模型（Claude）返回 422？**
A: Anthropic 使用原生 Messages 协议（非 OpenAI 协议），确保路由配置中 `vendor` 设为 `"anthropic"` 并配置了 `base_url`。

**Q: 本地模型调用失败？**
A: 确认 Ollama 已启动且 `LOCAL_BASE_URL` 地址正确。可通过 `curl http://localhost:11434/v1/models` 验证。

## 项目结构

```
modex/
├── app/
│   ├── main.py                      # 应用入口，FastAPI 实例创建与中间件注册
│   ├── adapters/                    # 模型适配器层
│   │   ├── base.py                  # BaseAdapter 抽象基类 + GenerationParams / ModelOutput
│   │   ├── openai_compatible.py     # OpenAI 兼容协议实现（HTTP 发送 + 错误处理管线）
│   │   ├── domestic/                # 国内厂商适配器
│   │   │   ├── deepseek.py          # DeepSeek
│   │   │   ├── moonshot.py           # Moonshot（Kimi）
│   │   │   ├── qwen.py              # 阿里云通义千问
│   │   │   └── zhipu.py             # 智谱 AI（GLM）
│   │   ├── overseas/                # 国外厂商适配器
│   │   │   ├── openrouter.py        # OpenRouter（OpenAI 兼容协议）
│   │   │   └── anthropic.py         # Anthropic（Claude 原生 Messages 协议）
│   │   └── local/                   # 本地模型适配器
│   │       └── ollama.py            # Ollama / vLLM
│   ├── api/                         # API 接口层
│   │   ├── deps.py                  # 依赖注入（获取 InferenceService 单例）
│   │   └── v1/
│   │       ├── router.py            # v1 路由聚合
│   │       └── endpoints/
│   │           ├── health.py        # 健康检查 / 模型列表
│   │           └── inference.py     # 对话补全接口
│   ├── core/                        # 核心基础设施
│   │   ├── config.py                # Settings 配置 + ModelRoute + RouteTable
│   │   ├── enums.py                 # 枚举（ProviderType / RoleType）
│   │   └── registry.py              # 适配器注册表（装饰器自动注册）
│   ├── exceptions/                  # 异常定义与全局处理
│   │   ├── __init__.py              # 业务异常类定义
│   │   └── handlers.py              # 全局异常处理 → 统一响应格式
│   ├── schemas/                     # Pydantic 数据模型
│   │   ├── chat.py                  # 请求 Schema（ChatCompletionRequest / Message）
│   │   └── common.py               # 响应 Schema（ApiResponse / ChatCompletionData）
│   ├── services/                    # 业务服务层
│   │   └── inference_service.py     # InferenceService（路由分发 + 参数合并 + 适配器调度）
│   └── utils/
│       └── logger.py                # 日志配置
├── config/
│   └── routes.json                  # 模型路由表配置
├── docs/
│   └── 零基础项目教学指南.md          # 面向零基础的项目教学文档
├── .env.example                     # 环境变量模板
├── requirements.txt                 # Python 依赖
├── run.py                            # 启动入口
└── README.md
```

## 开发规范

### 代码规范

- 遵循 [PEP 8](https://peps.python.org/pep-0008/) 编码规范
- 所有函数和方法添加**类型注解**（参数与返回值）
- 面向零基础用户添加注释，使用通俗类比说明逻辑职责

### 架构约定

- 模型接入按三类严格分区：国内厂商独立 API Key、国外厂商统一 Router、本地模型独立配置
- 新增模型厂商时**不得修改核心业务逻辑**，仅需新增适配器模块并在路由表配置映射
- 所有接口响应使用统一标准 JSON 信封格式（`code` / `message` / `data` / `request_id`）
- 参数合并采用显式分层规则：`请求参数 > 路由表模型级默认配置 > 系统兜底`
- 适配器通过装饰器 `@adapter_registry.register(provider, vendor)` 自动注册

### 分支管理

| 分支 | 用途 |
|------|------|
| `main` | 生产稳定分支，受保护 |
| `dev` | 日常开发集成分支 |
| `feature/*` | 新功能开发分支 |
| `fix/*` | Bug 修复分支 |

### 提交信息规范

使用 Conventional Commits 格式：

```
<type>(<scope>): <subject>

type:    feat（新功能）/ fix（修复）/ docs（文档）/ refactor（重构）/ test（测试）
scope:   可选，影响的模块（如 adapters / routes / config）
subject: 简洁描述
```

示例：

```
feat(adapters): 新增 Anthropic Messages API 适配器
fix(inference): 修复空内容响应导致 500 错误
docs(readme): 编写项目 README 文档
```

## 贡献指南

1. **Fork** 本仓库并克隆到本地
2. 从 `dev` 分支创建功能分支：`git checkout -b feature/your-feature`
3. 编写代码并确保：
   - 通过 `python -c "import ast; ast.parse(open('app/services/inference_service.py').read())"` 语法检查
   - 新增适配器已用 `@adapter_registry.register()` 注册并在 `__init__.py` 导入
   - 新增模型已在 `config/routes.json` 配置路由
   - 不修改核心业务逻辑（`inference_service.py` 的调度链路）
4. 提交代码，遵循[提交信息规范](#提交信息规范)
5. 发起 Pull Request 到 `dev` 分支，描述变更内容与测试方式

**适配器开发要点**：

```python
from app.adapters.openai_compatible import OpenAICompatibleAdapter
from app.core.enums import ProviderType
from app.core.registry import adapter_registry


@adapter_registry.register(ProviderType.DOMESTIC, "newvendor")
class NewVendorAdapter(OpenAICompatibleAdapter):
    """厂商适配器。"""

    provider = ProviderType.DOMESTIC
    vendor = "newvendor"
    default_base_url = "https://api.newvendor.com/v1"

    # 如厂商协议与 OpenAI 兼容，无需实现 chat()；
    # 如有差异，覆盖 build_headers / build_payload / parse_response 即可。
```

## 许可证

本项目采用 [MIT License](https://opensource.org/licenses/MIT) 开源协议。
