"""HTTP 请求日志中间件（dev / DEBUG 时输出全量 API 访问日志）。"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from core.log_config import is_dev_mode

http_logger = logging.getLogger("zizhuang.http")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        if not (is_dev_mode() or http_logger.isEnabledFor(logging.DEBUG)):
            return await call_next(request)

        start = time.perf_counter()
        client = request.client.host if request.client else "-"
        method = request.method
        path = request.url.path
        query = request.url.query
        target = f"{path}?{query}" if query else path

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            http_logger.exception(
                "%s %s %s -> error %.1fms",
                client,
                method,
                target,
                elapsed_ms,
            )
            raise

        elapsed_ms = (time.perf_counter() - start) * 1000
        http_logger.info(
            "%s %s %s -> %s %.1fms",
            client,
            method,
            target,
            response.status_code,
            elapsed_ms,
        )
        return response
