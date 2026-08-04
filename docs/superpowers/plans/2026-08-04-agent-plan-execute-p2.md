# Agent Plan + 执行（Phase 2）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 复杂任务新建工作计划后先给人看并确认，再执行；续跑可发现；finish 摘要含剩余项。

**Architecture:** 扩展 `plan_store` 的 `approval` 字段与硬闸；新增 `plan_set_approval` + `render_plan_html`（写入 `工作成果/工作计划.html`，静态简要说明）；收紧 `plan_update_step`；更新 system 纪律（改计划仅对话）；guide 增加续跑叶子。不上 UI 面板（P3）。

**Tech Stack:** 现有 Python runtime、`guide.ts`、pytest / 前端既有测试习惯

**Spec:** `docs/superpowers/specs/2026-08-04-agent-plan-execute-design.md` §5.2 / §6.1.1 / §6.3 P2 / **§6.4** / §7 / §9.2

## Global Constraints

- 权威 Plan 仍为 `.office-agent/work/plan.json`；`工作成果/工作计划.html` 仅为查阅用简要说明
- 新计划默认 `approval=pending`；缺省旧文件按 `approved` 兼容
- 未 `approved` 禁止 step → `in_progress`/`done`
- 确认关：复杂新建必确认；续跑与「不用确认」跳过；简单任务不建 Plan
- **改计划只走对话框**；不解析、不同步用户对手改 HTML（规格 §6.4）
- HTML：转义文本、无脚本；页内固定「如需修改请在对话框提出」
- 对用户文案称「工作计划」；工具名可保留 `plan_*`
- 不上多 Agent；不改 `max_tool_steps` 默认值；不做 P3 UI
- **不做** MD 双写、展示文件↔JSON 漂移检测

## File map

| 文件 | 职责 |
|------|------|
| `runtime/src/office_agent/plan_store.py` | `approval`、硬闸、`render_plan_html`、`set_plan_approval` |
| `runtime/src/office_agent/tools.py` | create 默认 pending + 写 html；`plan_set_approval` |
| `runtime/src/office_agent/permissions.py` | `plan_set_approval` 进 RISKY |
| `runtime/src/office_agent/agent_loop.py` | schemas；确认关 + 仅对话修改；ask_user 放宽 |
| `runtime/tests/test_plan_store.py` 等 | §9.2 |
| `apps/desktop/src/lib/guide.ts` | 「继续工作计划」 |
| `docs/superpowers/evals/fixtures/plan-resume/README.md` | 确认关说明 |

---

### Task 1: `approval` + 硬闸 + HTML 渲染（plan_store）

**Files:**
- Modify: `runtime/src/office_agent/plan_store.py`
- Test: `runtime/tests/test_plan_store.py`

**Interfaces:**
- Produces:
  - `APPROVAL_STATUSES = frozenset({"pending", "approved", "rejected"})`
  - `PLAN_HTML_REL = "工作成果/工作计划.html"`
  - `effective_approval(plan) -> str` — 缺省 → `"approved"`
  - `set_plan_approval(plan, approval: str, *, cancel_if_rejected: bool = True) -> dict`
  - `render_plan_html(plan) -> str` — 静态 HTML；含目标、步骤、页脚修改说明；对用户文本 `html.escape`
  - `apply_step_update`：若新 status ∈ {in_progress, done} 且未 approved → `PlanValidationError`（match `approval`）

- [ ] **Step 1: Failing tests**（至少含 effective_approval / pending 硬闸 / approved 可推进 / render 含目标与「对话框」修改说明 / `<script` 不出现且 escape `<`）

```python
def test_render_plan_html_escapes_and_footer():
    from office_agent.plan_store import render_plan_html
    plan = validate_plan({**_minimal_plan(), "goal": "A <B> & C", "approval": "pending"})
    html = render_plan_html(plan)
    assert "A &lt;B&gt; &amp; C" in html
    assert "<script" not in html.lower()
    assert "对话框" in html
```

- [ ] **Step 2: pytest RED** → **Step 3: Implement** → **Step 4: GREEN**
- [ ] **Step 5: Commit** `feat: add plan approval gate and HTML brief render`

---

### Task 2: 工具层 — create 写 HTML、`plan_set_approval`

**Files:**
- Modify: `tools.py` / `permissions.py` / `agent_loop.py`（schemas）
- Test: `test_plan_tools.py`

行为：
- `plan_create` → `approval=pending` + 写入 `工作成果/工作计划.html`
- `plan_set_approval`：approved / rejected（rejected→cancelled）；刷新 html
- 用户「不用确认」：create 后立即 `plan_set_approval(approved)`，不 ask_user

- [ ] Tests：create 出 pending+html；未批准 step 失败；批准后可 step；rejected 取消
- [ ] Commit `feat: plan_set_approval and write 工作计划.html on create`

---

### Task 3: System 纪律

**Files:** `agent_loop.py` + `test_agent_loop.py`

纪律须含：确认关；`工作计划.html` 仅供查阅；**修改只在对话框提出**；忽略对手改展示文件的期望；续跑/跳过确认规则；`needs_user`；ask_user 用途放宽。

- [ ] Prompt 断言含 `plan_set_approval`、`工作计划.html`、`对话框`、`needs_user`
- [ ] Commit `feat: enforce plan confirmation and dialog-only edits in prompt`

---

### Task 4: Guide「继续工作计划」

- `guide.ts` 增加 leaf：`saying: "按工作计划未完成项继续"`
- [ ] Commit `feat: add continue-work-plan saying to capability guide`

---

### Task 5: 夹具 + 回归

- README：新建须确认；展示为 html；seed 可标 `approval: approved` 直接续跑
- `pytest` plan_store / plan_tools / agent_loop / tools / permissions
- [ ] Commit `docs: clarify plan-resume with HTML brief and confirmation`

---

## Self-Review

1. §9.2 → Tasks 1–5；§6.4 仅对话修改 → Task 3  
2. 无 MD/漂移同步范围  
3. `PLAN_HTML_REL` / `render_plan_html` 命名一致  

## 执行交接

Plan updated at `docs/superpowers/plans/2026-08-04-agent-plan-execute-p2.md`.

**1. Subagent-Driven（推荐）** · **2. Inline Execution** — Which approach?
