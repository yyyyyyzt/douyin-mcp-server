"""db 层测试（TDD）：建表、CRUD、FTS5 检索、video_id 唯一。"""

import json
import sqlite3

import pytest

from core import db


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(str(tmp_path / "test.db"))
    db.init_db(c)
    yield c
    c.close()


def _sample(**overrides):
    card = dict(
        stage="水电改造",
        title="冷热水管走顶规范",
        raw_text="冷热水管要走顶，弹线定位，误差小于2毫米，避开承重墙和电线管。",
        structured_json=json.dumps({"stage": "水电改造", "title": "冷热水管走顶规范", "steps": []}, ensure_ascii=False),
        source_type="manual",
        source_url=None,
        video_id=None,
    )
    card.update(overrides)
    return card


def test_init_db_creates_tables(conn):
    names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        )
    }
    assert "knowledge_cards" in names
    assert "knowledge_fts" in names


def test_init_db_is_idempotent(tmp_path):
    c = db.connect(str(tmp_path / "x.db"))
    db.init_db(c)
    db.init_db(c)  # 再次调用不应报错
    c.close()


def test_insert_and_get_card(conn):
    card_id = db.insert_card(conn, **_sample())
    assert isinstance(card_id, int) and card_id > 0

    got = db.get_card(conn, card_id)
    assert got is not None
    assert got["stage"] == "水电改造"
    assert got["title"] == "冷热水管走顶规范"
    assert "承重墙" in got["raw_text"]
    assert got["created_at"]  # 自动填充时间戳


def test_get_missing_card_returns_none(conn):
    assert db.get_card(conn, 99999) is None


def test_video_id_unique(conn):
    db.insert_card(conn, **_sample(video_id="vid-123"))
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_card(conn, **_sample(video_id="vid-123"))


def test_get_card_by_video_id(conn):
    db.insert_card(conn, **_sample(video_id="vid-abc"))
    got = db.get_card_by_video_id(conn, "vid-abc")
    assert got is not None and got["video_id"] == "vid-abc"
    assert db.get_card_by_video_id(conn, "nope") is None


def test_list_cards_and_filter_by_stage(conn):
    db.insert_card(conn, **_sample(stage="水电改造", title="A"))
    db.insert_card(conn, **_sample(stage="泥木", title="B"))
    db.insert_card(conn, **_sample(stage="泥木", title="C"))

    assert len(db.list_cards(conn)) == 3
    nimu = db.list_cards(conn, stage="泥木")
    assert len(nimu) == 2
    assert {c["title"] for c in nimu} == {"B", "C"}


def test_update_card(conn):
    card_id = db.insert_card(conn, **_sample(title="旧标题"))
    ok = db.update_card(conn, card_id, title="新标题", stage="防水")
    assert ok is True
    got = db.get_card(conn, card_id)
    assert got["title"] == "新标题"
    assert got["stage"] == "防水"


def test_update_missing_card_returns_false(conn):
    assert db.update_card(conn, 12345, title="x") is False


def test_delete_card(conn):
    card_id = db.insert_card(conn, **_sample())
    assert db.delete_card(conn, card_id) is True
    assert db.get_card(conn, card_id) is None
    assert db.delete_card(conn, card_id) is False


def test_fts_search_finds_card_by_chinese_keyword(conn):
    db.insert_card(conn, **_sample(title="冷热水管走顶规范", raw_text="冷热水管走顶，避开承重墙"))
    db.insert_card(conn, **_sample(title="瓷砖铺贴", raw_text="瓷砖空鼓率不超过百分之五", video_id="v2"))

    results = db.search_cards(conn, "冷热水管", top_k=5)
    assert len(results) >= 1
    assert results[0]["title"] == "冷热水管走顶规范"
    assert "score" in results[0]


def test_fts_search_no_match_returns_empty(conn):
    db.insert_card(conn, **_sample(title="冷热水管", raw_text="冷热水管走顶"))
    assert db.search_cards(conn, "完全无关的查询内容xyz", top_k=5) == []


def test_fts_index_updates_after_edit(conn):
    card_id = db.insert_card(conn, **_sample(title="原始标题", raw_text="原始内容描述文字"))
    db.update_card(conn, card_id, raw_text="瓷砖空鼓率检测标准")
    # 旧关键词不再命中，新关键词可命中
    assert db.search_cards(conn, "原始内容描述", top_k=5) == []
    assert len(db.search_cards(conn, "瓷砖空鼓率", top_k=5)) == 1


def test_fts_index_removed_after_delete(conn):
    card_id = db.insert_card(conn, **_sample(title="冷热水管", raw_text="冷热水管走顶规范说明"))
    db.delete_card(conn, card_id)
    assert db.search_cards(conn, "冷热水管走顶", top_k=5) == []
