"""SQLite + FTS5 知识卡片存储与检索（按 user_id 隔离）。

Schema：
- users：openid + level（提取限额用）
- knowledge_cards：content_md 为唯一正文，默认私有 is_public=0
- knowledge_fts：title + content_md（trigram）
- llm_usage：每日链接提取计数
- transcripts：转写共享缓存 (video_id, asr_model)

init_db 会对旧库做就地迁移（raw_text → content_md 等）。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any, Optional

LOCAL_WEB_OPENID = "local-web"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    openid TEXT NOT NULL UNIQUE,
    unionid TEXT,
    nickname TEXT,
    avatar_url TEXT,
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


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )
    }


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _content_md_from_legacy_row(row: sqlite3.Row) -> str:
    """从旧版 raw_text / structured_json 拼出 Markdown 正文。"""
    keys = set(row.keys())
    raw = (row["raw_text"] if "raw_text" in keys else "") or ""
    raw = str(raw).strip()
    structured = row["structured_json"] if "structured_json" in keys else None
    if not structured:
        return raw
    try:
        data = json.loads(structured) if isinstance(structured, str) else structured
    except (TypeError, json.JSONDecodeError):
        return raw
    if not isinstance(data, dict):
        return raw
    parts: list[str] = []
    summary = (data.get("summary") or "").strip()
    if summary:
        parts.append(summary)
    steps = data.get("steps") or data.get("points") or []
    if isinstance(steps, list) and steps:
        for i, step in enumerate(steps, 1):
            if isinstance(step, dict):
                text = (step.get("text") or step.get("content") or step.get("title") or "").strip()
            else:
                text = str(step).strip()
            if text:
                parts.append(f"{i}. {text}")
    body = "\n\n".join(parts).strip()
    return body or raw


def _migrate_knowledge_cards_to_content_md(conn: sqlite3.Connection) -> None:
    """将 knowledge_cards(raw_text/structured_json) 迁到 content_md，并重建 FTS。"""
    conn.executescript(
        """
        DROP TRIGGER IF EXISTS knowledge_cards_ai;
        DROP TRIGGER IF EXISTS knowledge_cards_ad;
        DROP TRIGGER IF EXISTS knowledge_cards_au;
        DROP TABLE IF EXISTS knowledge_fts;
        """
    )

    cols = _table_columns(conn, "knowledge_cards")
    old_rows = conn.execute("SELECT * FROM knowledge_cards").fetchall()

    conn.execute(
        """
        CREATE TABLE knowledge_cards_new (
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
        )
        """
    )

    for row in old_rows:
        keys = set(row.keys())
        content_md = (
            _content_md_from_legacy_row(row)
            if "raw_text" in keys or "structured_json" in keys
            else ""
        )
        is_public = int(row["is_public"]) if "is_public" in keys and row["is_public"] is not None else 0
        conn.execute(
            """
            INSERT INTO knowledge_cards_new (
                id, user_id, title, content_md, stage, source_type, source_url,
                video_id, is_public, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["user_id"],
                (row["title"] if "title" in keys and row["title"] is not None else "") or "",
                content_md or "",
                row["stage"] if "stage" in keys else None,
                (row["source_type"] if "source_type" in keys else None) or "manual",
                row["source_url"] if "source_url" in keys else None,
                row["video_id"] if "video_id" in keys else None,
                is_public,
                row["created_at"] if "created_at" in keys else None,
                row["updated_at"] if "updated_at" in keys else None,
            ),
        )

    conn.executescript(
        """
        DROP TABLE knowledge_cards;
        ALTER TABLE knowledge_cards_new RENAME TO knowledge_cards;

        CREATE VIRTUAL TABLE knowledge_fts USING fts5(
            title,
            content_md,
            content='knowledge_cards',
            content_rowid='id',
            tokenize='trigram'
        );

        CREATE TRIGGER knowledge_cards_ai AFTER INSERT ON knowledge_cards BEGIN
            INSERT INTO knowledge_fts(rowid, title, content_md)
            VALUES (new.id, new.title, new.content_md);
        END;

        CREATE TRIGGER knowledge_cards_ad AFTER DELETE ON knowledge_cards BEGIN
            INSERT INTO knowledge_fts(knowledge_fts, rowid, title, content_md)
            VALUES ('delete', old.id, old.title, old.content_md);
        END;

        CREATE TRIGGER knowledge_cards_au AFTER UPDATE ON knowledge_cards BEGIN
            INSERT INTO knowledge_fts(knowledge_fts, rowid, title, content_md)
            VALUES ('delete', old.id, old.title, old.content_md);
            INSERT INTO knowledge_fts(rowid, title, content_md)
            VALUES (new.id, new.title, new.content_md);
        END;

        INSERT INTO knowledge_fts(rowid, title, content_md)
        SELECT id, title, content_md FROM knowledge_cards;
        """
    )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """兼容生产旧库：补列、raw_text→content_md、确保 llm_usage/transcripts。"""
    tables = _table_names(conn)

    if "users" in tables:
        _ensure_column(conn, "users", "level", "level INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "users", "nickname", "nickname TEXT")
        _ensure_column(conn, "users", "avatar_url", "avatar_url TEXT")

    if "knowledge_cards" in tables:
        cols = _table_columns(conn, "knowledge_cards")
        if "content_md" not in cols:
            _migrate_knowledge_cards_to_content_md(conn)
        else:
            _ensure_column(
                conn, "knowledge_cards", "is_public", "is_public INTEGER NOT NULL DEFAULT 0"
            )

    # CREATE IF NOT EXISTS 已在 _SCHEMA；这里再确保 llm_usage 有 extract_calls
    if "llm_usage" in _table_names(conn):
        usage_cols = _table_columns(conn, "llm_usage")
        if "extract_calls" not in usage_cols:
            conn.execute(
                "ALTER TABLE llm_usage ADD COLUMN extract_calls INTEGER NOT NULL DEFAULT 0"
            )


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    _migrate_schema(conn)
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


def update_user_profile(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    nickname: Optional[str] = None,
    avatar_url: Optional[str] = None,
) -> bool:
    """更新用户昵称/头像（微信 getUserProfile 同步）。"""
    updates: dict[str, Any] = {}
    if nickname is not None:
        updates["nickname"] = (nickname or "").strip() or None
    if avatar_url is not None:
        updates["avatar_url"] = (avatar_url or "").strip() or None
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    cur = conn.execute(
        f"UPDATE users SET {set_clause} WHERE id = ?",
        list(updates.values()) + [user_id],
    )
    conn.commit()
    return cur.rowcount > 0


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
