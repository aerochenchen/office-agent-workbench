from __future__ import annotations

import threading
import time
from pathlib import Path

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
