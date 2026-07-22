"""应用日志配置。

`python web/app.py` 启动时会开启 dev 模式（LOG_LEVEL=DEBUG + 请求全量日志）。
生产环境用 uvicorn/gunicorn 挂载 `web.app:app` 时默认 INFO，可通过环境变量覆盖。
"""

from __future__ import annotations

import logging
import os
import sys

_DEV_TRUTHY = frozenset({"1", "true", "yes", "on"})


def is_dev_mode() -> bool:
    return os.getenv("ZIZHUANG_DEV", "").strip().lower() in _DEV_TRUTHY


def setup_logging(*, debug: bool | None = None) -> None:
    """配置根 logger。debug=True 时默认 DEBUG 并保留 uvicorn 访问日志。"""
    if debug is None:
        debug = is_dev_mode()

    if debug:
        os.environ.setdefault("LOG_LEVEL", "DEBUG")
        os.environ.setdefault("ZIZHUANG_DEV", "1")

    level_name = os.getenv("LOG_LEVEL", "DEBUG" if debug else "INFO").upper()
    level = getattr(logging, level_name, logging.DEBUG if debug else logging.INFO)
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
        root.addHandler(handler)
    root.setLevel(level)

    if debug or level <= logging.DEBUG:
        logging.getLogger("uvicorn").setLevel(logging.DEBUG)
        logging.getLogger("uvicorn.error").setLevel(logging.DEBUG)
        logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    else:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def enable_dev_mode() -> None:
    """`python web/app.py` 入口：开启 dev 全量日志。"""
    os.environ.setdefault("ZIZHUANG_DEV", "1")
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    setup_logging(debug=True)
