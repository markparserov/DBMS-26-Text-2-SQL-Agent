"""
Логирование событий бэкенда в отдельную SQLite-базу.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LoggingDB:
    """Хранилище журналов для аудита работы движка и сессий."""

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
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    session_id TEXT,
                    event_type TEXT NOT NULL,
                    details_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    session_id TEXT,
                    model TEXT,
                    request_messages_json TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    tokens_used INTEGER,
                    latency_ms INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    sql_generated TEXT,
                    row_count INTEGER DEFAULT 0,
                    tools_used_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    total_messages INTEGER DEFAULT 0,
                    details_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_session ON llm_calls(session_id, id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_interactions_session ON user_interactions(session_id, id)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_log_session ON sessions_log(session_id, id)")

    def log_event(
        self,
        event_type: str,
        details: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events(ts, session_id, event_type, details_json) VALUES (?, ?, ?, ?)",
                (_utc_now(), session_id, event_type, json.dumps(details or {}, ensure_ascii=False)),
            )

    def log_llm_call(
        self,
        *,
        session_id: str | None,
        model: str | None,
        request_messages: list[dict[str, Any]],
        response_data: dict[str, Any],
        tokens_used: int | None = None,
        latency_ms: int | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls(
                    ts, session_id, model, request_messages_json, response_json, tokens_used, latency_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now(),
                    session_id,
                    model,
                    json.dumps(request_messages, ensure_ascii=False),
                    json.dumps(response_data, ensure_ascii=False),
                    tokens_used,
                    latency_ms,
                ),
            )

    def log_user_interaction(
        self,
        *,
        session_id: str,
        question: str,
        answer: str,
        sql_generated: str | None = None,
        row_count: int = 0,
        tools_used: list[str] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_interactions(
                    ts, session_id, question, answer, sql_generated, row_count, tools_used_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now(),
                    session_id,
                    question,
                    answer,
                    sql_generated or "",
                    row_count,
                    json.dumps(tools_used or [], ensure_ascii=False),
                ),
            )

    def log_session_action(
        self,
        *,
        session_id: str,
        action: str,
        total_messages: int = 0,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions_log(ts, session_id, action, total_messages, details_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    _utc_now(),
                    session_id,
                    action,
                    total_messages,
                    json.dumps(details or {}, ensure_ascii=False),
                ),
            )
