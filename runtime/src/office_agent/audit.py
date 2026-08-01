from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


# 工具参数中的这些字段视为敏感内容：审计落库时只保留长度，不存明文，
# 避免审计库本身成为敏感数据池（如 workspace_write 的 content 含公文全文）。
_SENSITIVE_ARG_FIELDS = frozenset({"content", "api_key", "key", "token", "password", "passwd"})


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

    def record(
        self,
        tool: str,
        args: dict,
        ok: bool,
        detail: str = "",
        *,
        turn_id: str | None = None,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit (ts, tool, args_json, ok, detail, turn_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    tool,
                    json.dumps(_redact_args(args), ensure_ascii=False),
                    1 if ok else 0,
                    detail,
                    turn_id,
                ),
            )
