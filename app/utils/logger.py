"""日志工具。"""
import logging
import sys

_DEFAULT_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s"
)


def setup_logging(level: str = "INFO") -> None:
    """初始化全局日志配置。"""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=_DEFAULT_FORMAT,
        stream=sys.stdout,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger。"""
    return logging.getLogger(name)
