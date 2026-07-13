"""API 测试（TDD）：PUT /api/cards/{id} 编辑 + DELETE /api/cards/{id} 删除。"""

import json

import pytest
from fastapi.testclient import TestClient

import app as webapp
from core import db
from tests.helpers import auth_headers, clear_app_overrides, ensure_test_user, override_current_user


def _structured(title, content):
    return json.dumps({"title": title, "content": content}, ensure_ascii=False)


@pytest.fixture()
def env(tmp_path):
    db_path = str(tmp_path / "edit.db")
    conn = db.connect(db_path)
    db.init_db(conn)
    user = ensure_test_user(conn)

    webapp.app.dependency_overrides[webapp.get_db_path] = lambda: db_path
    override_current_user(user)
    headers = auth_headers(user)
    client = TestClient(webapp.app)
    yield client, conn, user, headers
    clear_app_overrides()
    conn.close()


def _seed(conn, user_id, *, title="冷热水管走顶规范", raw_text="冷热水管走顶，弹线定位，误差≤2mm。"):
    return db.insert_card(
        conn,
        user_id,
        title=title,
        raw_text=raw_text,
        structured_json=_structured(title, raw_text),
        source_type="manual",
    )


def test_update_text_fields_and_sync_structured_json(env):
    client, conn, user, headers = env
    cid = _seed(conn, user["id"])

    resp = client.put(
        f"/api/cards/{cid}",
        json={
            "title": "瓷砖通铺排版规范",
            "raw_text": "瓷砖通铺，先做排版图。",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    card = resp.json()["card"]
    assert card["title"] == "瓷砖通铺排版规范"
    assert card["raw_text"] == "瓷砖通铺，先做排版图。"
    sj = json.loads(card["structured_json"])
    assert sj["title"] == "瓷砖通铺排版规范"
    assert sj["content"] == "瓷砖通铺，先做排版图。"


def test_update_partial_only_raw_text_keeps_other_fields(env):
    client, conn, user, headers = env
    cid = _seed(conn, user["id"])

    resp = client.put(f"/api/cards/{cid}", json={"raw_text": "更正后的文案内容。"}, headers=headers)
    assert resp.status_code == 200
    card = resp.json()["card"]
    assert card["raw_text"] == "更正后的文案内容。"
    assert card["title"] == "冷热水管走顶规范"


def test_update_does_not_call_llm(env, monkeypatch):
    client, conn, user, headers = env
    cid = _seed(conn, user["id"])

    import core.structure as structure_mod

    def _boom(*a, **k):
        raise AssertionError("编辑接口不应调用 structure_text / LLM")

    monkeypatch.setattr(structure_mod, "structure_text", _boom)
    resp = client.put(f"/api/cards/{cid}", json={"title": "新标题不调AI"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["card"]["title"] == "新标题不调AI"


def test_update_reflects_in_search(env):
    client, conn, user, headers = env
    cid = _seed(conn, user["id"], title="旧标题水管走顶")

    assert any(c["id"] == cid for c in db.search_cards(conn, "旧标题水管", user["id"]))

    resp = client.put(f"/api/cards/{cid}", json={"title": "新标题瓷砖排版"}, headers=headers)
    assert resp.status_code == 200

    assert any(c["id"] == cid for c in db.search_cards(conn, "新标题瓷砖", user["id"]))
    assert all(c["id"] != cid for c in db.search_cards(conn, "旧标题水管", user["id"]))


def test_update_missing_card_returns_404(env):
    client, _, _, headers = env
    resp = client.put("/api/cards/99999", json={"title": "x"}, headers=headers)
    assert resp.status_code == 404


def test_update_empty_body_returns_400(env):
    client, conn, user, headers = env
    cid = _seed(conn, user["id"])
    resp = client.put(f"/api/cards/{cid}", json={}, headers=headers)
    assert resp.status_code == 400


def test_update_empty_raw_text_returns_400(env):
    client, conn, user, headers = env
    cid = _seed(conn, user["id"])
    resp = client.put(f"/api/cards/{cid}", json={"raw_text": "   "}, headers=headers)
    assert resp.status_code == 400


def test_delete_card_and_search_miss(env):
    client, conn, user, headers = env
    cid = _seed(conn, user["id"], title="待删除的防水卡片")
    assert any(c["id"] == cid for c in db.search_cards(conn, "待删除的防水", user["id"]))

    resp = client.delete(f"/api/cards/{cid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    assert client.get(f"/api/cards/{cid}", headers=headers).status_code == 404
    assert all(c["id"] != cid for c in db.search_cards(conn, "待删除的防水", user["id"]))


def test_delete_missing_card_returns_404(env):
    client, _, _, headers = env
    resp = client.delete("/api/cards/99999", headers=headers)
    assert resp.status_code == 404
