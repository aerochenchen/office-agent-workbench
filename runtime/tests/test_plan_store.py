from __future__ import annotations

import json
from pathlib import Path

import pytest

from office_agent.plan_store import (
    APPROVAL_STATUSES,
    PLAN_HTML_REL,
    PLAN_REL,
    PlanValidationError,
    apply_step_update,
    effective_approval,
    render_plan_html,
    save_plan,
    set_plan_approval,
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


def test_set_plan_status_completed_requires_all_steps_done():
    plan = validate_plan(_minimal_plan())
    with pytest.raises(PlanValidationError, match="done|skipped|completed"):
        set_plan_status(plan, "completed")


def test_approval_statuses_constant():
    assert APPROVAL_STATUSES == frozenset({"pending", "approved", "rejected"})


def test_plan_html_rel_constant():
    assert PLAN_HTML_REL == "output/工作计划.html"


def test_effective_approval_defaults_to_approved():
    plan = validate_plan(_minimal_plan())
    assert effective_approval(plan) == "approved"


def test_effective_approval_returns_explicit_value():
    plan = validate_plan({**_minimal_plan(), "approval": "pending"})
    assert effective_approval(plan) == "pending"


def test_validate_accepts_optional_approval():
    for status in APPROVAL_STATUSES:
        plan = validate_plan({**_minimal_plan(), "approval": status})
        assert plan["approval"] == status


def test_validate_rejects_invalid_approval():
    with pytest.raises(PlanValidationError, match="approval"):
        validate_plan({**_minimal_plan(), "approval": "maybe"})


def test_apply_step_update_blocks_in_progress_when_pending():
    plan = validate_plan({**_minimal_plan(), "approval": "pending"})
    with pytest.raises(PlanValidationError, match="approval"):
        apply_step_update(plan, "s1", status="in_progress")


def test_apply_step_update_blocks_done_when_pending():
    plan = validate_plan({**_minimal_plan(), "approval": "pending"})
    with pytest.raises(PlanValidationError, match="approval"):
        apply_step_update(plan, "s1", status="done")


def test_apply_step_update_allows_notes_when_pending():
    plan = validate_plan({**_minimal_plan(), "approval": "pending"})
    out = apply_step_update(plan, "s1", notes="先不改状态")
    assert out["steps"][0]["notes"] == "先不改状态"
    assert out["steps"][0]["status"] == "pending"


def test_apply_step_update_allows_in_progress_when_approved():
    plan = validate_plan({**_minimal_plan(), "approval": "approved"})
    out = apply_step_update(plan, "s1", status="in_progress")
    assert out["steps"][0]["status"] == "in_progress"


def test_set_plan_approval_sets_value():
    plan = validate_plan({**_minimal_plan(), "approval": "pending"})
    out = set_plan_approval(plan, "approved")
    assert out["approval"] == "approved"


def test_set_plan_approval_rejected_cancels_by_default():
    plan = validate_plan({**_minimal_plan(), "approval": "pending"})
    out = set_plan_approval(plan, "rejected")
    assert out["approval"] == "rejected"
    assert out["status"] == "cancelled"


def test_set_plan_approval_rejected_without_cancel():
    plan = validate_plan({**_minimal_plan(), "approval": "pending"})
    out = set_plan_approval(plan, "rejected", cancel_if_rejected=False)
    assert out["approval"] == "rejected"
    assert out["status"] == "active"


def test_render_plan_html_includes_goal_and_steps():
    plan = validate_plan(_minimal_plan())
    html = render_plan_html(plan)
    assert "做完两件事" in html
    assert "第一步" in html
    assert "第二步" in html


def test_render_plan_html_escapes_and_footer():
    plan = validate_plan({**_minimal_plan(), "goal": "A <B> & C", "approval": "pending"})
    html = render_plan_html(plan)
    assert "A &lt;B&gt; &amp; C" in html
    assert "<script" not in html.lower()
    assert "对话框" in html
