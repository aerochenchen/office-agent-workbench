# 文书通能力强化 · Wave 3 Implementation Plan

> **For agentic workers:** Use subagent-driven-development or executing-plans. Checkbox tracking below.

**Goal:** 一文三用编排 + 汇报成套（提纲 / PPT / 讲稿）；预置；薄底座。

**Spec:** `docs/superpowers/specs/2026-08-03-capability-quality-wave3-design.md`

## Status

- [x] Design short doc
- [x] one-to-three
- [x] brief-deck + build_pptx.py
- [x] BUNDLED_SKILL_IDS + packaging + system prompt + 一页纸

## Verification

```bash
cd runtime && python3 -m pytest tests/test_bundled_seed.py -q
cd apps/desktop && npm test -- --run src/lib/skillUtils.test.ts
```
