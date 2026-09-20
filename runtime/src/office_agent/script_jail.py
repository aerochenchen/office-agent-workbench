"""In-process filesystem jail for workspace/skill scripts (defense in depth)."""

from __future__ import annotations

import builtins
import io
import os
import sys
from pathlib import Path

from office_agent.paths import app_data_dir

_SECRET_FILE_NAMES = frozenset({"config.json", "secrets.key"})


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


def is_denied_secret_path(path: Path) -> bool:
    """True for the runtime config/wrapping-key files under the app data dir."""
    try:
        resolved = Path(path).expanduser().resolve()
        data = app_data_dir().resolve()
    except OSError:
        return False
    if resolved.name.lower() not in _SECRET_FILE_NAMES:
        return False
    try:
        resolved.relative_to(data)
    except ValueError:
        return False
    return resolved.parent == data


def _assert_jail_path(file: object, allowed: list[Path], runtime: list[Path]) -> Path:
    path = Path(file).expanduser()  # type: ignore[arg-type]
    try:
        resolved = path.resolve()
    except OSError as e:
        raise PermissionError(f"path outside script jail: {file}") from e
    if is_denied_secret_path(resolved):
        raise PermissionError(f"denied secret path: {resolved}")
    if any(_is_under(resolved, root) for root in allowed):
        return resolved
    if any(_is_under(resolved, root) for root in runtime):
        return resolved
    posix = resolved.as_posix().lower()
    if posix.startswith(("/usr/", "/lib/", "/lib64/", "/etc/ssl", "/etc/pki")):
        return resolved
    if posix.startswith("/system/") or posix.startswith("/library/"):
        return resolved
    if posix.startswith("/opt/homebrew/") or posix.startswith("/opt/local/"):
        return resolved
    raise PermissionError(f"path outside script jail: {resolved}")


def install_fs_jail(roots: list[Path]) -> None:
    """Restrict builtins.open, io.open and os.open to jail roots plus the Python runtime tree.

    Only activates when OFFICE_AGENT_SCRIPT_JAIL=1 so a child subprocess cannot
    leak this monkeypatch into the parent runtime/tests.
    """
    if os.environ.get("OFFICE_AGENT_SCRIPT_JAIL") != "1":
        return
    allowed = [Path(r).resolve() for r in roots]
    runtime = _runtime_prefixes()
    real_open = builtins.open
    real_os_open = os.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if isinstance(file, int):
            return real_open(file, mode, *args, **kwargs)
        _assert_jail_path(file, allowed, runtime)
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path, flags, mode=0o777, *args, **kwargs):
        if not isinstance(path, int):
            _assert_jail_path(path, allowed, runtime)
        return real_os_open(path, flags, mode, *args, **kwargs)

    builtins.open = guarded_open  # type: ignore[assignment]
    io.open = guarded_open  # type: ignore[assignment]
    os.open = guarded_os_open  # type: ignore[assignment]
