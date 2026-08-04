from __future__ import annotations

from pathlib import Path

import pytest

from office_agent.audit import AuditLog
from office_agent.plan_store import PLAN_HTML_REL, PLAN_REL
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
    assert ex.execute("plan_set_approval", {"approval": "approved"})["ok"]
    assert ex.execute(
        "plan_update_step", {"step_id": "s1", "status": "in_progress"}
    )["ok"]
    assert ex.execute("plan_update_step", {"step_id": "s1", "status": "done"})["ok"]
    assert ex.execute(
        "plan_update_step", {"step_id": "s2", "status": "done"}
    )["ok"]
    got = ex.execute("plan_get", {})
    assert got["plan"]["status"] == "completed"


def test_plan_get_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ex = _executor(tmp_path, monkeypatch)
    got = ex.execute("plan_get", {})
    assert got["ok"] is False
    assert got["reason"] == "missing"


def test_plan_set_status_cancelled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ex = _executor(tmp_path, monkeypatch)
    ex.execute(
        "plan_create",
        {
            "goal": "A",
            "steps": [{"id": "s1", "title": "a"}, {"id": "s2", "title": "b"}],
        },
    )
    result = ex.execute("plan_set_status", {"status": "cancelled"})
    assert result["ok"] is True
    assert result["plan"]["status"] == "cancelled"


def test_plan_create_sets_pending_and_writes_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ex = _executor(tmp_path, monkeypatch)
    ws = tmp_path / "ws"
    created = ex.execute(
        "plan_create",
        {
            "goal": "写报告",
            "steps": [{"id": "s1", "title": "摸底"}, {"id": "s2", "title": "撰写"}],
        },
    )
    assert created["ok"] is True
    assert created["plan"]["approval"] == "pending"
    html_path = ws / PLAN_HTML_REL
    assert html_path.is_file()
    html = html_path.read_text(encoding="utf-8")
    assert "写报告" in html
    assert "对话框" in html


def test_plan_update_step_blocked_until_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ex = _executor(tmp_path, monkeypatch)
    ex.execute(
        "plan_create",
        {
            "goal": "A",
            "steps": [{"id": "s1", "title": "a"}, {"id": "s2", "title": "b"}],
        },
    )
    blocked = ex.execute(
        "plan_update_step", {"step_id": "s1", "status": "in_progress"}
    )
    assert blocked["ok"] is False
    assert "approval" in blocked["error"].lower()


def test_plan_set_approval_approved_allows_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ex = _executor(tmp_path, monkeypatch)
    ws = tmp_path / "ws"
    ex.execute(
        "plan_create",
        {
            "goal": "A",
            "steps": [{"id": "s1", "title": "a"}, {"id": "s2", "title": "b"}],
        },
    )
    approved = ex.execute("plan_set_approval", {"approval": "approved"})
    assert approved["ok"] is True
    assert approved["plan"]["approval"] == "approved"
    html = (ws / PLAN_HTML_REL).read_text(encoding="utf-8")
    assert "A" in html
    assert ex.execute(
        "plan_update_step", {"step_id": "s1", "status": "in_progress"}
    )["ok"]


def test_plan_set_approval_rejected_cancels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    ex = _executor(tmp_path, monkeypatch)
    ws = tmp_path / "ws"
    ex.execute(
        "plan_create",
        {
            "goal": "A",
            "steps": [{"id": "s1", "title": "a"}, {"id": "s2", "title": "b"}],
        },
    )
    html_path = ws / PLAN_HTML_REL
    html_before = html_path.read_text(encoding="utf-8")
    mtime_before = html_path.stat().st_mtime
    assert "已取消" not in html_before

    rejected = ex.execute("plan_set_approval", {"approval": "rejected"})
    assert rejected["ok"] is True
    assert rejected["plan"]["approval"] == "rejected"
    assert rejected["plan"]["status"] == "cancelled"

    html_after = html_path.read_text(encoding="utf-8")
    assert html_after != html_before
    assert html_path.stat().st_mtime >= mtime_before
    assert "已取消" in html_after

    blocked = ex.execute(
        "plan_update_step", {"step_id": "s1", "status": "in_progress"}
    )
    assert blocked["ok"] is False
    assert "approval" in blocked["error"].lower()


def test_plan_set_status_completed_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ex = _executor(tmp_path, monkeypatch)
    ex.execute(
        "plan_create",
        {
            "goal": "A",
            "steps": [{"id": "s1", "title": "a"}, {"id": "s2", "title": "b"}],
        },
    )
    result = ex.execute("plan_set_status", {"status": "completed"})
    assert result["ok"] is False
    assert "done" in result["error"].lower() or "skipped" in result["error"].lower()
