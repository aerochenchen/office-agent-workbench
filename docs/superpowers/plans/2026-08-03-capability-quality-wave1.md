# 文书通能力与材料质量强化 · Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 写作 × 审校 × 汇总质量三角：抽取可定位、对比可结构化、校对带定位、汇总可审计、写作自审落盘、排版可收口。

**Architecture:** 底座增强 `workspace_extract` granularity + 共享脚本 `docx_diff`；新建 light skill `doc-proofread` / `doc-diff-review`；加强 `multidoc-digest` / `gongwen-rag-writing` / `government-document-format`；约定 `.office-agent/glossary.md`。

**Tech Stack:** Python Runtime · pytest · python-docx · Skill 包

**Spec:** `docs/superpowers/specs/2026-08-03-capability-quality-wave1-design.md`

## Global Constraints

- 标准包不含 `gongwen-rag-writing`；不新增 agent tool schema（对比走 shared script）。
- `granularity` 默认 `section`，兼容既有消费方。
- 用户文案：说「文件夹」，禁「工作区」「项目文件夹」（对用户）；内部路径仍可用 `.office-agent`。

---

## Tasks (status)

- [x] Task 0 — 设计短文
- [x] Task 1 — ExtractUnit.meta + granularity
- [x] Task 2 — docx_diff 共享脚本 + 测试
- [x] Task 3 — doc-proofread
- [x] Task 4 — doc-diff-review
- [x] Task 5 — multidoc-digest 审计加强
- [x] Task 6 — gongwen-rag 自审落盘
- [x] Task 7 — government-document-format 收口自检
- [x] Task 8 — system prompt + glossary 约定
- [x] Checkpoint — pytest + 标准包仍不含 RAG

## Verification

```bash
cd runtime && python3 -m pytest tests/test_doc_io.py tests/test_docx_diff.py -v
grep -R "gongwen-rag-writing" packaging/README-standard.md  # 应写明不包含
ls bundled/skills/doc-proofread bundled/skills/doc-diff-review bundled/shared-scripts/docx_diff.py
```
