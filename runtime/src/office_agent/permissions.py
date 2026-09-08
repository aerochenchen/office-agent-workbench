from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class PermissionDenied(Exception):
    """Raised when a tool call is blocked by the permission gate or skill ACL."""


class NeedsInteractivePermission(Exception):
    """Raised when a non-interactive /chat turn hits a tool that requires confirmation."""

    def __init__(self, tool: str, args: dict, summary: str) -> None:
        self.tool = tool
        self.args = dict(args)
        self.summary = summary
        super().__init__(f"needs interactive permission: {tool}")


@dataclass
class PermissionRequest:
    id: str
    tool: str
    summary: str
    args: dict
    destination: str = ""
    path: str = ""


READ_ONLY_TOOLS = frozenset(
    {
        "workspace_list",
        "read_skill",
        "plan_get",
        "ask_user",
        "finish",
    }
)

# File contents leave the machine toward the configured model host.
SENSITIVE_READ_TOOLS = frozenset(
    {
        "workspace_read",
        "workspace_extract",
    }
)

RISKY_TOOLS = frozenset(
    {
        "workspace_write",
        "workspace_extract",
        "run_workspace_script",
        "run_skill_script",
        "run_shared_script",
        "plan_create",
        "plan_update_step",
        "plan_set_status",
        "plan_set_approval",
    }
)

GATED_TOOLS = RISKY_TOOLS | SENSITIVE_READ_TOOLS

_TRUST_MODES = frozenset({"trust", "trust_workspace"})


def _normalize_rel(rel: str) -> str:
    normalized = str(rel or "").replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip()


def _summarize(tool: str, args: dict) -> str:
    if tool == "workspace_read":
        return f"read {args.get('path', '')}"
    if tool == "workspace_write":
        return f"write {args.get('path', '')}"
    if tool == "workspace_extract":
        return f"extract {args.get('path', '')}"
    if tool == "run_workspace_script":
        return f"run workspace script {args.get('path', '')}"
    if tool == "run_skill_script":
        return f"run skill script {args.get('skill_id', '')}/{args.get('script', '')}"
    if tool == "run_shared_script":
        return f"run shared script {args.get('name', '')}"
    if tool == "plan_create":
        return f"create plan: {args.get('goal', '')}"
    if tool == "plan_update_step":
        return f"update step {args.get('step_id', '')} → {args.get('status', '')}"
    if tool == "plan_set_status":
        return f"set plan status {args.get('status', '')}"
    if tool == "plan_set_approval":
        return f"set plan approval {args.get('approval', '')}"
    return tool


class PermissionGate:
    def __init__(self, mode: str = "standard", *, destination_host: str = "") -> None:
        self.mode = mode or "standard"
        self.destination_host = destination_host
        self._auto: bool | None = None
        self._remembered: set[str] = set()
        self._read_allowlist: set[str] = set()
        self._lock = threading.Lock()
        self._pending: dict[str, threading.Event] = {}
        self._decisions: dict[str, bool] = {}
        self._requests: dict[str, PermissionRequest] = {}
        self.on_request: Callable[[PermissionRequest], None] | None = None
        self.on_timeout: Callable[[str], None] | None = None
        self.wait_timeout: float = 300.0

    def set_auto(self, allow: bool | None) -> None:
        """None = interactive waiter; True/False = auto allow/deny for tests."""
        self._auto = allow

    def allow_read_path(self, rel: str) -> None:
        normalized = _normalize_rel(rel)
        if normalized:
            self._read_allowlist.add(normalized)

    def remember_key(self, tool: str, args: dict) -> str:
        if tool == "run_shared_script":
            return f"{tool}:{args.get('name', '')}"
        if tool == "run_skill_script":
            return f"{tool}:{args.get('skill_id', '')}:{args.get('script', '')}"
        if tool in (
            "run_workspace_script",
            "workspace_write",
            "workspace_extract",
            "workspace_read",
        ):
            return f"{tool}:{args.get('path', '')}"
        return f"{tool}"

    def _read_allowed(self, args: dict) -> bool:
        path = _normalize_rel(str(args.get("path") or ""))
        return bool(path) and path in self._read_allowlist

    def check(self, tool: str, args: dict) -> None:
        """Raise PermissionDenied / NeedsInteractivePermission or block until allow."""
        if tool in READ_ONLY_TOOLS or tool not in GATED_TOOLS:
            return
        if tool in SENSITIVE_READ_TOOLS and self._read_allowed(args):
            return
        if self.mode in _TRUST_MODES:
            return
        if self._auto is True:
            return
        if self._auto is False:
            raise NeedsInteractivePermission(tool, args, _summarize(tool, args))

        key = self.remember_key(tool, args)
        if self.mode == "standard" and key in self._remembered:
            return

        request = PermissionRequest(
            id=str(uuid.uuid4()),
            tool=tool,
            summary=_summarize(tool, args),
            args=dict(args),
            destination=self.destination_host,
            path=_normalize_rel(str(args.get("path") or "")),
        )
        event = threading.Event()
        with self._lock:
            self._pending[request.id] = event
            self._requests[request.id] = request

        callback = self.on_request
        if callback is not None:
            callback(request)

        if not event.wait(timeout=self.wait_timeout):
            with self._lock:
                self._pending.pop(request.id, None)
                self._requests.pop(request.id, None)
            timeout_cb = self.on_timeout
            if timeout_cb is not None:
                timeout_cb(request.id)
            raise PermissionDenied(f"permission request timed out: {tool}")

        with self._lock:
            allowed = bool(self._decisions.pop(request.id, False))
            self._pending.pop(request.id, None)
            self._requests.pop(request.id, None)

        if not allowed:
            raise PermissionDenied(f"denied by user: {tool}")

        if self.mode == "standard":
            self._remembered.add(key)

    def resolve(self, request_id: str, allow: bool) -> None:
        with self._lock:
            event = self._pending.get(request_id)
            if event is None:
                raise KeyError(f"unknown permission request: {request_id}")
            self._decisions[request_id] = allow
        event.set()

    def cancel_all(self) -> list[str]:
        """Wake every waiter with deny so Cancel/UI stop does not run the tool.

        Returns the cancelled request ids (for clearing ProcessState.gates).
        """
        with self._lock:
            ids = list(self._pending.keys())
            for request_id in ids:
                self._decisions[request_id] = False
            events = list(self._pending.values())
        for event in events:
            event.set()
        return ids
