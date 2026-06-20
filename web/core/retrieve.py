"""检索层：为问答提供「召回相关卡片 + 判定是否有依据(grounded)」。

为什么不直接用 `db.search_cards`：
- `db.search_cards` 把整个查询当作一个 FTS5 短语匹配，自然语言提问（整句）几乎不会
  作为连续子串出现在卡片里，因此对话式问题常常召回为空。
- 这里在「整句短语匹配」之外，增加 **3-gram 重叠召回**（与 trigram 分词器天然契合）：
  把问题切成 3 字片段分别检索，按命中的片段数排序，实现关键词级别的重合召回；
  并对 < 3 字的超短查询用 LIKE 兜底。

grounded 判定：无任何召回，或最高分低于经验阈值 `CHAT_MIN_SCORE` → 视为「无依据」。
"""

import os
import re
import sqlite3
from typing import Optional

from core import db

DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.0  # 默认：只要有 FTS/关键词命中即视为有依据；可用 CHAT_MIN_SCORE 调高

# 去除空白与常见标点，便于切 n-gram
_CLEAN = re.compile(r"[\s，。、？！?,.!；;：:（）()\[\]【】\"'~`…—\-_/\\]+")


def get_min_score() -> float:
    try:
        return float(os.getenv("CHAT_MIN_SCORE", str(DEFAULT_MIN_SCORE)))
    except (TypeError, ValueError):
        return DEFAULT_MIN_SCORE


def _ngrams(text: str, n: int = 3) -> list[str]:
    s = _CLEAN.sub("", text)
    if len(s) < n:
        return [s] if s else []
    return list({s[i : i + n] for i in range(len(s) - n + 1)})


def _like_fallback(conn: sqlite3.Connection, query: str, top_k: int) -> list[dict]:
    like = f"%{query}%"
    rows = conn.execute(
        """
        SELECT * FROM knowledge_cards
        WHERE title LIKE ? OR raw_text LIKE ?
        ORDER BY id DESC LIMIT ?
        """,
        (like, like, top_k),
    ).fetchall()
    results = []
    for r in rows:
        item = dict(r)
        item["score"] = 1.0  # 子串命中给一个中性正分
        results.append(item)
    return results


def _overlap_search(conn: sqlite3.Connection, query: str, top_k: int) -> list[dict]:
    """3-gram 重叠召回：score = 命中的查询片段数（越多越相关）。"""
    grams = _ngrams(query, 3)
    if not grams:
        return []
    agg: dict[int, list] = {}  # card_id -> [hit_count, row_dict]
    for g in grams:
        for r in db.search_cards(conn, g, top_k=max(top_k * 4, 20)):
            cur = agg.get(r["id"])
            if cur:
                cur[0] += 1
            else:
                agg[r["id"]] = [1, r]
    ranked = sorted(agg.values(), key=lambda x: -x[0])[:top_k]
    results = []
    for hit_count, row in ranked:
        item = dict(row)
        item["score"] = float(hit_count)
        results.append(item)
    return results


def retrieve(conn: sqlite3.Connection, query: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """召回与查询最相关的若干卡片（每条带正向 score，越大越相关）。"""
    q = (query or "").strip()
    if not q:
        return []
    if len(q) < 3:
        return _like_fallback(conn, q, top_k)

    # 1) 整句短语 FTS（短关键词查询的精确路径）
    res = db.search_cards(conn, q, top_k=top_k)
    if res:
        return res
    # 2) 3-gram 重叠召回（对话式长问题的主路径）
    res = _overlap_search(conn, q, top_k)
    if res:
        return res
    # 3) 整句 LIKE 兜底
    return _like_fallback(conn, q, top_k)


def is_grounded(results: list[dict], min_score: Optional[float] = None) -> bool:
    """是否有足够依据：有召回且最高分 >= 阈值。"""
    if not results:
        return False
    if min_score is None:
        min_score = get_min_score()
    top = max((r.get("score", 0.0) or 0.0) for r in results)
    return top >= min_score
