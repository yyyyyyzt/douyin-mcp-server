"""API 测试：/api/cards/structure 整理预览 + /api/cards/save 纯存储。"""

import json

import pytest
from fastapi.testclient import TestClient

import app as webapp
from core import db
from tests.helpers import auth_headers, clear_app_overrides, ensure_test_user, override_current_user


class FakeLLM:
    def __init__(self, outputs):
        self._outputs = list(outputs)

    def chat(self, messages, **kwargs):
        return self._outputs.pop(0)


def _card_payload(cards):
    return json.dumps({"cards": cards}, ensure_ascii=False)


@pytest.fixture()
def client(tmp_path):
    conn = db.connect(str(tmp_path / "api.db"))
    db.init_db(conn)
    user = ensure_test_user(conn)

    def _get_db():
        return conn

    fake = FakeLLM([
        _card_payload([
            {
                "title": "冷热水管走顶规范",
                "content": "冷热水管走顶，弹线定位，误差≤2mm，避开承重墙。",
            }
        ])
    ])

    def _resolve_llm(llm_model=""):
        return fake

    webapp.app.dependency_overrides[webapp.get_db] = _get_db
    override_current_user(user)
    original_resolve = webapp.resolve_llm_client
    webapp.resolve_llm_client = _resolve_llm
    headers = auth_headers(user)
    yield TestClient(webapp.app), conn, user, headers
    webapp.resolve_llm_client = original_resolve
    clear_app_overrides()
    conn.close()


def test_structure_returns_preview_without_save(client):
    c, conn, user, headers = client
    resp = c.post(
        "/api/cards/structure",
        json={"text": "冷热水管走顶，弹线定位，误差≤2mm，避开承重墙。"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["preview"]["title"] == "冷热水管走顶规范"
    assert db.list_cards(conn, user["id"]) == []


def test_from_text_legacy_is_structure_only(client):
    c, conn, user, headers = client
    resp = c.post("/api/cards/from-text", json={"text": "一段水电文案"}, headers=headers)
    assert resp.status_code == 200
    assert "preview" in resp.json()
    assert db.list_cards(conn, user["id"]) == []


def test_save_card_persists_without_llm(client):
    c, conn, user, headers = client
    resp = c.post(
        "/api/cards/save",
        json={"title": "标题", "content": "正文内容", "transcript": "原始转写"},
        headers=headers,
    )
    assert resp.status_code == 200
    card = resp.json()["card"]
    assert card["title"] == "标题"
    assert card["content_md"] == "正文内容"
    assert db.get_card(conn, card["id"], user["id"]) is not None


def test_structure_empty_returns_400(client):
    c, _, _, headers = client
    resp = c.post("/api/cards/structure", json={"text": "   "}, headers=headers)
    assert resp.status_code == 400


def test_save_empty_content_returns_400(client):
    c, _, _, headers = client
    resp = c.post("/api/cards/save", json={"title": "t", "content": "   "}, headers=headers)
    assert resp.status_code == 400


def test_list_cards_after_save(client):
    c, _, _, headers = client
    c.post("/api/cards/save", json={"title": "A", "content": "内容A"}, headers=headers)
    resp = c.get("/api/cards", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["cards"]) == 1


def test_get_card_detail(client):
    c, _, _, headers = client
    saved = c.post(
        "/api/cards/save",
        json={"title": "详情", "content": "一段水电文案"},
        headers=headers,
    ).json()
    card_id = saved["card"]["id"]
    resp = c.get(f"/api/cards/{card_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["card"]["title"] == "详情"


def test_get_missing_card_returns_404(client):
    c, _, _, headers = client
    resp = c.get("/api/cards/99999", headers=headers)
    assert resp.status_code == 404
