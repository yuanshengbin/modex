"""配置管理。

- 应用级配置通过 :class:`Settings` 从环境变量 / ``.env`` 文件加载；
- 模型路由表（mode -> provider/vendor/model 的映射）从 JSON 文件加载，
  新增模型或厂商时只需修改配置，无需改动核心代码。
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import ProviderType
from app.exceptions import UnsupportedModeError

# 项目根目录（app/core/config.py 向上三级）
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置，字段名与环境变量（.env）一一对应。"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------------- 应用 ----------------
    app_name: str = "MODEX AI Backend"
    debug: bool = False
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])
    request_timeout: float = 60.0
    routes_config_path: str = "config/routes.json"

    # ---------------- 国内厂商独立 API Key ----------------
    deepseek_api_key: str = ""
    moonshot_api_key: str = ""
    qwen_api_key: str = ""
    zhipu_api_key: str = ""

    # ---------------- 国外厂商第三方 Router ----------------
    router_api_key: str = ""
    router_base_url: str = "https://openrouter.ai/api/v1"
    router_site_url: str = ""
    router_site_name: str = ""

    # ---------------- 本地私有化模型 ----------------
    local_base_url: str = "http://localhost:11434/v1"

    @property
    def domestic_api_keys(self) -> Dict[str, str]:
        """国内厂商标识到独立 API Key 的映射。

        新增国内厂商时，在此注册其 Key 字段即可。
        """
        return {
            "deepseek": self.deepseek_api_key,
            "moonshot": self.moonshot_api_key,
            "qwen": self.qwen_api_key,
            "zhipu": self.zhipu_api_key,
        }

    def resolve_routes_path(self) -> Path:
        """将配置中的路由表路径解析为绝对路径。"""
        path = Path(self.routes_config_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path


class ModelRoute(BaseModel):
    """单条模型路由配置。

    :param provider: 模型提供方大类
    :param vendor: 提供方下的厂商标识，用于定位适配器
    :param model: 实际上游模型名称
    :param base_url: 可选的上游地址覆盖（如指向自建 vLLM 服务）
    :param defaults: 模型级默认推理参数，请求显式传入的参数优先级更高
    """

    provider: ProviderType
    vendor: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    base_url: Optional[str] = None
    defaults: Dict[str, Any] = Field(default_factory=dict)


class RouteTable:
    """mode 到 :class:`ModelRoute` 的路由表。"""

    def __init__(self) -> None:
        self._routes: Dict[str, ModelRoute] = {}

    def load(self, path: Path) -> None:
        """从 JSON 文件加载路由表。"""
        if not path.exists():
            raise FileNotFoundError(f"模型路由配置文件不存在: {path}")

        raw = json.loads(path.read_text(encoding="utf-8"))
        raw_routes = raw.get("routes", raw)
        if not isinstance(raw_routes, dict):
            raise ValueError("路由配置文件中的 routes 必须是对象")

        self._routes = {
            mode: ModelRoute(**route_conf)
            for mode, route_conf in raw_routes.items()
        }

    def get(self, mode: str) -> ModelRoute:
        """按 mode 精确匹配路由，未命中则抛出异常。"""
        route = self._routes.get(mode)
        if route is None:
            raise UnsupportedModeError(
                f"未找到 mode='{mode}' 对应的模型路由",
                details={"available_modes": self.list_modes()},
            )
        return route

    def list_modes(self) -> List[str]:
        """返回全部已注册的 mode。"""
        return sorted(self._routes.keys())

    def __len__(self) -> int:
        return len(self._routes)


def get_settings() -> Settings:
    """构造配置实例（每次调用读取最新环境变量）。"""
    return Settings()
