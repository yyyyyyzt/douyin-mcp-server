"""应用日志配置：stdout 结构化输出，便于 systemd / docker 收集。"""

from __future__ import annotations

import logging
import os
import sys


def setup_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    root.addHandler(handler)
    root.setLevel(level)

    # 避免 uvicorn 与自定义中间件重复刷屏（保留 error）
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
