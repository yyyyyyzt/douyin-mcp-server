"""db 层测试（TDD）：建表、CRUD、FTS5 检索、video_id 按用户去重。"""

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


@pytest.fixture()
def uid(conn):
    return db.ensure_user(conn, "test-user")


def _sample(**overrides):
    card = dict(
        stage="水电改造",
        title="冷热水管走顶规范",
        content_md="冷热水管要走顶，弹线定位，误差小于2毫米，避开承重墙和电线管。",
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
    assert "users" in names
    assert "llm_usage" in names
    assert "transcripts" in names


def test_init_db_is_idempotent(tmp_path):
    c = db.connect(str(tmp_path / "x.db"))
    db.init_db(c)
    db.init_db(c)
    c.close()


def test_insert_and_get_card(conn, uid):
    card_id = db.insert_card(conn, uid, **_sample())
    assert isinstance(card_id, int) and card_id > 0

    got = db.get_card(conn, card_id, uid)
    assert got is not None
    assert got["stage"] == "水电改造"
    assert got["title"] == "冷热水管走顶规范"
    assert "承重墙" in got["content_md"]
    assert got["created_at"]


def test_get_missing_card_returns_none(conn, uid):
    assert db.get_card(conn, 99999, uid) is None


def test_video_id_unique_per_user(conn, uid):
    db.insert_card(conn, uid, **_sample(video_id="vid-123"))
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_card(conn, uid, **_sample(video_id="vid-123"))


def test_get_card_by_video_id(conn, uid):
    db.insert_card(conn, uid, **_sample(video_id="vid-abc"))
    got = db.get_card_by_video_id(conn, "vid-abc", uid)
    assert got is not None and got["video_id"] == "vid-abc"
    assert db.get_card_by_video_id(conn, "nope", uid) is None


def test_list_cards_and_filter_by_stage(conn, uid):
    db.insert_card(conn, uid, **_sample(stage="水电改造", title="A"))
    db.insert_card(conn, uid, **_sample(stage="泥木", title="B"))
    db.insert_card(conn, uid, **_sample(stage="泥木", title="C"))

    assert len(db.list_cards(conn, uid)) == 3
    nimu = db.list_cards(conn, uid, stage="泥木")
    assert len(nimu) == 2
    assert {c["title"] for c in nimu} == {"B", "C"}


def test_update_card(conn, uid):
    card_id = db.insert_card(conn, uid, **_sample(title="旧标题"))
    ok = db.update_card(conn, card_id, uid, title="新标题", stage="防水")
    assert ok is True
    got = db.get_card(conn, card_id, uid)
    assert got["title"] == "新标题"
    assert got["stage"] == "防水"


def test_update_missing_card_returns_false(conn, uid):
    assert db.update_card(conn, 12345, uid, title="x") is False


def test_delete_card(conn, uid):
    card_id = db.insert_card(conn, uid, **_sample())
    assert db.delete_card(conn, card_id, uid) is True
    assert db.get_card(conn, card_id, uid) is None
    assert db.delete_card(conn, card_id, uid) is False


def test_fts_search_finds_card_by_chinese_keyword(conn, uid):
    db.insert_card(conn, uid, **_sample(title="冷热水管走顶规范", content_md="冷热水管走顶，避开承重墙"))
    db.insert_card(conn, uid, **_sample(title="瓷砖铺贴", content_md="瓷砖空鼓率不超过百分之五", video_id="v2"))

    results = db.search_cards(conn, "冷热水管", uid, top_k=5)
    assert len(results) >= 1
    assert results[0]["title"] == "冷热水管走顶规范"
    assert "score" in results[0]


def test_fts_search_no_match_returns_empty(conn, uid):
    db.insert_card(conn, uid, **_sample(title="冷热水管", content_md="冷热水管走顶"))
    assert db.search_cards(conn, "完全无关的查询内容xyz", uid, top_k=5) == []


def test_fts_index_updates_after_edit(conn, uid):
    card_id = db.insert_card(conn, uid, **_sample(title="原始标题", content_md="原始内容描述文字"))
    db.update_card(conn, card_id, uid, content_md="瓷砖空鼓率检测标准")
    assert db.search_cards(conn, "原始内容描述", uid, top_k=5) == []
    assert len(db.search_cards(conn, "瓷砖空鼓率", uid, top_k=5)) == 1


def test_fts_index_removed_after_delete(conn, uid):
    card_id = db.insert_card(conn, uid, **_sample(title="冷热水管", content_md="冷热水管走顶规范说明"))
    db.delete_card(conn, card_id, uid)
    assert db.search_cards(conn, "冷热水管走顶", uid, top_k=5) == []


def test_migrate_legacy_raw_text_schema(tmp_path):
    """生产旧库只有 raw_text 时，init_db 应迁到 content_md 且可插入/检索。"""
    path = str(tmp_path / "legacy.db")
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            openid TEXT NOT NULL UNIQUE,
            unionid TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login_at TIMESTAMP
        );
        CREATE TABLE knowledge_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            stage TEXT,
            title TEXT,
            raw_text TEXT NOT NULL,
            structured_json TEXT,
            source_type TEXT DEFAULT 'manual',
            source_url TEXT,
            video_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, video_id)
        );
        CREATE VIRTUAL TABLE knowledge_fts USING fts5(
            title, raw_text,
            content='knowledge_cards', content_rowid='id', tokenize='trigram'
        );
        INSERT INTO users (openid) VALUES ('legacy-user');
        INSERT INTO knowledge_cards (user_id, stage, title, raw_text, video_id)
        VALUES (1, '水电改造', '旧卡片', '冷热水管要走顶避开承重墙', 'vid-old');
        INSERT INTO knowledge_fts(rowid, title, raw_text)
        SELECT id, title, raw_text FROM knowledge_cards;
        """
    )
    c.commit()
    c.close()

    conn = db.connect(path)
    db.init_db(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_cards)")}
    assert "content_md" in cols
    assert "raw_text" not in cols
    assert "is_public" in cols
    assert "level" in {row[1] for row in conn.execute("PRAGMA table_info(users)")}

    got = db.get_card(conn, 1, 1)
    assert got is not None
    assert "承重墙" in got["content_md"]
    assert got["title"] == "旧卡片"

    hits = db.search_cards(conn, "冷热水管", 1, top_k=5)
    assert len(hits) >= 1

    new_id = db.insert_card(
        conn, 1, title="新卡", content_md="泥木基层处理要点说明文字", stage="泥木"
    )
    assert new_id > 0
    assert db.get_card(conn, new_id, 1)["content_md"].startswith("泥木")
    conn.close()


def test_migrate_adds_user_level_on_existing_db(tmp_path):
    path = str(tmp_path / "users.db")
    c = sqlite3.connect(path)
    c.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            openid TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO users (openid) VALUES ('u1');
        """
    )
    c.commit()
    c.close()

    conn = db.connect(path)
    db.init_db(conn)
    row = conn.execute("SELECT level FROM users WHERE openid='u1'").fetchone()
    assert row is not None
    assert int(row["level"]) == 0
    conn.close()
