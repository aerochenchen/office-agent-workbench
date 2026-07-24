# Task 11 Report: License scan & packaging docs (partial)

**Status:** DONE | **Commits:** none | **Date:** 2026-07-23

## Delivered

- `packaging/README-standard.md` — 标准底座内容、4GB 基线、无 Torch。
- `packaging/README-writing-rag-optional.md` — 可选写作/RAG 包、8GB、离线模型与 zip 导入步骤。
- `scripts/check_licenses.sh` — 在 `runtime/.venv` 安装/调用 `pip-licenses`，`--fail-on` GPL/AGPL。
- `apps/desktop` 设置弹窗底部简短 About/NOTICE（Tauri、React、FastAPI、openai SDK）。

## Verify

`./scripts/check_licenses.sh` — **exit 0**，输出 `OK: no GPL/AGPL (pip-licenses --fail-on).`

## Out of scope (this slice)

- 断公网 smoke、Task 10 可选 Skill 实体未在本任务创建。
