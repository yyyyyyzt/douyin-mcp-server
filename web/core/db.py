"""SQLite + FTS5 知识卡片存储与检索（按 user_id 隔离）。

Schema（无历史迁移）：
- users：openid + level（提取限额用）
- knowledge_cards：content_md 为唯一正文，默认私有 is_public=0
- knowledge_fts：title + content_md（trigram）
- llm_usage：每日链接提取计数
- transcripts：转写共享缓存 (video_id, asr_model)
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Optional

LOCAL_WEB_OPENID = "local-web"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    openid TEXT NOT NULL UNIQUE,
    unionid TEXT,
    level INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL DEFAULT '',
    content_md TEXT NOT NULL,
    stage TEXT,
    source_type TEXT DEFAULT 'manual',
    source_url TEXT,
    video_id TEXT,
    is_public INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, video_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    title,
    content_md,
    content='knowledge_cards',
    content_rowid='id',
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS knowledge_cards_ai AFTER INSERT ON knowledge_cards BEGIN
    INSERT INTO knowledge_fts(rowid, title, content_md)
    VALUES (new.id, new.title, new.content_md);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_cards_ad AFTER DELETE ON knowledge_cards BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, title, content_md)
    VALUES ('delete', old.id, old.title, old.content_md);
END;

CREATE TRIGGER IF NOT EXISTS knowledge_cards_au AFTER UPDATE ON knowledge_cards BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, title, content_md)
    VALUES ('delete', old.id, old.title, old.content_md);
    INSERT INTO knowledge_fts(rowid, title, content_md)
    VALUES (new.id, new.title, new.content_md);
END;

CREATE TABLE IF NOT EXISTS llm_usage (
    user_id INTEGER NOT NULL REFERENCES users(id),
    day TEXT NOT NULL,
    extract_calls INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS transcripts (
    video_id TEXT NOT NULL,
    asr_model TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (video_id, asr_model)
);
"""

_UPDATABLE_FIELDS = {
    "title",
    "content_md",
    "stage",
    "source_type",
    "source_url",
    "video_id",
    "is_public",
}


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
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
    title: str = "",
    content_md: str,
    stage: Optional[str] = None,
    source_type: str = "manual",
    source_url: Optional[str] = None,
    video_id: Optional[str] = None,
    is_public: int = 0,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO knowledge_cards
            (user_id, title, content_md, stage, source_type, source_url, video_id, is_public)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            title or "",
            content_md,
            stage,
            source_type,
            source_url,
            video_id,
            int(is_public),
        ),
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


# ---------- 链接提取限额 ----------

def get_extract_calls(conn: sqlite3.Connection, user_id: int, day: Optional[str] = None) -> int:
    day = day or date.today().isoformat()
    row = conn.execute(
        "SELECT extract_calls FROM llm_usage WHERE user_id = ? AND day = ?",
        (user_id, day),
    ).fetchone()
    return int(row["extract_calls"]) if row else 0


def increment_extract_calls(
    conn: sqlite3.Connection, user_id: int, day: Optional[str] = None
) -> int:
    day = day or date.today().isoformat()
    conn.execute(
        """
        INSERT INTO llm_usage (user_id, day, extract_calls) VALUES (?, ?, 1)
        ON CONFLICT(user_id, day) DO UPDATE SET
            extract_calls = extract_calls + 1
        """,
        (user_id, day),
    )
    conn.commit()
    return get_extract_calls(conn, user_id, day)


# ---------- 转写共享缓存 ----------

def get_transcript(
    conn: sqlite3.Connection, video_id: str, asr_model: str
) -> Optional[str]:
    row = conn.execute(
        "SELECT text FROM transcripts WHERE video_id = ? AND asr_model = ?",
        (video_id, asr_model),
    ).fetchone()
    return row["text"] if row else None


def save_transcript(
    conn: sqlite3.Connection, video_id: str, asr_model: str, text: str
) -> None:
    conn.execute(
        """
        INSERT INTO transcripts (video_id, asr_model, text) VALUES (?, ?, ?)
        ON CONFLICT(video_id, asr_model) DO UPDATE SET
            text = excluded.text,
            created_at = CURRENT_TIMESTAMP
        """,
        (video_id, asr_model, text),
    )
    conn.commit()
