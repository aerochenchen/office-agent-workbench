from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

PLAN_REL = ".office-agent/work/plan.json"

PLAN_STATUSES = frozenset({"active", "completed", "blocked", "cancelled"})
STEP_STATUSES = frozenset({"pending", "in_progress", "done", "failed", "skipped"})


class PlanValidationError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_plan(data: dict) -> dict:
    if not isinstance(data, dict):
        raise PlanValidationError("plan must be a dict")

    if data.get("version") != 1:
        raise PlanValidationError("version must be 1")

    status = data.get("status")
    if status not in PLAN_STATUSES:
        raise PlanValidationError(f"invalid plan status: {status!r}")

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
    updated = copy.deepcopy(plan)
    updated["status"] = status
    updated["updated_at"] = _now_iso()
    return validate_plan(updated)
