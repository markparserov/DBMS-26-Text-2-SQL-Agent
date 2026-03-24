"""
Менеджер пользовательских сессий и истории диалога.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionManager:
    """SQLite-backed хранилище сессий и сообщений чата."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    last_active TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    visible_to_user INTEGER NOT NULL DEFAULT 1,
                    tool_name TEXT,
                    meta_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id, id)"
            )

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        ts = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions(session_id, created_at, last_active) VALUES (?, ?, ?)",
                (session_id, ts, ts),
            )
        return session_id

    def ensure_session(self, session_id: str | None) -> str:
        if not session_id:
            return self.create_session()
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if exists:
                self.touch_session(session_id)
                return session_id
        return self.create_session()

    def touch_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET last_active = ? WHERE session_id = ?",
                (_utc_now(), session_id),
            )

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        visible_to_user: bool = True,
        tool_name: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.ensure_session(session_id)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages(session_id, role, content, visible_to_user, tool_name, meta_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    1 if visible_to_user else 0,
                    tool_name,
                    json.dumps(meta or {}, ensure_ascii=False),
                    _utc_now(),
                ),
            )
            conn.execute(
                "UPDATE sessions SET last_active = ? WHERE session_id = ?",
                (_utc_now(), session_id),
            )

    def get_history(
        self,
        session_id: str,
        *,
        include_hidden: bool = True,
        max_messages: int | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT role, content, visible_to_user, tool_name, meta_json, created_at
            FROM messages
            WHERE session_id = ?
        """
        params: list[Any] = [session_id]
        if not include_hidden:
            query += " AND visible_to_user = 1"
        query += " ORDER BY id ASC"
        if max_messages and max_messages > 0:
            query += " LIMIT ?"
            params.append(max_messages)

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        history: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["visible_to_user"] = bool(item.get("visible_to_user", 1))
            try:
                item["meta"] = json.loads(item.get("meta_json") or "{}")
            except json.JSONDecodeError:
                item["meta"] = {}
            item.pop("meta_json", None)
            history.append(item)
        return history

    def clear_session(self, session_id: str) -> int:
        with self._connect() as conn:
            deleted = conn.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (session_id,),
            ).rowcount
            conn.execute(
                "UPDATE sessions SET last_active = ? WHERE session_id = ?",
                (_utc_now(), session_id),
            )
        return int(deleted or 0)

    def count_messages(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def cleanup_expired(self, max_age_hours: int = 24) -> int:
        threshold = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        with self._connect() as conn:
            session_ids = conn.execute(
                "SELECT session_id FROM sessions WHERE last_active < ?",
                (threshold,),
            ).fetchall()
            if not session_ids:
                return 0
            ids = [row["session_id"] for row in session_ids]
            conn.executemany("DELETE FROM messages WHERE session_id = ?", [(sid,) for sid in ids])
            conn.executemany("DELETE FROM sessions WHERE session_id = ?", [(sid,) for sid in ids])
        return len(ids)
