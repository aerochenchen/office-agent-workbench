"""In-process filesystem jail for workspace/skill scripts (defense in depth)."""

from __future__ import annotations

import builtins
import os
import sys
from pathlib import Path


def _runtime_prefixes() -> list[Path]:
    prefixes: list[Path] = []
    for raw in (
        getattr(sys, "prefix", ""),
        getattr(sys, "base_prefix", ""),
        getattr(sys, "exec_prefix", ""),
        getattr(sys, "_MEIPASS", ""),
    ):
        if raw:
            prefixes.append(Path(raw).resolve())
    exe = Path(sys.executable).resolve()
    prefixes.append(exe.parent)
    if exe.parent.parent:
        prefixes.append(exe.parent.parent)
    return prefixes


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def install_fs_jail(roots: list[Path]) -> None:
    """Restrict builtins.open to jail roots plus the Python runtime tree.

    Only activates when OFFICE_AGENT_SCRIPT_JAIL=1 so a child subprocess cannot
    leak this monkeypatch into the parent runtime/tests.
    """
    if os.environ.get("OFFICE_AGENT_SCRIPT_JAIL") != "1":
        return
    allowed = [Path(r).resolve() for r in roots]
    runtime = _runtime_prefixes()
    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if isinstance(file, int):
            return real_open(file, mode, *args, **kwargs)
        path = Path(file).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            raise PermissionError(f"path outside script jail: {file}") from None
        if any(_is_under(resolved, root) for root in allowed):
            return real_open(file, mode, *args, **kwargs)
        if any(_is_under(resolved, root) for root in runtime):
            return real_open(file, mode, *args, **kwargs)
        posix = resolved.as_posix().lower()
        # Allow reading OS/Python bits required to start the interpreter.
        if posix.startswith(("/usr/", "/lib/", "/lib64/", "/etc/ssl", "/etc/pki")):
            return real_open(file, mode, *args, **kwargs)
        if posix.startswith("/system/") or posix.startswith("/library/"):
            return real_open(file, mode, *args, **kwargs)
        if posix.startswith("/opt/homebrew/") or posix.startswith("/opt/local/"):
            return real_open(file, mode, *args, **kwargs)
        raise PermissionError(f"path outside script jail: {resolved}")

    builtins.open = guarded_open  # type: ignore[assignment]
