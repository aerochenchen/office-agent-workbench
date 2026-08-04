from __future__ import annotations

import copy
import html
import json
from datetime import datetime, timezone
from pathlib import Path

PLAN_REL = ".office-agent/work/plan.json"
PLAN_HTML_REL = "output/工作计划.html"

PLAN_STATUSES = frozenset({"active", "completed", "blocked", "cancelled"})
STEP_STATUSES = frozenset({"pending", "in_progress", "done", "failed", "skipped"})
APPROVAL_STATUSES = frozenset({"pending", "approved", "rejected"})


class PlanValidationError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def effective_approval(plan: dict) -> str:
    return plan.get("approval", "approved")


def validate_plan(data: dict) -> dict:
    if not isinstance(data, dict):
        raise PlanValidationError("plan must be a dict")

    if data.get("version") != 1:
        raise PlanValidationError("version must be 1")

    status = data.get("status")
    if status not in PLAN_STATUSES:
        raise PlanValidationError(f"invalid plan status: {status!r}")

    approval = data.get("approval")
    if approval is not None and approval not in APPROVAL_STATUSES:
        raise PlanValidationError(f"invalid approval: {approval!r}")

    steps = data.get("steps")
    if not isinstance(steps, list):
        raise PlanValidationError("steps must be a list")

    if len(steps) < 2:
        raise PlanValidationError("steps must contain at least 2 items")

    step_ids: set[str] = set()
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise PlanValidationError(f"step {i} must be a dict")
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id:
            raise PlanValidationError(f"step {i} missing id")
        if step_id in step_ids:
            raise PlanValidationError(f"duplicate step id: {step_id!r}")
        step_ids.add(step_id)

        step_status = step.get("status")
        if step_status not in STEP_STATUSES:
            raise PlanValidationError(
                f"invalid step status for {step_id!r}: {step_status!r}"
            )

    status_by_id: dict[str, str] = {}
    for step in steps:
        step_id = step["id"]
        depends_on = step.get("depends_on")
        if not isinstance(depends_on, list):
            raise PlanValidationError(f"depends_on for {step_id!r} must be a list")
        for dep in depends_on:
            if dep not in step_ids:
                raise PlanValidationError(
                    f"depends_on references unknown step id: {dep!r}"
                )
        status_by_id[step_id] = step.get("status")

    in_progress_count = sum(1 for s in steps if s.get("status") == "in_progress")
    if in_progress_count > 1:
        raise PlanValidationError("at most one step may be in_progress")

    for step in steps:
        step_status = step.get("status")
        if step_status in ("in_progress", "done"):
            for dep in step.get("depends_on") or []:
                dep_status = status_by_id.get(dep)
                if dep_status not in ("done", "skipped"):
                    raise PlanValidationError(
                        f"step {step['id']!r} depends on {dep!r} which is not done or skipped"
                    )

    return copy.deepcopy(data)


def load_plan(path: Path) -> dict | None:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return validate_plan(raw)


def save_plan(path: Path, data: dict) -> None:
    validated = validate_plan(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(validated, f, ensure_ascii=False, indent=2)


def apply_step_update(
    plan: dict,
    step_id: str,
    *,
    status: str | None = None,
    notes: str | None = None,
    outputs: list[str] | None = None,
) -> dict:
    updated = copy.deepcopy(plan)
    steps = updated.get("steps", [])
    target = None
    for step in steps:
        if step.get("id") == step_id:
            target = step
            break
    if target is None:
        raise PlanValidationError(f"unknown step id: {step_id!r}")

    if status is not None and status in ("in_progress", "done"):
        if effective_approval(updated) != "approved":
            raise PlanValidationError(
                "plan approval required before setting step to in_progress or done"
            )

    if status is not None:
        target["status"] = status
    if notes is not None:
        target["notes"] = notes
    if outputs is not None:
        target["outputs"] = outputs

    updated["updated_at"] = _now_iso()
    validated = validate_plan(updated)

    if all(s.get("status") in ("done", "skipped") for s in validated["steps"]):
        validated["status"] = "completed"

    return validated


def set_plan_status(plan: dict, status: str) -> dict:
    if status == "completed":
        for step in plan.get("steps", []):
            if step.get("status") not in ("done", "skipped"):
                raise PlanValidationError(
                    "cannot mark plan completed until every step is done or skipped"
                )
    updated = copy.deepcopy(plan)
    updated["status"] = status
    updated["updated_at"] = _now_iso()
    return validate_plan(updated)


def set_plan_approval(
    plan: dict, approval: str, *, cancel_if_rejected: bool = True
) -> dict:
    if approval not in APPROVAL_STATUSES:
        raise PlanValidationError(f"invalid approval: {approval!r}")

    updated = copy.deepcopy(plan)
    updated["approval"] = approval
    if approval == "rejected" and cancel_if_rejected:
        updated["status"] = "cancelled"
    updated["updated_at"] = _now_iso()
    return validate_plan(updated)


def _plan_status_label(plan: dict) -> str:
    approval = plan.get("approval")
    status = plan.get("status")
    if approval == "rejected" or status == "cancelled":
        return "已取消"
    if approval == "pending":
        return "待确认"
    if status == "completed":
        return "已完成"
    return ""


def render_plan_html(plan: dict) -> str:
    goal = html.escape(plan.get("goal", ""))
    status_label = _plan_status_label(plan)
    steps = plan.get("steps", [])

    step_items = []
    for i, step in enumerate(steps, start=1):
        title = html.escape(step.get("title", ""))
        detail = html.escape(step.get("detail", ""))
        status = html.escape(step.get("status", ""))
        item = f"<li><strong>{i}. {title}</strong> ({status})"
        if detail:
            item += f"<br>{detail}"
        item += "</li>"
        step_items.append(item)

    steps_html = "\n".join(step_items)
    status_html = ""
    if status_label:
        status_html = f"<h2>状态</h2>\n<p>{html.escape(status_label)}</p>\n"
    footer = (
        "本页为工作计划简要说明，仅供查阅。"
        "如需修改步骤或目标，请在对话框中直接提出修改意见，不要改本文件。"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>工作计划</title>
</head>
<body>
<h1>工作计划</h1>
{status_html}<h2>目标</h2>
<p>{goal}</p>
<h2>步骤</h2>
<ol>
{steps_html}
</ol>
<footer><p>{footer}</p></footer>
</body>
</html>
"""
