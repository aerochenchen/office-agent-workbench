from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from office_agent.paths import app_data_dir

DEFAULT_TITLE = "新对话"
TITLE_MAX_LEN = 24


def _now() -> float:
    return time.time()


def title_from_user_text(text: str) -> str:
    """Derive a short session title from the first user message."""
    line = (text or "").strip().splitlines()[0] if text else ""
    # Drop attachment footer injected by agent_loop
    if "用户附带的文件路径" in line:
        line = line.split("用户附带的文件路径")[0].strip()
    line = line.strip() or DEFAULT_TITLE
    if len(line) > TITLE_MAX_LEN:
        return line[: TITLE_MAX_LEN - 1] + "…"
    return line


def history_to_ui_messages(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Flatten stored agent messages into simple user/assistant bubbles for the UI."""
    out: list[dict[str, str]] = []
    for msg in history:
        role = msg.get("role")
        content = msg.get("content")
        if role == "user" and isinstance(content, str) and content.strip():
            text = content
            marker = "\n\n用户附带的文件路径："
            if marker in text:
                text = text.split(marker, 1)[0].strip()
            out.append({"role": "user", "content": text})
        elif role == "assistant" and isinstance(content, str) and content.strip():
            # Skip pure tool-call turns that only carry tool_calls with empty content
            if msg.get("tool_calls") and not content.strip():
                continue
            out.append({"role": "assistant", "content": content.strip()})
    return out


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
            cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
            if "title" not in cols:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN title TEXT NOT NULL DEFAULT '新对话'"
                )
            if "updated_at" not in cols:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN updated_at REAL NOT NULL DEFAULT 0"
                )
                conn.execute(
                    "UPDATE sessions SET updated_at = created_at WHERE updated_at = 0 OR updated_at IS NULL"
                )

    def _row_to_meta(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "workspace_path": row["workspace_path"],
            "title": row["title"] if "title" in row.keys() else DEFAULT_TITLE,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"] if "updated_at" in row.keys() else row["created_at"],
        }

    def create_session(self, workspace_path: str = "", title: str = DEFAULT_TITLE) -> str:
        sid = str(uuid.uuid4())
        ts = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, workspace_path, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (sid, workspace_path, title or DEFAULT_TITLE, ts, ts),
            )
        return sid

    def session_exists(self, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return row is not None

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, workspace_path, title, created_at, updated_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        return self._row_to_meta(row) if row else None

    def list_sessions(self, workspace_path: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, workspace_path, title, created_at, updated_at FROM sessions "
                "WHERE workspace_path = ? ORDER BY updated_at DESC, created_at DESC",
                (workspace_path,),
            ).fetchall()
        return [self._row_to_meta(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            _ = cur.rowcount
            cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return cur.rowcount > 0

    def set_title(self, session_id: str, title: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (title or DEFAULT_TITLE, _now(), session_id),
            )

    def touch(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (_now(), session_id),
            )

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

            row = conn.execute(
                "SELECT title FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            title = row["title"] if row else DEFAULT_TITLE
            if title == DEFAULT_TITLE:
                for msg in messages:
                    if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                        new_title = title_from_user_text(str(msg["content"]))
                        conn.execute(
                            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                            (new_title, _now(), session_id),
                        )
                        break
                else:
                    conn.execute(
                        "UPDATE sessions SET updated_at = ? WHERE id = ?",
                        (_now(), session_id),
                    )
            else:
                conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE id = ?",
                    (_now(), session_id),
                )

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM messages WHERE session_id = ? ORDER BY seq",
                (session_id,),
            ).fetchall()
        return [json.loads(r["payload"]) for r in rows]
