from __future__ import annotations

import json
from pathlib import Path

import pytest

from office_agent.plan_store import (
    PLAN_REL,
    PlanValidationError,
    apply_step_update,
    save_plan,
    set_plan_status,
    validate_plan,
)


def _minimal_plan(**overrides):
    base = {
        "version": 1,
        "id": "plan_test",
        "goal": "做完两件事",
        "status": "active",
        "created_at": "2026-08-04T00:00:00+08:00",
        "updated_at": "2026-08-04T00:00:00+08:00",
        "steps": [
            {
                "id": "s1",
                "title": "第一步",
                "detail": "",
                "status": "pending",
                "depends_on": [],
                "inputs": [],
                "outputs": [],
                "needs_user": False,
                "notes": "",
            },
            {
                "id": "s2",
                "title": "第二步",
                "detail": "",
                "status": "pending",
                "depends_on": ["s1"],
                "inputs": [],
                "outputs": [],
                "needs_user": False,
                "notes": "",
            },
        ],
        "resume_hint": "按工作计划未完成项继续",
    }
    base.update(overrides)
    return base


def test_plan_rel_constant():
    assert PLAN_REL == ".office-agent/work/plan.json"


def test_validate_rejects_single_step():
    plan = _minimal_plan()
    plan["steps"] = plan["steps"][:1]
    with pytest.raises(PlanValidationError, match="at least 2"):
        validate_plan(plan)


def test_validate_rejects_two_in_progress():
    plan = _minimal_plan()
    plan["steps"][0]["status"] = "in_progress"
    plan["steps"][1]["status"] = "in_progress"
    plan["steps"][1]["depends_on"] = []
    with pytest.raises(PlanValidationError, match="in_progress"):
        validate_plan(plan)


def test_apply_step_update_blocks_before_dependency_done():
    plan = validate_plan(_minimal_plan())
    with pytest.raises(PlanValidationError, match="depends"):
        apply_step_update(plan, "s2", status="in_progress")


def test_apply_step_update_auto_completes_plan(tmp_path: Path):
    plan = validate_plan(_minimal_plan())
    plan = apply_step_update(plan, "s1", status="done")
    plan = apply_step_update(plan, "s2", status="done")
    assert plan["status"] == "completed"
    path = tmp_path / "plan.json"
    save_plan(path, plan)
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "completed"


def test_set_plan_status_cancelled():
    plan = validate_plan(_minimal_plan())
    out = set_plan_status(plan, "cancelled")
    assert out["status"] == "cancelled"
