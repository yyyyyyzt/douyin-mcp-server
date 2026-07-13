"""db 层用户隔离测试（TDD）：users 表、按 user_id 作用域、迁移、去重。"""

import json
import sqlite3

import pytest

from core import db


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(str(tmp_path / "users.db"))
    db.init_db(c)
    yield c
    c.close()


def _user(conn, openid: str) -> int:
    return db.ensure_user(conn, openid)


def _sample(**overrides):
    card = dict(
        stage="水电改造",
        title="冷热水管走顶规范",
        raw_text="冷热水管要走顶，弹线定位，误差小于2毫米，避开承重墙和电线管。",
        structured_json=json.dumps(
            {"stage": "水电改造", "title": "冷热水管走顶规范", "steps": []},
            ensure_ascii=False,
        ),
        source_type="manual",
        source_url=None,
        video_id=None,
    )
    card.update(overrides)
    return card


def test_users_table_and_ensure_user(conn):
    uid = _user(conn, "openid-a")
    assert uid > 0
    row = db.get_user_by_openid(conn, "openid-a")
    assert row is not None
    assert row["openid"] == "openid-a"
    # 幂等
    assert db.ensure_user(conn, "openid-a") == uid


def test_ensure_local_web_user(conn):
    uid = db.ensure_local_web_user(conn)
    row = db.get_user_by_openid(conn, db.LOCAL_WEB_OPENID)
    assert row["id"] == uid


def test_insert_requires_user_id(conn):
    uid = _user(conn, "u1")
    card_id = db.insert_card(conn, uid, **_sample())
    got = db.get_card(conn, card_id, uid)
    assert got is not None
    assert got["user_id"] == uid


def test_users_cannot_see_each_others_cards(conn):
    ua = _user(conn, "user-a")
    ub = _user(conn, "user-b")
    cid = db.insert_card(conn, ua, **_sample(title="A 的卡片"))
    assert db.get_card(conn, cid, ua) is not None
    assert db.get_card(conn, cid, ub) is None
    assert len(db.list_cards(conn, ua)) == 1
    assert len(db.list_cards(conn, ub)) == 0


def test_video_id_unique_per_user_not_globally(conn):
    ua = _user(conn, "user-a")
    ub = _user(conn, "user-b")
    db.insert_card(conn, ua, **_sample(video_id="vid-shared"))
    db.insert_card(conn, ub, **_sample(video_id="vid-shared"))
    assert db.get_card_by_video_id(conn, "vid-shared", ua) is not None
    assert db.get_card_by_video_id(conn, "vid-shared", ub) is not None


def test_video_id_duplicate_same_user_raises(conn):
    uid = _user(conn, "user-a")
    db.insert_card(conn, uid, **_sample(video_id="vid-dup"))
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_card(conn, uid, **_sample(video_id="vid-dup"))


def test_update_delete_scoped_to_user(conn):
    ua = _user(conn, "user-a")
    ub = _user(conn, "user-b")
    cid = db.insert_card(conn, ua, **_sample(title="原标题"))
    assert db.update_card(conn, cid, ub, title="黑客改") is False
    assert db.get_card(conn, cid, ua)["title"] == "原标题"
    assert db.delete_card(conn, cid, ub) is False
    assert db.delete_card(conn, cid, ua) is True


def test_search_cards_scoped_by_user(conn):
    ua = _user(conn, "user-a")
    ub = _user(conn, "user-b")
    db.insert_card(conn, ua, **_sample(title="卫生间防水高度", raw_text="防水要刷到1.8米"))
    db.insert_card(conn, ub, **_sample(title="厨房插座布局", raw_text="厨房插座要预留足够数量"))
    a_hits = db.search_cards(conn, "卫生间防水", ua)
    b_hits = db.search_cards(conn, "卫生间防水", ub)
    assert len(a_hits) >= 1
    assert b_hits == []


def test_migrate_legacy_db_without_user_id(tmp_path):
    """模拟旧库：无 users / user_id，迁移后数据归属 local-web。"""
    path = str(tmp_path / "legacy.db")
    c = db.connect(path)
    c.executescript(
        """
        CREATE TABLE knowledge_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage TEXT,
            title TEXT,
            raw_text TEXT NOT NULL,
            structured_json TEXT,
            source_type TEXT DEFAULT 'manual',
            source_url TEXT,
            video_id TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE VIRTUAL TABLE knowledge_fts USING fts5(
            title, raw_text,
            content='knowledge_cards', content_rowid='id',
            tokenize='trigram'
        );
        CREATE TRIGGER knowledge_cards_ai AFTER INSERT ON knowledge_cards BEGIN
            INSERT INTO knowledge_fts(rowid, title, raw_text)
            VALUES (new.id, new.title, new.raw_text);
        END;
        """
    )
    c.execute(
        "INSERT INTO knowledge_cards (title, raw_text) VALUES (?, ?)",
        ("旧数据标题", "旧数据正文内容"),
    )
    c.commit()
    c.close()

    c2 = db.connect(path)
    db.init_db(c2)
    local_id = db.ensure_local_web_user(c2)
    rows = c2.execute("SELECT id, user_id, title FROM knowledge_cards").fetchall()
    assert len(rows) == 1
    assert rows[0]["user_id"] == local_id
    assert rows[0]["title"] == "旧数据标题"
    got = db.get_card(c2, rows[0]["id"], local_id)
    assert got is not None
    c2.close()
