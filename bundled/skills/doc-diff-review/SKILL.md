---
name: doc-diff-review
display_name: 文稿对照
description: 两版 docx 结构化对比并解读主要改动；可按条款聚类对照范本。
version: 1.0.0
tier: light
permissions:
  - workspace_read
  - workspace_write
  - run_python
shared_scripts:
  - docx_diff
category: productivity
trigger_phrases:
  - 两版对比
  - 两版对照
  - 条款对照
  - 对照范本
  - 列出主要改动
  - 两版对比，列出主要改动
  - 对照范本看条款改了哪些
target_file_type: .docx
---

# 文稿对照

对两份 `.docx` 做段落级结构化对比，再解读为可读的审校说明。条款模式按标题聚类。

## 何时用 / 不用

- **用**：两版对比、列出主要改动；对照范本看条款改了哪些。
- **不用**：单稿校对（走 `doc-proofread`）；排版（走 `government-document-format`）。

## 输入与产出

```
旧版.docx / 新版.docx（或 范本.docx / 修订稿.docx）
.office-agent/work/doc-diff-review/diff.json
output/对照审校.md
```

## 四步纪律（必须按序）

### Step 1 — 确认两路径（Agent，1 步）

明确旧版（或范本）与新版（或修订稿）的工作区相对路径。缺一则 `ask_user` 一次。

### Step 2 — 跑结构化 diff（脚本，1 步）

```
run_shared_script
  name: docx_diff
  args: [<旧.docx>, <新.docx>, --out, .office-agent/work/doc-diff-review/diff.json]
```

向用户报告 `summary`（add/delete/replace）与 `warnings`（如有表格未细比）。

### Step 3 — 解读改动（Agent，约 2～4 步）

`workspace_read` 读取 diff JSON，写 `output/对照审校.md`：

**默认模式（两版对比）**

1. 首页：文件名、改动统计、warnings
2. 「主要改动」：按重要性列出；每条注明 `op`、`old_para`/`new_para`、原文/新文摘要
3. 可附「次要/措辞微调」折叠列表（简写）

**条款模式**（用户说「条款」「范本」）

1. 以两侧像条款标题的段落（如「一、」「（一）」「第×条」）为锚，将邻近 replace/add/delete 归入该条款
2. 输出表格或分级列表：条款标题 | 改动类型 | 摘要
3. 仍须能回溯到 diff 中的 `op` + 段落 index

### Step 4 — 收尾（Agent，1 步）

`finish` 时给出 `output/对照审校.md` 与 diff JSON 路径；提醒表格改动可能未完全覆盖。

## 步数预算

| 阶段 | 约计 |
|------|------|
| 确认 + diff | 2 |
| 解读成文 | 2～4 |
| **合计** | **≈4～6** |

## 硬规则

1. **必须先跑 `docx_diff`**，禁止凭记忆空口对比两篇全文。
2. 报告中的每条主要改动须能对应 JSON 里至少一条 `changes[]`。
3. 不把未改动段落写成「已修改」。
4. 交付在 `output/`；diff JSON 在 `.office-agent/work/doc-diff-review/`。

## 变更记录

- 1.0.0 — Wave1：共享脚本 docx_diff + Agent 解读
