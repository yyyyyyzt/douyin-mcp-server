"""Environment smoke tests.

These verify the dev environment is wired up correctly:
- core packages import (ffmpeg-python, mcp, fastapi)
- the WebUI FastAPI app responds on its health endpoint (exercised with httpx)

They intentionally avoid any network calls to Douyin / ASR APIs.
"""

import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))


def test_core_imports():
    import ffmpeg  # noqa: F401
    import mcp  # noqa: F401
    from douyin_mcp_server import server  # noqa: F401

    assert hasattr(server, "parse_douyin_video_info")


def test_webui_health_endpoint():
    from app import app

    async def _call():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.get("/api/health")

    resp = asyncio.run(_call())

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["api_key_configured"] is True


def test_webui_config_endpoint():
    from app import app

    async def _call():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.get("/api/config")

    resp = asyncio.run(_call())
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key_configured"] is True
    assert "llm_models" in body
    assert "asr_models" in body
    assert "defaults" in body
