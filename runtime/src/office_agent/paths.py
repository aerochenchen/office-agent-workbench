from __future__ import annotations
import os
from pathlib import Path


def app_data_dir() -> Path:
    override = os.environ.get("OFFICE_AGENT_DATA")
    p = Path(override) if override else Path.home() / ".office-agent"
    p.mkdir(parents=True, exist_ok=True)
    for sub in ("skills", "shared-scripts", "db", "logs"):
        (p / sub).mkdir(exist_ok=True)
    return p
