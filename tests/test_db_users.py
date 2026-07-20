"""db 层用户隔离测试：users 表、按 user_id 作用域、去重。"""

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
        content_md="冷热水管要走顶，弹线定位，误差小于2毫米，避开承重墙和电线管。",
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
    assert got["is_public"] == 0
    assert got["content_md"]


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
    db.insert_card(
        conn, ua, **_sample(title="卫生间防水高度", content_md="防水要刷到1.8米")
    )
    db.insert_card(
        conn, ub, **_sample(title="厨房插座布局", content_md="厨房插座要预留足够数量")
    )
    a_hits = db.search_cards(conn, "卫生间防水", ua)
    b_hits = db.search_cards(conn, "卫生间防水", ub)
    assert len(a_hits) >= 1
    assert b_hits == []


def test_user_has_level_default_zero(conn):
    uid = _user(conn, "level-user")
    row = db.get_user_by_id(conn, uid)
    assert row["level"] == 0


def test_extract_usage_increment_and_reset_by_day(conn):
    uid = _user(conn, "usage-user")
    assert db.get_extract_calls(conn, uid, day="2026-07-20") == 0
    assert db.increment_extract_calls(conn, uid, day="2026-07-20") == 1
    assert db.increment_extract_calls(conn, uid, day="2026-07-20") == 2
    assert db.get_extract_calls(conn, uid, day="2026-07-21") == 0


def test_transcript_cache_roundtrip(conn):
    assert db.get_transcript(conn, "vid1", "model-a") is None
    db.save_transcript(conn, "vid1", "model-a", "转写文本")
    assert db.get_transcript(conn, "vid1", "model-a") == "转写文本"
    db.save_transcript(conn, "vid1", "model-a", "更新后的转写")
    assert db.get_transcript(conn, "vid1", "model-a") == "更新后的转写"
