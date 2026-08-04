---
name: doc-proofread
display_name: 通篇校对
description: 对工作区文稿做称谓/数字/术语/口径校对与红笔找茬，产出带定位的校对报告。
version: 1.0.0
tier: light
permissions:
  - workspace_read
  - workspace_write
category: productivity
trigger_phrases:
  - 通篇校对
  - 校对术语
  - 术语统一
  - 红笔找茬
  - 站在审稿领导的角度
  - 通篇校对术语、数字和称谓
  - 把文中的单位名称和术语统一一遍
target_file_type: .docx
---

# 通篇校对

面向机关文稿：通篇校对、术语统一、红笔找茬。产出**带定位**的问题清单，禁止空泛批评。

## 何时用 / 不用

- **用**：用户要对已有稿「校对」「统一术语/称谓」「站在审稿领导角度找站不住的地方」。
- **不用**：只改版式（走 `government-document-format`）；两版对比（走 `doc-diff-review`）；从零起草（走写作类技能）。

## 输入与产出

```
用户指定的 .docx（或文件夹内唯一稿）
.office-agent/glossary.md          # 可选：单位术语/称谓/禁写口径
.office-agent/work/doc-proofread/  # 过程摘录（可选）
工作成果/校对报告.md                 # 必交
工作成果/校对批注要点.md             # 可选：按严重度精简给领导看
```

## 四步纪律（必须按序）

### Step 1 — 定位文稿（Agent，1 步）

确认目标 `.docx` 路径。缺路径时用 `ask_user` **一次**；可用 `workspace_list` 自查。

### Step 2 — 按段抽取（工具，1 步）

```
workspace_extract
  path: <docx相对路径>
  granularity: paragraph
  max_units: 200
```

向用户确认非空段数量；若 truncated，说明将分批审读或请用户缩小范围。

### Step 3 — 读取口径（可选，1 步）

若存在 `.office-agent/glossary.md`，`workspace_read` 通读；术语/称谓/口径类问题**必须**对照该文件。不存在则跳过，并在报告首页注明「未提供 glossary」。  
单位可复制本技能 `references/glossary.example.md` 到工作区改名使用。

### Step 4 — 写校对报告（Agent，约 2～4 步）

写入 `工作成果/校对报告.md`，结构：

```markdown
# 校对报告

- 源文件：…
- glossary：有 / 无
- 抽查单元数：…

## 问题清单

### 1. [称谓|数字|标点|术语|口径|逻辑追问]
- **定位**：`unit_id` 或 `p{para_idx}`（locator）
- **原文**：不超过 80 字摘要
- **问题**：…
- **建议**：…
```

可选再写 `工作成果/校对批注要点.md`（只保留高优先级 5～15 条）。

**红笔模式**（用户说「红笔」「审稿领导」「站不住」）：侧重逻辑追问、论据不足、易被追问处；仍须每条带定位。

**术语统一模式**：列出同义混用，给出推荐统一写法（优先 glossary）。

## 步数预算

| 阶段 | 约计 |
|------|------|
| 定位 + 抽取 + glossary | 2～3 |
| 写报告 | 2～4 |
| **合计** | **≈4～7** |

超长文：按 `unit_id` 分批写入过程笔记再合并；禁止一次丢弃定位。

## 硬规则

1. **每条问题必须有定位**（`unit_id` 或 `meta.para_start` / locator 中的 `pN`）；无定位条目视为不合格，删掉重写。
2. 不编造文中不存在的句子；原文摘要须来自抽取单元。
3. 有 glossary 时，不得与已约定术语冲突而不说明。
4. 最终交付在 `工作成果/`；过程文件在 `.office-agent/work/doc-proofread/`。

## 变更记录

- 1.0.0 — Wave1：校对 / 术语 / 红笔合一 skill
