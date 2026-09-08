"""OS-level isolation and resource caps for script subprocesses."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

SCRIPT_TIMEOUT_SEC = 120
STDOUT_CAP_BYTES = 64 * 1024


def apply_rlimits() -> None:
    """Best-effort CPU/memory/process caps in the child (Unix)."""
    try:
        import resource
    except ImportError:
        return
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (SCRIPT_TIMEOUT_SEC, SCRIPT_TIMEOUT_SEC + 5))
    except (ValueError, OSError):
        pass
    try:
        # 1 GiB address space
        limit = 1024 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ValueError, OSError, AttributeError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    except (ValueError, OSError, AttributeError):
        pass
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    except (ValueError, OSError, AttributeError):
        pass


def preexec_isolate() -> None:
    apply_rlimits()
    try:
        os.setsid()
    except OSError:
        pass


def truncate_output(text: str | None, cap: int = STDOUT_CAP_BYTES) -> tuple[str, bool]:
    raw = text or ""
    encoded = raw.encode("utf-8", errors="replace")
    if len(encoded) <= cap:
        return raw, False
    clipped = encoded[:cap].decode("utf-8", errors="replace")
    return clipped + "\n…[output truncated]\n", True


def sandbox_available() -> bool:
    if sys.platform.startswith("linux"):
        return shutil.which("unshare") is not None
    if sys.platform == "darwin":
        return shutil.which("sandbox-exec") is not None
    return False


def wrap_isolated_cmd(cmd: list[str], *, workspace: Path) -> list[str]:
    """Prefix cmd with OS isolation when the tool exists.

    Linux: new empty net namespace (no outbound/inbound except what we add).
    macOS: sandbox-exec profile denying network.
    Other platforms: return cmd unchanged (caller may fail-closed).
    """
    if sys.platform.startswith("linux"):
        unshare = shutil.which("unshare")
        if unshare:
            return [unshare, "--net", "--", *cmd]
        return cmd
    if sys.platform == "darwin":
        sandbox_exec = shutil.which("sandbox-exec")
        if not sandbox_exec:
            return cmd
        ws = str(workspace.resolve())
        profile = (
            "(version 1)\n"
            "(deny default)\n"
            "(allow process-exec)\n"
            "(allow process-fork)\n"
            "(allow signal)\n"
            "(allow sysctl-read)\n"
            "(allow mach-lookup)\n"
            "(allow file-ioctl)\n"
            "(allow file-read*)\n"
            f'(allow file-write* (subpath "{ws}"))\n'
            '(allow file-write* (subpath "/private/tmp"))\n'
            '(allow file-write* (subpath "/tmp"))\n'
            "(deny network*)\n"
        )
        return [sandbox_exec, "-p", profile, *cmd]
    return cmd
