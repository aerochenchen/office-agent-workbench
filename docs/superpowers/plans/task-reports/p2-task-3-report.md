# P2 Task 3 Report: System 纪律

**Status:** DONE  
**Date:** 2026-08-04

## Scope

- `runtime/src/office_agent/agent_loop.py` — plan confirmation / dialog-only / finish-resume / ask_user priority
- `runtime/tests/test_agent_loop.py` — tightened prompt assertions

## Fix round (Important findings)

- Added ask_user 同轮优先级 line: 缺路径（plan_create 前）> 工作计划确认 > needs_user 留待下一轮
- Strengthened finish/resume assertions: `剩余步骤数或标题列表`, `可按工作计划继续`
- Tightened dialog/skip-confirm assertions: `output/工作计划.html`, `对话框`, `仅供查阅`, `不用确认`, `禁止解析或同步`
- New test: `test_system_prompt_ask_user_priority`

## Test evidence

```bash
cd runtime && .venv/bin/pytest tests/test_agent_loop.py::test_system_prompt_includes_plan_discipline \
  tests/test_agent_loop.py::test_system_prompt_enforces_plan_confirmation_and_dialog_only_edits \
  tests/test_agent_loop.py::test_system_prompt_ask_user_priority -v
```

```text
3 passed
```

## Commits

- `fix: tighten plan confirmation prompt and tests`
