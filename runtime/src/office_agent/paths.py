from __future__ import annotations

import os
from pathlib import Path


def chmod_private_dir(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def chmod_private_file(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def write_private_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chmod_private_dir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    chmod_private_file(path)


def write_private_text(path: Path, text: str) -> None:
    write_private_bytes(path, text.encode("utf-8"))


def app_data_dir() -> Path:
    override = os.environ.get("OFFICE_AGENT_DATA")
    p = Path(override) if override else Path.home() / ".office-agent"
    p.mkdir(parents=True, exist_ok=True)
    chmod_private_dir(p)
    for sub in ("skills", "shared-scripts", "db", "logs"):
        child = p / sub
        child.mkdir(exist_ok=True)
        chmod_private_dir(child)
    return p
