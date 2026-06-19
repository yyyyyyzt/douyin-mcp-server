"""SQLite + FTS5 知识卡片存储与检索。

设计要点：
- 一张主表 knowledge_cards 存原文与结构化 JSON。
- 一个外部内容（external content）FTS5 虚拟表 knowledge_fts，使用 trigram 分词器
  以支持中文子串检索（SQLite >= 3.34）。
- 通过触发器保持 FTS 索引与主表同步。
- bm25() 分数越小越相关，search_cards 已转为「越大越相关」的正向分值，便于上层设阈值。
"""

import sqlite3
from typing import Any, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_cards (
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

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    title,
    raw_text,
    content='knowledge_cards',
    content_rowid='id',
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS knowledge_cards_ai AFTER INSERT ON knowledge_cards BEGIN
    INSERT INTO knowledge_fts(rowid, title, raw_text)
    VALUES (new.id, new.title, new.raw_text);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_cards_ad AFTER DELETE ON knowledge_cards BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, title, raw_text)
    VALUES ('delete', old.id, old.title, old.raw_text);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_cards_au AFTER UPDATE ON knowledge_cards BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, title, raw_text)
    VALUES ('delete', old.id, old.title, old.raw_text);
    INSERT INTO knowledge_fts(rowid, title, raw_text)
    VALUES (new.id, new.title, new.raw_text);
END;
"""

# 允许更新的字段白名单，避免 SQL 注入与误写系统字段
_UPDATABLE_FIELDS = {"stage", "title", "raw_text", "structured_json", "source_type", "source_url", "video_id"}


def connect(db_path: str) -> sqlite3.Connection:
    """创建连接，返回行可按列名访问的连接对象。"""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """建表 / 索引 / 触发器（幂等）。"""
    conn.executescript(_SCHEMA)
    conn.commit()


def insert_card(
    conn: sqlite3.Connection,
    *,
    stage: Optional[str] = None,
    title: Optional[str] = None,
    raw_text: str,
    structured_json: Optional[str] = None,
    source_type: str = "manual",
    source_url: Optional[str] = None,
    video_id: Optional[str] = None,
) -> int:
    """插入一张卡片，返回新行 id。video_id 唯一冲突会抛 IntegrityError。"""
    cur = conn.execute(
        """
        INSERT INTO knowledge_cards
            (stage, title, raw_text, structured_json, source_type, source_url, video_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (stage, title, raw_text, structured_json, source_type, source_url, video_id),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_card(conn: sqlite3.Connection, card_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM knowledge_cards WHERE id = ?", (card_id,)).fetchone()
    return dict(row) if row else None


def get_card_by_video_id(conn: sqlite3.Connection, video_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM knowledge_cards WHERE video_id = ?", (video_id,)
    ).fetchone()
    return dict(row) if row else None


def list_cards(conn: sqlite3.Connection, stage: Optional[str] = None) -> list[dict]:
    if stage:
        rows = conn.execute(
            "SELECT * FROM knowledge_cards WHERE stage = ? ORDER BY created_at DESC, id DESC",
            (stage,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM knowledge_cards ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def update_card(conn: sqlite3.Connection, card_id: int, **fields: Any) -> bool:
    """按字段更新卡片；自动刷新 updated_at。返回是否有行被更新。"""
    updates = {k: v for k, v in fields.items() if k in _UPDATABLE_FIELDS}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    set_clause += ", updated_at = CURRENT_TIMESTAMP"
    params = list(updates.values()) + [card_id]

    cur = conn.execute(
        f"UPDATE knowledge_cards SET {set_clause} WHERE id = ?", params
    )
    conn.commit()
    return cur.rowcount > 0


def delete_card(conn: sqlite3.Connection, card_id: int) -> bool:
    cur = conn.execute("DELETE FROM knowledge_cards WHERE id = ?", (card_id,))
    conn.commit()
    return cur.rowcount > 0


def search_cards(conn: sqlite3.Connection, query: str, top_k: int = 5) -> list[dict]:
    """FTS5 全文检索，返回带 score 的卡片（score 越大越相关）。

    trigram 分词器要求查询长度 >= 3 个字符才能命中；过短或无命中返回空列表。
    """
    query = (query or "").strip()
    if len(query) < 3:
        return []

    # 用双引号包裹为短语查询，避免特殊字符触发 FTS 语法错误
    fts_query = '"' + query.replace('"', '""') + '"'
    try:
        rows = conn.execute(
            """
            SELECT c.*, bm25(knowledge_fts) AS bm25_score
            FROM knowledge_fts
            JOIN knowledge_cards c ON c.id = knowledge_fts.rowid
            WHERE knowledge_fts MATCH ?
            ORDER BY bm25(knowledge_fts)
            LIMIT ?
            """,
            (fts_query, top_k),
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    results = []
    for r in rows:
        item = dict(r)
        bm25 = item.pop("bm25_score", 0.0) or 0.0
        # bm25 越小越相关，转为正向分值方便上层比较与设阈值
        item["score"] = -bm25
        results.append(item)
    return results
