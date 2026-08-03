# 文书通能力强化 · Wave 2 Implementation Plan

> **For agentic workers:** Use subagent-driven-development or executing-plans. Checkbox tracking below.

**Goal:** 会议督办、材料摸底/缺料、表格成文闭环；xlsx cells 抽取；glossary 模板；三者预置。

**Spec:** `docs/superpowers/specs/2026-08-03-capability-quality-wave2-design.md`

## Status

- [x] Design short doc
- [x] meeting-followup
- [x] material-gap + inventory.py
- [x] sheet-to-brief
- [x] extract_xlsx granularity=cells
- [x] glossary templates
- [x] BUNDLED_SKILL_IDS + packaging + system prompt

## Verification

```bash
cd runtime && python3 -m pytest tests/test_doc_io.py tests/test_bundled_seed.py -q
cd apps/desktop && npm test -- --run src/lib/skillUtils.test.ts
```
