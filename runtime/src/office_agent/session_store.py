from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from office_agent.paths import app_data_dir


class SessionStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (app_data_dir() / "db" / "sessions.sqlite")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    workspace_path TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL DEFAULT (unixepoch('subsec'))
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session
                    ON messages(session_id, seq);
                """
            )

    def create_session(self, workspace_path: str = "") -> str:
        sid = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, workspace_path) VALUES (?, ?)",
                (sid, workspace_path),
            )
        return sid

    def session_exists(self, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return row is not None

    def append_messages(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        if not messages:
            return
        with self._connect() as conn:
            start = conn.execute(
                "SELECT COALESCE(MAX(seq), -1) FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            seq = int(start) + 1
            for msg in messages:
                conn.execute(
                    "INSERT INTO messages (session_id, seq, payload) VALUES (?, ?, ?)",
                    (session_id, seq, json.dumps(msg, ensure_ascii=False)),
                )
                seq += 1

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM messages WHERE session_id = ? ORDER BY seq",
                (session_id,),
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]
