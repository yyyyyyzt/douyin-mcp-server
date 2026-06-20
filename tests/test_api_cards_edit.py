"""API 测试（TDD）：PUT /api/cards/{id} 编辑 + DELETE /api/cards/{id} 删除。

编辑只改文本字段（stage/title/raw_text/steps），不重新调 AI，但同步重写
structured_json；并验证 FTS 检索随编辑/删除自动更新（触发器同步）。
"""

import json

import pytest
from fastapi.testclient import TestClient

import app as webapp
from core import db


def _structured(stage, title, steps):
    return json.dumps({"stage": stage, "title": title, "steps": steps}, ensure_ascii=False)


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


def _seed(conn, *, stage="水电改造", title="冷热水管走顶规范", raw_text="冷热水管走顶，弹线定位，误差≤2mm。",
          steps=None):
    steps = steps if steps is not None else [
        {"order": 1, "action": "弹线定位", "detail": "用水平仪", "standard": "误差≤2mm", "warning": "避开承重墙"}
    ]
    return db.insert_card(
        conn,
        stage=stage,
        title=title,
        raw_text=raw_text,
        structured_json=_structured(stage, title, steps),
        source_type="manual",
    )


def test_update_text_fields_and_sync_structured_json(env):
    client, conn, _ = env
    cid = _seed(conn)

    resp = client.put(
        f"/api/cards/{cid}",
        json={
            "stage": "泥木阶段",
            "title": "瓷砖通铺排版规范",
            "raw_text": "瓷砖通铺，先做排版图。",
            "steps": [
                {"order": 1, "action": "做排版图", "detail": "藏小砖", "standard": "中间露整砖", "warning": "贴前找平"}
            ],
        },
    )
    assert resp.status_code == 200
    card = resp.json()["card"]
    assert card["stage"] == "泥木阶段"
    assert card["title"] == "瓷砖通铺排版规范"
    assert card["raw_text"] == "瓷砖通铺，先做排版图。"
    # structured_json 同步重写，steps 已更新
    assert card["steps"][0]["action"] == "做排版图"
    sj = json.loads(card["structured_json"])
    assert sj["title"] == "瓷砖通铺排版规范"
    assert sj["stage"] == "泥木阶段"
    assert sj["steps"][0]["standard"] == "中间露整砖"


def test_update_partial_only_raw_text_keeps_other_fields(env):
    client, conn, _ = env
    cid = _seed(conn)

    resp = client.put(f"/api/cards/{cid}", json={"raw_text": "更正后的文案内容。"})
    assert resp.status_code == 200
    card = resp.json()["card"]
    assert card["raw_text"] == "更正后的文案内容。"
    # 未提供的字段保持不变
    assert card["title"] == "冷热水管走顶规范"
    assert card["stage"] == "水电改造"
    assert card["steps"][0]["action"] == "弹线定位"


def test_update_does_not_call_llm(env, monkeypatch):
    """编辑不应触发任何 LLM 调用。"""
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

    # 编辑前：旧标题可被检索命中
    assert any(c["id"] == cid for c in db.search_cards(conn, "旧标题水管"))

    resp = client.put(f"/api/cards/{cid}", json={"title": "新标题瓷砖排版"})
    assert resp.status_code == 200

    # 编辑后：新标题命中，旧标题不再命中（FTS 触发器同步）
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

    # 详情 404，检索不再命中
    assert client.get(f"/api/cards/{cid}").status_code == 404
    assert all(c["id"] != cid for c in db.search_cards(conn, "待删除的防水"))


def test_delete_missing_card_returns_404(env):
    client, _, _ = env
    resp = client.delete("/api/cards/99999")
    assert resp.status_code == 404
