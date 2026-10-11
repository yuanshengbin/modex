"""v1 路由聚合。"""
from fastapi import APIRouter

from app.api.v1.endpoints import health, inference

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(inference.router)
