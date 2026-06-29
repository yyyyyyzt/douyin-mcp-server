"""API 测试（TDD）：PUT /api/cards/{id} 编辑 + DELETE /api/cards/{id} 删除。"""

import json

import pytest
from fastapi.testclient import TestClient

import app as webapp
from core import db


def _structured(title, content):
    return json.dumps({"title": title, "content": content}, ensure_ascii=False)


@pytest.fixture()
def env(tmp_path):
    db_path = str(tmp_path / "edit.db")
    conn = db.connect(db_path)
    db.init_db(conn)

    webapp.app.dependency_overrides[webapp.get_db_path] = lambda: db_path
    client = TestClient(webapp.app)
    yield client, conn, db_path
    webapp.app.dependency_overrides.clear()
    conn.close()


def _seed(conn, *, title="冷热水管走顶规范", raw_text="冷热水管走顶，弹线定位，误差≤2mm。"):
    return db.insert_card(
        conn,
        title=title,
        raw_text=raw_text,
        structured_json=_structured(title, raw_text),
        source_type="manual",
    )


def test_update_text_fields_and_sync_structured_json(env):
    client, conn, _ = env
    cid = _seed(conn)

    resp = client.put(
        f"/api/cards/{cid}",
        json={
            "title": "瓷砖通铺排版规范",
            "raw_text": "瓷砖通铺，先做排版图。",
        },
    )
    assert resp.status_code == 200
    card = resp.json()["card"]
    assert card["title"] == "瓷砖通铺排版规范"
    assert card["raw_text"] == "瓷砖通铺，先做排版图。"
    sj = json.loads(card["structured_json"])
    assert sj["title"] == "瓷砖通铺排版规范"
    assert sj["content"] == "瓷砖通铺，先做排版图。"


def test_update_partial_only_raw_text_keeps_other_fields(env):
    client, conn, _ = env
    cid = _seed(conn)

    resp = client.put(f"/api/cards/{cid}", json={"raw_text": "更正后的文案内容。"})
    assert resp.status_code == 200
    card = resp.json()["card"]
    assert card["raw_text"] == "更正后的文案内容。"
    assert card["title"] == "冷热水管走顶规范"


def test_update_does_not_call_llm(env, monkeypatch):
    client, conn, _ = env
    cid = _seed(conn)

    import core.structure as structure_mod

    def _boom(*a, **k):
        raise AssertionError("编辑接口不应调用 structure_text / LLM")

    monkeypatch.setattr(structure_mod, "structure_text", _boom)
    resp = client.put(f"/api/cards/{cid}", json={"title": "新标题不调AI"})
    assert resp.status_code == 200
    assert resp.json()["card"]["title"] == "新标题不调AI"


def test_update_reflects_in_search(env):
    client, conn, _ = env
    cid = _seed(conn, title="旧标题水管走顶")

    assert any(c["id"] == cid for c in db.search_cards(conn, "旧标题水管"))

    resp = client.put(f"/api/cards/{cid}", json={"title": "新标题瓷砖排版"})
    assert resp.status_code == 200

    assert any(c["id"] == cid for c in db.search_cards(conn, "新标题瓷砖"))
    assert all(c["id"] != cid for c in db.search_cards(conn, "旧标题水管"))


def test_update_missing_card_returns_404(env):
    client, _, _ = env
    resp = client.put("/api/cards/99999", json={"title": "x"})
    assert resp.status_code == 404


def test_update_empty_body_returns_400(env):
    client, conn, _ = env
    cid = _seed(conn)
    resp = client.put(f"/api/cards/{cid}", json={})
    assert resp.status_code == 400


def test_update_empty_raw_text_returns_400(env):
    client, conn, _ = env
    cid = _seed(conn)
    resp = client.put(f"/api/cards/{cid}", json={"raw_text": "   "})
    assert resp.status_code == 400


def test_delete_card_and_search_miss(env):
    client, conn, _ = env
    cid = _seed(conn, title="待删除的防水卡片")
    assert any(c["id"] == cid for c in db.search_cards(conn, "待删除的防水"))

    resp = client.delete(f"/api/cards/{cid}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    assert client.get(f"/api/cards/{cid}").status_code == 404
    assert all(c["id"] != cid for c in db.search_cards(conn, "待删除的防水"))


def test_delete_missing_card_returns_404(env):
    client, _, _ = env
    resp = client.delete("/api/cards/99999")
    assert resp.status_code == 404
