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

    def record(self, tool: str, args: dict, ok: bool, detail: str = "") -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO audit (ts, tool, args_json, ok, detail) VALUES (?, ?, ?, ?, ?)",
                (
                    time.time(),
                    tool,
                    json.dumps(args, ensure_ascii=False),
                    1 if ok else 0,
                    detail,
                ),
            )
