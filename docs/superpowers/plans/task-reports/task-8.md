# Task 8 Report: Bundle light format skill stub

**Status:** DONE | **Commits:** none | **Date:** 2026-07-23

## Delivered

- `bundled/shared-scripts/format_gongwen.py` — 占位脚本，打印 argv。
- `bundled/skills/government-document-format/SKILL.md` — `tier: light`，`shared_scripts: [format_gongwen]`。
- `runtime/src/office_agent/bundled_seed.py` — `seed_bundled_assets()`：缺失时从 `bundled/`（或 `OFFICE_AGENT_BUNDLED`）复制到 `app_data`。
- `runtime/src/office_agent/app.py` — FastAPI `lifespan` 启动时调用 seed。
- `runtime/tests/test_bundled_seed.py` — `TestClient` 启动后 `/skills` 含 `government-document-format`，且 `shared-scripts/format_gongwen.py` 存在。

## Verify

`pytest tests/test_bundled_seed.py -v` — **PASSED**。
