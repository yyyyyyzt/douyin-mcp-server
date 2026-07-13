"""SQLite + FTS5 知识卡片存储与检索（按 user_id 隔离）。

设计要点：
- users 表存微信 openid（Web 兼容用户 openid=local-web）。
- knowledge_cards 带 user_id，去重为 UNIQUE(user_id, video_id)。
- FTS5 external content + trigram 中文检索；检索 JOIN 主表并过滤 user_id。
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

LOCAL_WEB_OPENID = "local-web"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    openid TEXT NOT NULL UNIQUE,
    unionid TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_cards (
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

_LEGACY_FTS_TRIGGERS = """
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

_UPDATABLE_FIELDS = {
    "stage",
    "title",
    "raw_text",
    "structured_json",
    "source_type",
    "source_url",
    "video_id",
}


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_legacy_schema(conn: sqlite3.Connection) -> None:
    """将旧版全局 video_id UNIQUE 库迁移为按 user_id 隔离。"""
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "knowledge_cards" not in tables:
        return

    cols = _table_columns(conn, "knowledge_cards")
    if "user_id" in cols:
        return

    local_id = ensure_local_web_user(conn)
    conn.execute("ALTER TABLE knowledge_cards ADD COLUMN user_id INTEGER")
    conn.execute("UPDATE knowledge_cards SET user_id = ?", (local_id,))

    conn.executescript(
        """
        CREATE TABLE knowledge_cards_new (
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
        INSERT INTO knowledge_cards_new (
            id, user_id, stage, title, raw_text, structured_json,
            source_type, source_url, video_id, created_at, updated_at
        )
        SELECT
            id, user_id, stage, title, raw_text, structured_json,
            source_type, source_url, video_id, created_at, updated_at
        FROM knowledge_cards;
        DROP TABLE knowledge_cards;
        ALTER TABLE knowledge_cards_new RENAME TO knowledge_cards;
        """
    )

    fts_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_fts'"
    ).fetchone()
    if not fts_exists:
        conn.executescript(
            """
            CREATE VIRTUAL TABLE knowledge_fts USING fts5(
                title, raw_text,
                content='knowledge_cards', content_rowid='id',
                tokenize='trigram'
            );
            """
        )
        conn.executescript(_LEGACY_FTS_TRIGGERS)
        conn.execute(
            """
            INSERT INTO knowledge_fts(rowid, title, raw_text)
            SELECT id, title, raw_text FROM knowledge_cards
            """
        )
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    _migrate_legacy_schema(conn)
    conn.commit()


def ensure_user(conn: sqlite3.Connection, openid: str, unionid: Optional[str] = None) -> int:
    openid = (openid or "").strip()
    if not openid:
        raise ValueError("openid 不能为空")
    row = conn.execute("SELECT id FROM users WHERE openid = ?", (openid,)).fetchone()
    if row:
        if unionid:
            conn.execute(
                "UPDATE users SET unionid = ?, last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
                (unionid, row["id"]),
            )
            conn.commit()
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO users (openid, unionid, last_login_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        (openid, unionid),
    )
    conn.commit()
    return int(cur.lastrowid)


def ensure_local_web_user(conn: sqlite3.Connection) -> int:
    return ensure_user(conn, LOCAL_WEB_OPENID)


def touch_user_login(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute(
        "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?",
        (user_id,),
    )
    conn.commit()


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_openid(conn: sqlite3.Connection, openid: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM users WHERE openid = ?", (openid,)).fetchone()
    return dict(row) if row else None


def insert_card(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    stage: Optional[str] = None,
    title: Optional[str] = None,
    raw_text: str,
    structured_json: Optional[str] = None,
    source_type: str = "manual",
    source_url: Optional[str] = None,
    video_id: Optional[str] = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO knowledge_cards
            (user_id, stage, title, raw_text, structured_json, source_type, source_url, video_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, stage, title, raw_text, structured_json, source_type, source_url, video_id),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_card(conn: sqlite3.Connection, card_id: int, user_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM knowledge_cards WHERE id = ? AND user_id = ?",
        (card_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def get_card_by_video_id(
    conn: sqlite3.Connection, video_id: str, user_id: int
) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM knowledge_cards WHERE video_id = ? AND user_id = ?",
        (video_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def list_cards(
    conn: sqlite3.Connection, user_id: int, stage: Optional[str] = None
) -> list[dict]:
    if stage:
        rows = conn.execute(
            """
            SELECT * FROM knowledge_cards
            WHERE user_id = ? AND stage = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id, stage),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM knowledge_cards
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_card(conn: sqlite3.Connection, card_id: int, user_id: int, **fields: Any) -> bool:
    updates = {k: v for k, v in fields.items() if k in _UPDATABLE_FIELDS}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    set_clause += ", updated_at = CURRENT_TIMESTAMP"
    params = list(updates.values()) + [card_id, user_id]

    cur = conn.execute(
        f"UPDATE knowledge_cards SET {set_clause} WHERE id = ? AND user_id = ?",
        params,
    )
    conn.commit()
    return cur.rowcount > 0


def delete_card(conn: sqlite3.Connection, card_id: int, user_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM knowledge_cards WHERE id = ? AND user_id = ?",
        (card_id, user_id),
    )
    conn.commit()
    return cur.rowcount > 0


def search_cards(
    conn: sqlite3.Connection, query: str, user_id: int, top_k: int = 5
) -> list[dict]:
    query = (query or "").strip()
    if len(query) < 3:
        return []

    fts_query = '"' + query.replace('"', '""') + '"'
    try:
        rows = conn.execute(
            """
            SELECT c.*, bm25(knowledge_fts) AS bm25_score
            FROM knowledge_fts
            JOIN knowledge_cards c ON c.id = knowledge_fts.rowid
            WHERE knowledge_fts MATCH ? AND c.user_id = ?
            ORDER BY bm25(knowledge_fts)
            LIMIT ?
            """,
            (fts_query, user_id, top_k),
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    results = []
    for r in rows:
        item = dict(r)
        bm25 = item.pop("bm25_score", 0.0) or 0.0
        item["score"] = -bm25
        results.append(item)
    return results
