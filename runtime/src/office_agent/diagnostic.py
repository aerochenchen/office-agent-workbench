from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from office_agent.paths import app_data_dir

_FORBIDDEN = frozenset({"api_key", "key", "token", "password", "passwd", "messages", "content"})
_KEEP_DAYS = 30
_MAX_BYTES = 20 * 1024 * 1024
_LEVELS = frozenset({"error", "warn", "info", "debug"})


def _min_level() -> str:
    raw = (os.environ.get("OFFICE_AGENT_LOG_LEVEL") or "info").strip().lower()
    return raw if raw in _LEVELS else "info"


def _enabled(level: str) -> bool:
    order = ("debug", "info", "warn", "error")
    try:
        return order.index(level) >= order.index(_min_level())
    except ValueError:
        return True


def configure(log_dir: Path | None = None) -> Path:
    root = Path(log_dir) if log_dir is not None else (app_data_dir() / "logs")
    root.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=_KEEP_DAYS)
    for path in root.glob("runtime-*.jsonl"):
        _prune_if_old(path, cutoff)
    for path in root.glob("desktop-*.jsonl"):
        _prune_if_old(path, cutoff)
    return root


def _prune_if_old(path: Path, cutoff) -> None:
    stem = path.name
    parts = stem.replace(".jsonl", "").split("-")
    if len(parts) < 4:
        return
    try:
        day = datetime(int(parts[1]), int(parts[2]), int(parts[3][:2]), tzinfo=timezone.utc).date()
    except ValueError:
        return
    if day < cutoff:
        path.unlink(missing_ok=True)


def current_log_path(kind: str = "runtime") -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    root = app_data_dir() / "logs"
    root.mkdir(parents=True, exist_ok=True)
    base = root / f"{kind}-{day}.jsonl"
    if base.is_file() and base.stat().st_size >= _MAX_BYTES:
        n = 1
        while True:
            cand = root / f"{kind}-{day}.{n}.jsonl"
            if not cand.is_file() or cand.stat().st_size < _MAX_BYTES:
                return cand
            n += 1
    return base


def emit(
    event: str,
    *,
    level: str = "info",
    turn_id: str | None = None,
    session_id: str | None = None,
    **fields: Any,
) -> None:
    lvl = level if level in _LEVELS else "info"
    if not _enabled(lvl):
        return
    row: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "level": lvl,
        "event": event,
        "turn_id": turn_id or "-",
    }
    if session_id:
        row["session_id"] = session_id
    boot = os.environ.get("OFFICE_AGENT_BOOT_ID", "").strip()
    if boot:
        row["boot_id"] = boot
    for key, value in fields.items():
        if key in _FORBIDDEN or key in row:
            continue
        if value is None:
            continue
        row[key] = value
    try:
        line = json.dumps(row, ensure_ascii=False) + "\n"
        path = current_log_path("runtime")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except (OSError, TypeError):
        pass
