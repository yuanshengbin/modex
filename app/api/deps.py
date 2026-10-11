"""FastAPI 依赖注入：从应用状态中获取共享组件。"""
from fastapi import Request

from app.core.config import RouteTable, Settings
from app.services.inference_service import InferenceService


def get_settings(request: Request) -> Settings:
    """获取应用配置。"""
    return request.app.state.settings


def get_route_table(request: Request) -> RouteTable:
    """获取模型路由表。"""
    return request.app.state.route_table


def get_inference_service(request: Request) -> InferenceService:
    """获取推理服务单例。"""
    return request.app.state.inference_service
