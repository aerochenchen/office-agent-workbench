from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from office_agent.permissions import PermissionGate
from office_agent.skills import SkillRegistry
from office_agent.tools import ToolExecutor
from office_agent.workspace import Workspace


def _wait_until(pred, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met before timeout")


def test_cautious_blocks_write_until_resolved(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()

    gate = PermissionGate(mode="cautious")
    gate.set_auto(None)
    seen: list = []
    gate.on_request = lambda req: seen.append(req)

    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="cautious",
        gate=gate,
    )

    results: list[dict] = []

    def run() -> None:
        results.append(
            ex.execute("workspace_write", {"path": "notes.txt", "content": "hi\n"})
        )

    t = threading.Thread(target=run)
    t.start()
    _wait_until(lambda: len(seen) >= 1)
    assert seen[0].tool == "workspace_write"
    gate.resolve(seen[0].id, True)
    t.join(timeout=5)
    assert not t.is_alive()

    assert len(results) == 1
    assert results[0]["ok"] is True
    assert (ws / "notes.txt").read_text(encoding="utf-8") == "hi\n"


def test_standard_remembers_same_script(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "shared-scripts").mkdir()
    (tmp_path / "shared-scripts" / "format_gongwen.py").write_text(
        "print('ok')\n", encoding="utf-8"
    )
    ws = tmp_path / "ws"
    ws.mkdir()

    gate = PermissionGate(mode="standard")
    gate.set_auto(None)
    seen: list = []
    gate.on_request = lambda req: seen.append(req)

    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="standard",
        gate=gate,
    )

    results: list[dict] = []

    def run_once() -> None:
        results.append(
            ex.execute("run_shared_script", {"name": "format_gongwen", "args": []})
        )

    t1 = threading.Thread(target=run_once)
    t1.start()
    _wait_until(lambda: len(seen) >= 1)
    gate.resolve(seen[0].id, True)
    t1.join(timeout=5)
    assert results[0]["ok"] is True
    assert "ok" in results[0]["stdout"]

    before = len(seen)
    # Same script name should be remembered — no second confirmation.
    second = ex.execute("run_shared_script", {"name": "format_gongwen", "args": []})
    assert second["ok"] is True
    assert len(seen) == before


def test_cancel_all_unblocks_wait_without_running_tool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()

    gate = PermissionGate(mode="cautious")
    gate.set_auto(None)
    seen: list = []
    gate.on_request = lambda req: seen.append(req)

    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="cautious",
        gate=gate,
    )

    results: list[dict] = []

    def run() -> None:
        results.append(
            ex.execute("workspace_write", {"path": "notes.txt", "content": "hi\n"})
        )

    t = threading.Thread(target=run)
    t.start()
    _wait_until(lambda: len(seen) >= 1)
    cancelled = gate.cancel_all()
    assert seen[0].id in cancelled
    t.join(timeout=5)
    assert not t.is_alive()
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert "permission denied" in results[0]["error"].lower()
    assert not (ws / "notes.txt").exists()


def test_skill_missing_run_python_denied(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = tmp_path / "skills" / "limited"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: limited\ndescription: d\ntier: light\n"
        "permissions:\n  - workspace_read\n---\n\n#\n",
        encoding="utf-8",
    )
    (skill / "scripts" / "hello.py").write_text("print('should-not-run')\n", encoding="utf-8")
    (tmp_path / "ws").mkdir()

    ex = ToolExecutor(
        Workspace(tmp_path / "ws"),
        SkillRegistry(),
        permission_mode="trust_workspace",
    )
    result = ex.execute(
        "run_skill_script",
        {"skill_id": "limited", "script": "hello.py", "args": []},
    )
    assert result["ok"] is False
    assert "permission denied" in result["error"].lower()
    assert "should-not-run" not in str(result)


def test_unattached_read_blocked_without_interactive_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "secret.txt").write_text("nope", encoding="utf-8")
    from office_agent.permissions import NeedsInteractivePermission, PermissionGate

    gate = PermissionGate(mode="cautious")
    gate.set_auto(False)
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="cautious", gate=gate)
    with pytest.raises(NeedsInteractivePermission):
        ex.execute("workspace_read", {"path": "secret.txt"})


def test_attached_read_skips_confirmation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "doc.txt").write_text("ok", encoding="utf-8")
    from office_agent.permissions import PermissionGate

    gate = PermissionGate(mode="cautious")
    gate.set_auto(False)
    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="cautious",
        gate=gate,
        attached_paths=["doc.txt"],
    )
    result = ex.execute("workspace_read", {"path": "doc.txt"})
    assert result["ok"] is True
    assert result["content"] == "ok"


def test_workspace_script_denied_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    work = ws / ".office-agent" / "work"
    work.mkdir(parents=True)
    (work / "p.py").write_text("print('x')\n", encoding="utf-8")
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute("run_workspace_script", {"path": "p.py", "args": []})
    assert result["ok"] is False
    assert "disabled" in result["error"].lower()


def test_on_decision_not_called_for_needs_interactive() -> None:
    from office_agent.permissions import NeedsInteractivePermission

    decisions: list[tuple[str, str, str]] = []
    gate = PermissionGate(mode="cautious")
    gate.set_auto(False)
    gate.on_decision = lambda tool, decision, mode: decisions.append((tool, decision, mode))

    with pytest.raises(NeedsInteractivePermission):
        gate.check("workspace_write", {"path": "x.txt", "content": "a"})

    assert decisions == []


def test_on_decision_allow_via_resolve() -> None:
    decisions: list[tuple[str, str, str]] = []
    seen: list = []
    gate = PermissionGate(mode="cautious")
    gate.set_auto(None)
    gate.on_request = lambda req: seen.append(req)
    gate.on_decision = lambda tool, decision, mode: decisions.append((tool, decision, mode))

    errors: list[BaseException] = []

    def run() -> None:
        try:
            gate.check("workspace_write", {"path": "notes.txt", "content": "hi\n"})
        except BaseException as e:
            errors.append(e)

    t = threading.Thread(target=run)
    t.start()
    _wait_until(lambda: len(seen) >= 1)
    gate.resolve(seen[0].id, True)
    t.join(timeout=5)
    assert not t.is_alive()
    assert errors == []
    assert decisions == [("workspace_write", "allow", "cautious")]


def test_on_decision_deny_via_resolve() -> None:
    from office_agent.permissions import PermissionDenied

    decisions: list[tuple[str, str, str]] = []
    seen: list = []
    gate = PermissionGate(mode="cautious")
    gate.set_auto(None)
    gate.on_request = lambda req: seen.append(req)
    gate.on_decision = lambda tool, decision, mode: decisions.append((tool, decision, mode))

    errors: list[BaseException] = []

    def run() -> None:
        try:
            gate.check("workspace_write", {"path": "notes.txt", "content": "hi\n"})
        except BaseException as e:
            errors.append(e)

    t = threading.Thread(target=run)
    t.start()
    _wait_until(lambda: len(seen) >= 1)
    gate.resolve(seen[0].id, False)
    t.join(timeout=5)
    assert not t.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], PermissionDenied)
    assert decisions == [("workspace_write", "deny", "cautious")]


def test_on_decision_timeout_when_no_resolve() -> None:
    from office_agent.permissions import PermissionDenied

    decisions: list[tuple[str, str, str]] = []
    timed_out: list[str] = []
    gate = PermissionGate(mode="cautious")
    gate.set_auto(None)
    gate.wait_timeout = 0.05
    gate.on_timeout = lambda request_id: timed_out.append(request_id)
    gate.on_decision = lambda tool, decision, mode: decisions.append((tool, decision, mode))

    with pytest.raises(PermissionDenied, match="timed out"):
        gate.check("workspace_write", {"path": "notes.txt", "content": "hi\n"})

    assert len(timed_out) == 1
    assert decisions == [("workspace_write", "timeout", "cautious")]
