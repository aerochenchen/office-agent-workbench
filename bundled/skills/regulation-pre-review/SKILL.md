---
name: regulation-pre-review
display_name: 制度发布前审查
description: 规章发布前按22条要点审查，产出审查报告与底稿。
version: 1.0.0
tier: light
permissions:
  - workspace_read
  - workspace_write
  - run_python
category: productivity
trigger_phrases:
  - 审查这个制度
  - 发布前审查
  - 规范制度审查
  - 填审查报告
  - 附件1
target_file_type: .docx
---

# 制度发布前审查

把一份待发布的规章按附件 1 的 22 条要点逐条审出结论和修改意见，并写成可送签的审查报告。不替代法定审查，签字栏留白。

执行前按需读取：

- 输入与缺项：[references/01-inputs.md](references/01-inputs.md)
- 22 条判定口径：[references/02-review-points.md](references/02-review-points.md)
- 结论措辞：[references/03-writing-rules.md](references/03-writing-rules.md)
- 表格字段：[references/04-form-spec.md](references/04-form-spec.md)

## 何时用 / 何时不用

- **用**：用户要「审查这个制度」「发布前审查」「填审查报告」「附件1」，或给出一份待发布规章，要求做合法性、合理性、可操作性、规范性审查。
- **不用**：只校对错字术语（走 `doc-proofread`）；两版对照（走 `doc-diff-review`）；只改公文版式（走 `government-document-format`）。

## 输入与产出

```
规章全文.docx / .pdf / .md / .txt          # 必需，最终稿
上位依据、现行制度目录、职责、征求意见、会商纪要   # 强烈建议，缺则对应要点写「待补」
.office-agent/work/regulation-pre-review/取稿.txt
.office-agent/work/regulation-pre-review/review.json
工作成果/《规章名》发布前审查报告.xlsx       # 必交
工作成果/《规章名》审查底稿.md               # 必交
```

需要纸质版时，打开 xlsx，用 Excel 或 WPS 另存 PDF。脚本不导出 PDF。

## 五步纪律（必须按序）

### Step 1 — 定位文稿（Agent，1 步）

确认规章路径、名称、审查方式（审查会 / 自查）、审查日期。缺名称时用正文标题。缺审查方式时按自查出表，并告诉用户。缺路径时 `ask_user` **一次**。

### Step 2 — 取稿（脚本或抽取，1 步）

Word 用脚本，保留交叉引用里的法律名称：

```
run_skill_script
  skill_id: regulation-pre-review
  script: extract_docx.py
  args: ["<规章.docx>", "-o", ".office-agent/work/regulation-pre-review/取稿.txt"]
```

PDF、md、txt 用 `workspace_extract` 或 `workspace_read`。抽取被截断时，分批写入取稿文件，不要只审开头。

### Step 3 — 读口径（Agent，2 步）

`read_skill` 读取 `references/02-review-points.md` 和 `references/03-writing-rules.md`。有上位依据或制度目录时一并读入。缺哪类材料，对应要点走「待补」，禁止臆断法条、文号、文件名。

### Step 4 — 逐条研判并写 JSON（Agent，约 3～6 步）

按 02 的口径过 1—22 条。先判「不符合」，再判「基本符合」，其余「符合」。同一问题只记在一条上。

用 `workspace_write` 写入 `.office-agent/work/regulation-pre-review/review.json`。结构见 04，也可对照 `assets/templates/review_data.template.json`。`items` 必须 22 条且顺序固定。`signoff` 的签字留空。缺项写入 `pending_inputs`。

### Step 5 — 出表（脚本，1 步）

```
run_skill_script
  skill_id: regulation-pre-review
  script: build_report.py
  args: [
    ".office-agent/work/regulation-pre-review/review.json",
    "-o", "工作成果/《规章名》发布前审查报告.xlsx",
    "--draft", "工作成果/《规章名》审查底稿.md"
  ]
```

看 stdout 的 JSON：`ok` 为真，且 `items` 为 22。然后 `finish`，`deliverables` 列出这两个路径。

## 定结论

只要出现一条实质性「不符合」（越权、与上位法冲突、与现行制度硬冲突），`result` 取 `fail`（审查不通过）。仅表述类问题取 `pass`（审查通过），并在意见栏注明修改。表内仍有「待补」时，不要直接定 `pass`。

## 步数预算

| 阶段 | 约计步数 |
|------|----------|
| 定位 + 取稿 + 读口径 | 4 |
| 写 review.json | 3～6 |
| 出表 | 1 |
| **合计** | **≈8～11** |

规章特别长时，本轮只完成取稿和前 11 条，把已判定内容写入 `review.json` 草稿；下一轮从该文件续写后 11 条再出表。

## 硬规则

- 22 条全部有结论。结论只用：`符合` / `基本符合` / `不符合` / `不适用` / `待补`
- 「不符合」「基本符合」必须同时给出：条款定位 + 问题 + 改法。改法用祈使句：「建议删除……」「建议改为……」
- 条款定位写 `第X条`、`第X条第Y款`、`第X章`。引用原文加「」，不整段照抄
- 依据不确定时写「需核对《××》相应条款」，并列入 `pending_inputs`
- 审查报告中的修改意见是给起草部门的
- 报告版面只走 `scripts/build_report.py`。禁止手画表格、改列宽字号，禁止调用 Excel 或导出 PDF
- 签字栏留空，由人工签署

## 变更记录

- 1.0.0 — 适配文书通：22 条研判仍由模型完成，xlsx 与底稿由技能脚本写出；不再自带离线 wheel，不再经 Excel 导出 PDF
