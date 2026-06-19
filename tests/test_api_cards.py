"""API 测试（TDD）：/api/cards/from-text 录入 + 列表/详情读取。"""

import json

import pytest
from fastapi.testclient import TestClient

import app as webapp
from core import db


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

    def _get_db():
        return conn

    fake = FakeLLM([
        _card_payload([
            {
                "stage": "水电改造",
                "title": "冷热水管走顶规范",
                "steps": [{"order": 1, "action": "弹线定位", "detail": "用水平仪", "standard": "误差≤2mm", "warning": "避开承重墙"}],
            }
        ])
    ])

    def _get_llm():
        return fake

    webapp.app.dependency_overrides[webapp.get_db] = _get_db
    webapp.app.dependency_overrides[webapp.get_llm_client] = _get_llm
    yield TestClient(webapp.app), conn
    webapp.app.dependency_overrides.clear()
    conn.close()


def test_from_text_creates_card(client):
    c, conn = client
    resp = c.post("/api/cards/from-text", json={"text": "冷热水管走顶，弹线定位，误差≤2mm，避开承重墙。"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["cards"]) == 1
    card = data["cards"][0]
    assert card["title"] == "冷热水管走顶规范"
    assert card["id"] > 0
    # 已持久化
    assert db.get_card(conn, card["id"]) is not None


def test_from_text_empty_returns_400(client):
    c, _ = client
    resp = c.post("/api/cards/from-text", json={"text": "   "})
    assert resp.status_code == 400


def test_list_cards(client):
    c, _ = client
    c.post("/api/cards/from-text", json={"text": "一段水电文案"})
    resp = c.get("/api/cards")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["cards"]) == 1


def test_get_card_detail(client):
    c, _ = client
    created = c.post("/api/cards/from-text", json={"text": "一段水电文案"}).json()
    card_id = created["cards"][0]["id"]
    resp = c.get(f"/api/cards/{card_id}")
    assert resp.status_code == 200
    detail = resp.json()["card"]
    assert detail["id"] == card_id
    assert detail["steps"][0]["action"] == "弹线定位"  # structured_json 已解析


def test_get_missing_card_returns_404(client):
    c, _ = client
    resp = c.get("/api/cards/99999")
    assert resp.status_code == 404
