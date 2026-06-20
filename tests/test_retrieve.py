"""检索层测试：FTS 短语 + 3-gram 重叠召回 + LIKE 兜底 + grounded 判定。"""

import json

import pytest

from core import db, retrieve


def _seed(conn, stage, title, raw_text):
    return db.insert_card(
        conn,
        stage=stage,
        title=title,
        raw_text=raw_text,
        structured_json=json.dumps({"stage": stage, "title": title, "steps": []}, ensure_ascii=False),
        source_type="manual",
    )


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(str(tmp_path / "r.db"))
    db.init_db(c)
    yield c
    c.close()


def test_phrase_hit(conn):
    cid = _seed(conn, "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米，墙面阴角加强。")
    res = retrieve.retrieve(conn, "卫生间防水")
    assert any(r["id"] == cid for r in res)
    assert all("score" in r for r in res)


def test_natural_question_overlap_recall(conn):
    """整句问题无法短语命中，但 3-gram 重叠应召回相关卡片。"""
    cid = _seed(conn, "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米，门口要做挡水坝。")
    _seed(conn, "水电改造", "插座布局", "厨房插座要预留足够数量。")
    res = retrieve.retrieve(conn, "卫生间的防水应该刷多高才合适？")
    assert res, "应通过 3-gram 重叠召回到卫生间防水卡片"
    assert res[0]["id"] == cid  # 重叠最多的排在最前


def test_short_query_like_fallback(conn):
    cid = _seed(conn, "泥木阶段", "瓷砖通铺", "瓷砖通铺更好看。")
    res = retrieve.retrieve(conn, "瓷砖")  # 2 字，FTS trigram 不召回，走 LIKE
    assert any(r["id"] == cid for r in res)


def test_no_match_returns_empty(conn):
    _seed(conn, "防水阶段", "卫生间防水高度", "卫生间防水要刷到1.8米。")
    assert retrieve.retrieve(conn, "今天股票走势如何") == []


def test_empty_query_returns_empty(conn):
    _seed(conn, "防水阶段", "卫生间防水", "防水。")
    assert retrieve.retrieve(conn, "   ") == []


def test_is_grounded(conn):
    assert retrieve.is_grounded([]) is False
    assert retrieve.is_grounded([{"score": 1.0}]) is True
    # 阈值过滤：最高分低于阈值视为无依据
    assert retrieve.is_grounded([{"score": 1.0}], min_score=2.0) is False
    assert retrieve.is_grounded([{"score": 3.0}], min_score=2.0) is True


def test_min_score_env(conn, monkeypatch):
    monkeypatch.setenv("CHAT_MIN_SCORE", "5.0")
    assert retrieve.get_min_score() == 5.0
    assert retrieve.is_grounded([{"score": 1.0}]) is False
