from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from office_agent.agent_loop import (
    _ask_user_text,
    _ensure_plan_html_link_in_ask,
    _parse_tool_args,
    result_summary,
    tool_label,
)
from office_agent.paths import app_data_dir

DEFAULT_TITLE = "新对话"
TITLE_MAX_LEN = 24
_UNTRUSTED_CLOSE = "</untrusted_workspace_data>"


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


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _strip_user_attachments(text: str) -> str:
    marker = "\n\n用户附带的文件路径："
    if marker in text:
        return text.split(marker, 1)[0].strip()
    return text.strip()


def _tool_result_dict(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if text.startswith("<untrusted_workspace_data"):
        start = text.find(">")
        end = text.rfind(_UNTRUSTED_CLOSE)
        if start >= 0 and end > start:
            inner = text[start + 1 : end].strip()
            brace = inner.find("{")
            if brace >= 0:
                text = inner[brace:]
    if text in {"cancelled", "onboarding: tools unavailable"}:
        return {"ok": False, "error": text}
    try:
        parsed = json.loads(text) if text else {}
    except json.JSONDecodeError:
        return {"ok": True}
    return parsed if isinstance(parsed, dict) else {"ok": True}


def _tool_call_name_args(tc: Any) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(tc, dict):
        return "", "", {}
    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
    name = str(fn.get("name") or tc.get("name") or "")
    raw_args = fn.get("arguments") if fn else tc.get("arguments")
    if isinstance(raw_args, dict):
        args = raw_args
    else:
        args = _parse_tool_args(str(raw_args or ""))
    return str(tc.get("id") or ""), name, args


def _turn_to_assistant_bubble(turn: list[dict[str, Any]]) -> dict[str, Any] | None:
    results: dict[str, dict[str, Any]] = {}
    for msg in turn:
        if msg.get("role") != "tool":
            continue
        tc_id = str(msg.get("tool_call_id") or "")
        if tc_id:
            results[tc_id] = _tool_result_dict(msg.get("content"))

    live_steps: list[dict[str, Any]] = []
    tool_events: list[dict[str, Any]] = []
    ask_text = ""
    finish_text = ""
    final_text = ""

    for msg in turn:
        if msg.get("role") != "assistant":
            continue
        text = _message_text(msg.get("content")).strip()
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            if text:
                final_text = text
            continue
        for tc in tool_calls:
            tc_id, name, args = _tool_call_name_args(tc)
            if not name:
                continue
            result = results.get(tc_id, {"ok": True})
            ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
            live_steps.append(
                {
                    "id": tc_id or f"step{len(live_steps) + 1}",
                    "name": name,
                    "label": tool_label(name),
                    "status": "ok" if ok else "fail",
                    "summary": result_summary(name, result),
                }
            )
            event = {"name": name, "args": args, "result": result}
            tool_events.append(event)
            if name == "ask_user":
                ask_text = _ask_user_text(args, result)
            elif name == "finish" and ok:
                finish_text = str(result.get("summary") or args.get("summary") or "").strip()

    if ask_text:
        ask_text = _ensure_plan_html_link_in_ask(ask_text, tool_events)
    content = final_text or ask_text or finish_text
    if not content:
        return None
    bubble: dict[str, Any] = {"role": "assistant", "content": content}
    if live_steps:
        bubble["live_steps"] = live_steps
    return bubble


def history_to_ui_messages(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rebuild the live chat bubbles: one user + one final assistant per turn."""
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(history):
        msg = history[i]
        if msg.get("role") != "user":
            i += 1
            continue
        user_text = _strip_user_attachments(_message_text(msg.get("content")))
        i += 1
        turn: list[dict[str, Any]] = []
        while i < len(history) and history[i].get("role") != "user":
            turn.append(history[i])
            i += 1
        if user_text:
            out.append({"role": "user", "content": user_text})
        bubble = _turn_to_assistant_bubble(turn)
        if bubble:
            out.append(bubble)
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
