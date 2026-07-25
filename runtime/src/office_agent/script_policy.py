from __future__ import annotations

import os
from pathlib import Path

from office_agent.workspace import DELIVERABLE_SUFFIXES

_PATH_LIKE_SUFFIXES = frozenset({".py", ".txt", ".md", ".json", ".csv", ".yaml", ".yml"}) | DELIVERABLE_SUFFIXES


def build_script_env(base: dict | None = None) -> dict[str, str]:
    """Force HF/TRANSFORMERS offline; clear HTTP(S)_PROXY; set NO_PROXY=*."""
    env = dict(os.environ if base is None else base)
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["NO_PROXY"] = "*"
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(key, None)
    return env


def _looks_like_path(arg: str) -> bool:
    if not arg or arg.startswith("-"):
        return False
    raw = Path(arg)
    if raw.exists():
        return True
    if "/" in arg or "\\" in arg:
        return True
    return raw.suffix.lower() in _PATH_LIKE_SUFFIXES


def _resolve_under_roots(arg: str, roots: list[Path]) -> Path:
    raw = Path(arg).expanduser()
    resolved_roots = [root.resolve() for root in roots]
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw.resolve())
    else:
        for root in resolved_roots:
            candidates.append((root / raw).resolve())
    for candidate in candidates:
        for root in resolved_roots:
            try:
                candidate.relative_to(root)
                return candidate
            except ValueError:
                continue
    raise _tool_error(f"path argument outside allowed roots: {arg}")


def _tool_error(message: str) -> Exception:
    from office_agent.tools import ToolError

    return ToolError(message)


def assert_argv_within_roots(argv: list[str], roots: list[Path]) -> None:
    """
    For each arg that looks like a filesystem path (exists or has path sep
    or suffix .py/.docx/...), resolve and require relative_to one of roots.
    Raise ToolError otherwise.
    """
    if not roots:
        raise _tool_error("no allowed roots configured for script argv")
    for arg in argv:
        if not _looks_like_path(arg):
            continue
        _resolve_under_roots(arg, roots)
