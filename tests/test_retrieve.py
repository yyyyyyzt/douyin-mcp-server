"""检索层测试：FTS 短语 + 3-gram 重叠召回 + LIKE 兜底 + grounded 判定。"""

import json

import pytest

from core import db, retrieve


def _seed(conn, user_id, stage, title, raw_text):
    return db.insert_card(
        conn,
        user_id,
        stage=stage,
        title=title,
        content_md=raw_text,
        source_type="manual",
    )


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(str(tmp_path / "r.db"))
    db.init_db(c)
    yield c
    c.close()


@pytest.fixture()
def uid(conn):
    return db.ensure_user(conn, "retrieve-user")


def test_phrase_hit(conn, uid):
    cid = _seed(conn, uid, "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米，墙面阴角加强。")
    res = retrieve.retrieve(conn, "卫生间防水", uid)
    assert any(r["id"] == cid for r in res)
    assert all("score" in r for r in res)


def test_natural_question_overlap_recall(conn, uid):
    cid = _seed(conn, uid, "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米，门口要做挡水坝。")
    _seed(conn, uid, "水电改造", "插座布局", "厨房插座要预留足够数量。")
    res = retrieve.retrieve(conn, "卫生间的防水应该刷多高才合适？", uid)
    assert res
    assert res[0]["id"] == cid


def test_short_query_like_fallback(conn, uid):
    cid = _seed(conn, uid, "泥木阶段", "瓷砖通铺", "瓷砖通铺更好看。")
    res = retrieve.retrieve(conn, "瓷砖", uid)
    assert any(r["id"] == cid for r in res)


def test_no_match_returns_empty(conn, uid):
    _seed(conn, uid, "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米。")
    assert retrieve.retrieve(conn, "今天股票走势如何", uid) == []


def test_empty_query_returns_empty(conn, uid):
    _seed(conn, uid, "防水阶段", "卫生间防水", "防水。")
    assert retrieve.retrieve(conn, "   ", uid) == []


def test_is_grounded(conn):
    assert retrieve.is_grounded([]) is False
    assert retrieve.is_grounded([{"score": 1.0}]) is True
    assert retrieve.is_grounded([{"score": 1.0}], min_score=2.0) is False
    assert retrieve.is_grounded([{"score": 3.0}], min_score=2.0) is True


def test_min_score_env(conn, monkeypatch):
    monkeypatch.setenv("CHAT_MIN_SCORE", "5.0")
    assert retrieve.get_min_score() == 5.0
    assert retrieve.is_grounded([{"score": 1.0}]) is False
