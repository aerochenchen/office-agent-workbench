# Agent Plan + 执行（Phase 1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Runtime 落地通用 Plan 工件与 `plan_*` 工具，并写入 system 纪律，使复杂任务可分步执行、中断后续跑。

**Architecture:** 新增 `office_agent/plan_store.py` 负责 schema 校验与 `.office-agent/work/plan.json` 读写；`ToolExecutor` 暴露 `plan_get` / `plan_create` / `plan_update_step` / `plan_set_status`；`agent_loop` 注入触发与续跑纪律。领域逻辑不进底座。P2/P3（guide 话术、UI）不在本计划。

**Tech Stack:** Python 3.11+、现有 `Workspace` / `ToolExecutor` / `agent_loop`、pytest

**Spec:** `docs/superpowers/specs/2026-08-04-agent-plan-execute-design.md`

## Global Constraints

- Plan 权威路径固定为 `.office-agent/work/plan.json`（经 Workspace 沙箱）
- Schema `version` 必须为 `1`；步骤 ≥2；至多一个 `in_progress`
- 不上多 Agent；不取消 `max_tool_steps`
- 简单任务不强制建 Plan（仅 prompt 纪律 + 评测说明，不做运行时拦截）
- 对用户文案称「工作计划」，路径对模型可用技术名
- 提交信息用简体中文或英文 feat 前缀均可，与仓库近期风格一致；本计划示例用英文 feat

## File map

| 文件 | 职责 |
|------|------|
| `runtime/src/office_agent/plan_store.py` | Plan 常量、校验、load/save、步进更新纯函数 |
| `runtime/src/office_agent/tools.py` | 注册并实现四个 `plan_*` handler |
| `runtime/src/office_agent/agent_loop.py` | `TOOL_SCHEMAS`、`TOOL_LABELS`、system 纪律、`result_summary` |
| `runtime/src/office_agent/permissions.py` | `plan_get` 只读；其余写入类进 `RISKY_TOOLS` |
| `runtime/tests/test_plan_store.py` | schema / 依赖 / in_progress 规则 |
| `runtime/tests/test_plan_tools.py` | ToolExecutor 集成 |
| `runtime/tests/test_agent_loop.py` | schema 名列表含 plan_* |
| `docs/superpowers/evals/fixtures/plan-resume/README.md` | 人工/后续 AB 评测说明 |
| `docs/superpowers/specs/2026-08-04-agent-plan-execute-design.md` | 状态改为实施中 |

---

### Task 1: `plan_store` 纯逻辑

**Files:**
- Create: `runtime/src/office_agent/plan_store.py`
- Test: `runtime/tests/test_plan_store.py`

**Interfaces:**
- Produces:
  - `PLAN_REL = ".office-agent/work/plan.json"`
  - `PLAN_STATUSES`, `STEP_STATUSES` frozensets
  - `validate_plan(data: dict) -> dict` — 返回规范化副本或 raise `PlanValidationError`
  - `load_plan(path: Path) -> dict | None`
  - `save_plan(path: Path, data: dict) -> None` — 先 validate
  - `apply_step_update(plan: dict, step_id: str, *, status: str | None = None, notes: str | None = None, outputs: list[str] | None = None) -> dict` — 返回新 plan dict
  - `set_plan_status(plan: dict, status: str) -> dict`
  - `PlanValidationError(ValueError)`

- [ ] **Step 1: Write failing tests**

```python
# runtime/tests/test_plan_store.py
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
```

- [ ] **Step 2: Run tests — expect fail**

Run: `cd runtime && python -m pytest tests/test_plan_store.py -v`  
Expected: `ModuleNotFoundError` or import error for `office_agent.plan_store`

- [ ] **Step 3: Implement `plan_store.py`**

实现要点（须全部满足测试）：

- `PlanValidationError`
- 校验：`version==1`；`status`/`steps[].status` 枚举；`len(steps)>=2`；step `id` 唯一；`depends_on` 均存在；`in_progress` 计数 ≤1；若某步 `in_progress|done` 则其依赖必须为 `done|skipped`
- `apply_step_update`：拷贝后改字段；改 status 时重新 validate；若所有 step 为 `done|skipped` 则 `status="completed"`；刷新 `updated_at`（可用 `datetime.now(timezone.utc).isoformat()`）
- `save_plan`：`validate_plan` 后 `path.parent.mkdir(parents=True, exist_ok=True)`，`json.dump(..., ensure_ascii=False, indent=2)`
- `load_plan`：文件不存在返回 `None`；存在则 `json.loads` + `validate_plan`

- [ ] **Step 4: Run tests — expect pass**

Run: `cd runtime && python -m pytest tests/test_plan_store.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**（仅当用户要求提交时执行；否则跳过）

```bash
git add runtime/src/office_agent/plan_store.py runtime/tests/test_plan_store.py
git commit -m "$(cat <<'EOF'
feat: add plan_store validation and step updates

EOF
)"
```

---

### Task 2: 注册 `plan_*` 工具

**Files:**
- Modify: `runtime/src/office_agent/tools.py`
- Modify: `runtime/src/office_agent/permissions.py`
- Modify: `runtime/src/office_agent/agent_loop.py`（`TOOL_SCHEMAS`、`TOOL_LABELS`、`args_summary`/`result_summary`）
- Test: `runtime/tests/test_plan_tools.py`
- Modify: `runtime/tests/test_agent_loop.py`（工具名集合断言）

**Interfaces:**
- Consumes: `plan_store` 全部公开 API；`ToolExecutor.workspace.root`
- Produces: handlers 返回 `{"ok": bool, ...}`；`plan_get` 缺文件时 `{"ok": false, "reason": "missing"}`

- [ ] **Step 1: Write failing tool tests**

```python
# runtime/tests/test_plan_tools.py
from __future__ import annotations

from pathlib import Path

from office_agent.audit import AuditLog
from office_agent.plan_store import PLAN_REL
from office_agent.skills import SkillRegistry
from office_agent.tools import ToolExecutor
from office_agent.workspace import Workspace


def _executor(tmp_path: Path) -> ToolExecutor:
    ws = Workspace(tmp_path)
    ws.ensure_layout()
    skills = SkillRegistry(tmp_path / "skills")
    skills.skills_dir.mkdir(parents=True, exist_ok=True)
    return ToolExecutor(ws, skills, audit=AuditLog(tmp_path / "audit.jsonl"))


def test_plan_create_and_get(tmp_path: Path):
    ex = _executor(tmp_path)
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
    assert (tmp_path / PLAN_REL).is_file()
    got = ex.execute("plan_get", {})
    assert got["ok"] is True
    assert got["plan"]["goal"] == "分两步处理材料"
    assert len(got["plan"]["steps"]) == 2


def test_plan_create_rejects_second_active(tmp_path: Path):
    ex = _executor(tmp_path)
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


def test_plan_update_and_complete(tmp_path: Path):
    ex = _executor(tmp_path)
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
```

- [ ] **Step 2: Run — expect fail**（unknown tool）

Run: `cd runtime && python -m pytest tests/test_plan_tools.py -v`  
Expected: FAIL `unknown tool: plan_create` 或类似

- [ ] **Step 3: Implement tools + permissions + schemas**

`permissions.py`：

- `READ_ONLY_TOOLS` 增加 `"plan_get"`
- `RISKY_TOOLS` 增加 `"plan_create"`, `"plan_update_step"`, `"plan_set_status"`

`tools.py` handlers 行为：

- `plan_get`：`load_plan(workspace.root / PLAN_REL)`；None → `ok:false, reason:"missing"`
- `plan_create`：若已有 active plan → error；否则组装完整 plan（补默认字段、`id` 用 `uuid.uuid4().hex` 前缀 `plan_`、时间戳），`save_plan`
  - args：`goal: str`（必填），`steps: list`（每项至少 `id`,`title`；其余可选），可选 `resume_hint`
- `plan_update_step`：load → `apply_step_update` → save；缺 plan 则 error
- `plan_set_status`：load → `set_plan_status` → save；用于 `cancelled` / `blocked` / 手动 `completed`

`agent_loop.py`：为四工具补充 `TOOL_SCHEMAS` 与中文 `TOOL_LABELS`；在 `args_summary` / `result_summary` 中给出短摘要（goal / step_id / status）。

更新 `test_agent_loop.py` 中工具名集合，包含四个 `plan_*`。

- [ ] **Step 4: Run tests**

Run: `cd runtime && python -m pytest tests/test_plan_tools.py tests/test_plan_store.py tests/test_agent_loop.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**（仅当用户要求时）

```bash
git add runtime/src/office_agent/tools.py runtime/src/office_agent/permissions.py \
  runtime/src/office_agent/agent_loop.py runtime/tests/test_plan_tools.py \
  runtime/tests/test_agent_loop.py
git commit -m "$(cat <<'EOF'
feat: add plan_get/create/update_step/set_status tools

EOF
)"
```

---

### Task 3: System 纪律

**Files:**
- Modify: `runtime/src/office_agent/agent_loop.py` — `_build_system_prompt`
- Test: `runtime/tests/test_agent_loop.py`（断言 prompt 含关键句）

**Interfaces:**
- Consumes: 无新符号
- Produces: system 字符串含 Plan 纪律段落

- [ ] **Step 1: Write / extend test**

```python
def test_system_prompt_includes_plan_discipline():
    from office_agent.agent_loop import _build_system_prompt

    text = _build_system_prompt([])
    assert "plan_create" in text
    assert "工作计划" in text
    assert "按工作计划" in text or "继续" in text
```

- [ ] **Step 2: Run — may fail on missing strings**

Run: `cd runtime && python -m pytest tests/test_agent_loop.py::test_system_prompt_includes_plan_discipline -v`

- [ ] **Step 3: Append discipline block to `_build_system_prompt`**

在「执行纪律」或独立「工作计划纪律」段落入（措辞可微调，但须覆盖）：

1. 复杂/大批量/用户要求分步时先 `plan_create`，再执行  
2. 有 active plan 时先 `plan_get`，每轮只推进一个可执行步骤  
3. 用户说继续时禁止无故重规划  
4. `finish` 时若未完成须说明剩余项并提示按工作计划继续  
5. 单文件校对、两版对照、单一排版等简单任务不强制建 Plan  
6. 业务产出仍写 `output/`，Plan 只管家务状态  

- [ ] **Step 4: Run related tests PASS**

- [ ] **Step 5: Commit**（仅当用户要求时）

```bash
git add runtime/src/office_agent/agent_loop.py runtime/tests/test_agent_loop.py
git commit -m "$(cat <<'EOF'
feat: add plan-execute discipline to system prompt

EOF
)"
```

---

### Task 4: 续跑评测夹具说明 + 规格状态

**Files:**
- Create: `docs/superpowers/evals/fixtures/plan-resume/README.md`
- Create: `docs/superpowers/evals/fixtures/plan-resume/seed-plan.json`（4 步示例，s1/s2 已 done，s3/s4 pending）
- Modify: `docs/superpowers/specs/2026-08-04-agent-plan-execute-design.md` — 状态改为「实施中」
- Modify: `docs/superpowers/evals/scorecard.md` — 增一行 P-Plan 续跑（列可留空）

- [ ] **Step 1: Write fixture README**

说明人工/后续 AB 步骤：

1. 打开空文件夹，将 `seed-plan.json` 复制为 `.office-agent/work/plan.json`  
2. 在 `output/` 放置两份占位已完成说明（可选）  
3. 话术：`按工作计划未完成项继续`  
4. 金标：Agent 调用 `plan_get`，推进 s3 而非重建 Plan；最终 plan `completed` 或剩余项减少  

`seed-plan.json` 须通过 `validate_plan`（4 步，前两 done）。

- [ ] **Step 2: 本地校验 seed**

```bash
cd runtime && python -c "
from pathlib import Path
from office_agent.plan_store import validate_plan
import json
p=Path('../docs/superpowers/evals/fixtures/plan-resume/seed-plan.json')
validate_plan(json.loads(p.read_text(encoding='utf-8')))
print('ok')
"
```

Expected: `ok`

- [ ] **Step 3: 更新 scorecard 与规格状态行**

- [ ] **Step 4: Commit**（仅当用户要求时）

```bash
git add docs/superpowers/evals/fixtures/plan-resume \
  docs/superpowers/specs/2026-08-04-agent-plan-execute-design.md \
  docs/superpowers/evals/scorecard.md
git commit -m "$(cat <<'EOF'
docs: add plan-resume eval fixture and mark plan-execute in progress

EOF
)"
```

---

### Task 5: Self-review 与回归

- [ ] **Step 1: 跑 Runtime 相关测试**

Run: `cd runtime && python -m pytest tests/test_plan_store.py tests/test_plan_tools.py tests/test_agent_loop.py tests/test_tools.py tests/test_permissions.py -v`  
Expected: PASS

- [ ] **Step 2: 对照规格 §9.1 勾选**

| §9.1 | 对应 |
|------|------|
| 非法写入拒绝 | Task 1 |
| active 不可静默覆盖 | Task 2 |
| depends_on / 单一 in_progress | Task 1 |
| 续跑夹具 | Task 4（人工金标；自动化到 tool 层即可） |
| 简单任务不强制 | Task 3 prompt |
| 不回归 max_steps | 未改 config |

- [ ] **Step 3: 扫描计划文件无 TBD/TODO 占位**

---

## Post-Phase 1（不在本计划编码）

| 阶段 | 内容 | 新计划文件 |
|------|------|------------|
| P2 | guide「继续工作计划」；`finish` 摘要约定加固；可选 `output/工作计划.md` | 另开 `2026-08-XX-agent-plan-execute-p2.md` |
| P3 | UI 只读进度 | 另开 |
| P4 | 领域 Skill 模板（如规章审查） | 业务单独立项 |

---

## Self-Review（写计划时）

1. **Spec coverage：** §5 schema → Task1；§6 tools → Task2；§6.3/§7 纪律与续跑 → Task3+4；§9.1 → Task5。§8 P2+ 明确排除。  
2. **Placeholder scan：** 无 TBD。  
3. **Type consistency：** `PLAN_REL`、四工具名、`PlanValidationError` 前后一致。
