from __future__ import annotations

from pathlib import Path

import pytest

from office_agent.audit import AuditLog
from office_agent.plan_store import PLAN_REL
from office_agent.skills import SkillRegistry
from office_agent.tools import ToolExecutor
from office_agent.workspace import Workspace


def _executor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ToolExecutor:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    return ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="trust",
        audit=AuditLog(tmp_path / "audit.jsonl"),
    )


def test_plan_create_and_get(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ex = _executor(tmp_path, monkeypatch)
    ws = tmp_path / "ws"
    created = ex.execute(
        "plan_create",
        {
            "goal": "分两步处理材料",
            "steps": [
                {"id": "s1", "title": "摸底"},
                {"id": "s2", "title": "写报告", "depends_on": ["s1"]},
            ],
        },
    )
    assert created["ok"] is True
    assert (ws / PLAN_REL).is_file()
    got = ex.execute("plan_get", {})
    assert got["ok"] is True
    assert got["plan"]["goal"] == "分两步处理材料"
    assert len(got["plan"]["steps"]) == 2


def test_plan_create_rejects_second_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ex = _executor(tmp_path, monkeypatch)
    assert ex.execute(
        "plan_create",
        {
            "goal": "A",
            "steps": [{"id": "s1", "title": "a"}, {"id": "s2", "title": "b"}],
        },
    )["ok"]
    second = ex.execute(
        "plan_create",
        {
            "goal": "B",
            "steps": [{"id": "s1", "title": "a"}, {"id": "s2", "title": "b"}],
        },
    )
    assert second["ok"] is False
    assert "active" in second["error"].lower() or "active" in str(second.get("error", ""))


def test_plan_update_and_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ex = _executor(tmp_path, monkeypatch)
    ex.execute(
        "plan_create",
        {
            "goal": "A",
            "steps": [{"id": "s1", "title": "a"}, {"id": "s2", "title": "b"}],
        },
    )
    assert ex.execute(
        "plan_update_step", {"step_id": "s1", "status": "in_progress"}
    )["ok"]
    assert ex.execute("plan_update_step", {"step_id": "s1", "status": "done"})["ok"]
    assert ex.execute(
        "plan_update_step", {"step_id": "s2", "status": "done"}
    )["ok"]
    got = ex.execute("plan_get", {})
    assert got["plan"]["status"] == "completed"
