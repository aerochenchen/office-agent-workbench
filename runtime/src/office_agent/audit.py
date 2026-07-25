from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


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
                    json.dumps(args, ensure_ascii=False),
                    1 if ok else 0,
                    detail,
                    turn_id,
                ),
            )
