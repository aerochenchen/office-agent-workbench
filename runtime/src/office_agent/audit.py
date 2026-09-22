from __future__ import annotations

import getpass
import hashlib
import json
import sqlite3
import time
from pathlib import Path

from office_agent.paths import instance_id


# 工具参数中的这些字段视为敏感内容：审计落库时只保留长度，不存明文，
# 避免审计库本身成为敏感数据池（如 workspace_write 的 content 含公文全文）。
_SENSITIVE_ARG_FIELDS = frozenset({"content", "api_key", "key", "token", "password", "passwd"})

_NEW_COLS = [
    ("event_type", "TEXT"),
    ("session_id", "TEXT"),
    ("actor", "TEXT"),
    ("instance_id", "TEXT"),
    ("outcome", "TEXT"),
    ("error_code", "TEXT"),
    ("attrs_json", "TEXT"),
    ("prev_hash", "TEXT"),
]


def workspace_hash(path: Path | str) -> str:
    return hashlib.sha256(
        str(Path(path).expanduser().resolve()).encode("utf-8")
    ).hexdigest()


def _actor() -> str:
    try:
        return getpass.getuser() or "unknown"
    except Exception:
        return "unknown"


def _redact_args(args: dict) -> dict:
    """对敏感字段脱敏：content 类只记长度；凭据类完全遮罩。"""
    if not isinstance(args, dict):
        return args
    safe: dict = {}
    for k, v in args.items():
        if k not in _SENSITIVE_ARG_FIELDS:
            safe[k] = v
            continue
        if k == "content" and isinstance(v, str):
            safe[k] = f"<redacted len={len(v)}>"
        else:
            safe[k] = "<redacted>"
    return safe


def _redact_attrs(attrs: dict | None) -> dict | None:
    if not isinstance(attrs, dict):
        return attrs
    safe = {k: v for k, v in attrs.items() if k not in _SENSITIVE_ARG_FIELDS}
    if "api_base" in safe:
        from office_agent.deployment import model_host_from_api_base

        val = safe["api_base"]
        if isinstance(val, dict):
            safe["api_base"] = {
                k: model_host_from_api_base(str(v)) if isinstance(v, str) else v
                for k, v in val.items()
            }
        else:
            safe["api_base"] = model_host_from_api_base(str(val))
    return safe


class AuditLog:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit (
                    ts REAL,
                    tool TEXT,
                    args_json TEXT,
                    ok INTEGER,
                    detail TEXT
                )
                """
            )
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(audit)").fetchall()
            }
            if "turn_id" not in cols:
                conn.execute("ALTER TABLE audit ADD COLUMN turn_id TEXT")
            for name, col_type in _NEW_COLS:
                if name not in cols:
                    conn.execute(f"ALTER TABLE audit ADD COLUMN {name} {col_type}")

    def record(
        self,
        tool: str,
        args: dict,
        ok: bool,
        detail: str = "",
        *,
        turn_id: str | None = None,
        session_id: str | None = None,
        error_code: str | None = None,
    ) -> None:
        self.record_event(
            "tool_invoked",
            outcome="ok" if ok else "error",
            turn_id=turn_id,
            session_id=session_id,
            tool=tool,
            args=args,
            detail=detail,
            error_code=error_code,
        )

    def record_event(
        self,
        event_type: str,
        *,
        outcome: str = "ok",
        turn_id: str | None = None,
        session_id: str | None = None,
        tool: str | None = None,
        args: dict | None = None,
        detail: str = "",
        error_code: str | None = None,
        attrs: dict | None = None,
    ) -> None:
        safe_args = _redact_args(args) if args is not None else None
        safe_attrs = _redact_attrs(attrs)
        truncated = (detail or "")[:500]
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO audit (
                        ts, tool, args_json, ok, detail, turn_id,
                        event_type, session_id, actor, instance_id,
                        outcome, error_code, attrs_json, prev_hash
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        time.time(),
                        tool if tool is not None else "-",
                        json.dumps(safe_args, ensure_ascii=False)
                        if safe_args is not None
                        else None,
                        1 if outcome == "ok" else 0,
                        truncated,
                        turn_id,
                        event_type,
                        session_id,
                        _actor(),
                        instance_id(),
                        outcome,
                        error_code,
                        json.dumps(safe_attrs, ensure_ascii=False)
                        if safe_attrs is not None
                        else None,
                        None,
                    ),
                )
        except sqlite3.Error:
            from office_agent.diagnostic import emit

            emit("audit_write_failed", level="error", error_code="sqlite")
