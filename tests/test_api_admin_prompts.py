"""API 测试：/api/admin/prompts 提示词管理。"""

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))

from app import app  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


async def _get(path, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path, headers=headers or {})


async def _put(path, json_body, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.put(path, json=json_body, headers=headers or {})


async def _post(path, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(path, headers=headers or {})


def test_admin_prompts_list_without_token_when_open(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    resp = _run(_get("/api/admin/prompts"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["prompts"]) >= 5
    assert body["prompts"][0]["key"]
    assert "content" in body["prompts"][0]


def test_admin_prompts_requires_token_when_configured(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "secret-admin")
    denied = _run(_get("/api/admin/prompts"))
    ok = _run(_get("/api/admin/prompts", headers={"X-Admin-Token": "secret-admin"}))
    assert denied.status_code == 403
    assert ok.status_code == 200


def test_admin_prompts_save_and_reset(tmp_path, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    path = tmp_path / "prompts.json"
    monkeypatch.setattr("core.prompts.PROMPTS_PATH", path)

    save = _run(_put("/api/admin/prompts", {"prompts": {"qa_grounded": "管理员自定义"}}))
    assert save.status_code == 200

    listed = _run(_get("/api/admin/prompts"))
    grounded = next(p for p in listed.json()["prompts"] if p["key"] == "qa_grounded")
    assert grounded["content"] == "管理员自定义"
    assert grounded["is_custom"] is True

    reset = _run(_post("/api/admin/prompts/reset"))
    assert reset.status_code == 200
    after = next(p for p in reset.json()["prompts"] if p["key"] == "qa_grounded")
    assert after["is_custom"] is False
