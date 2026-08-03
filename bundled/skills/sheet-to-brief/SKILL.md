---
name: sheet-to-brief
display_name: 表格成文
description: 用工作区表格写情况说明或数据结论，或按空白表用材料填报并列出缺口。
version: 1.0.0
tier: light
permissions:
  - workspace_read
  - workspace_write
category: productivity
trigger_phrases:
  - 表写情况说明
  - 数据结论
  - 按表填报
  - 用这张表写一段情况说明
  - 解读这张表，写出几条主要结论
  - 按这个空白表，用文件夹里的材料填好
target_file_type: .xlsx
---

# 表格成文

三种模式：**情况说明**、**数据结论**、**按表填报**。定量表述必须能指回单元格（如 `汇总!B3`）。

## 何时用 / 不用

- **用**：用表写情况说明；解读表写结论；按空白表从文件夹材料填报。
- **不用**：公文红头排版（走 `government-document-format`）；纯 Word 校对（走 `doc-proofread`）。

## 输入与产出

```
用户指定的 .xlsx / .xls
.office-agent/work/sheet-to-brief/   # 过程摘录（可选）
output/情况说明.md                   # 模式 A
output/数据结论.md                   # 模式 B
output/<填报结果>.xlsx 或 .md        # 模式 C
output/填报缺口.md                   # 模式 C 必交
```

## 四步纪律（必须按序）

### Step 1 — 定位表格（Agent，1 步）

确认目标表路径。缺路径时 `ask_user` **一次**。

### Step 2 — 单元格级抽取（工具，1 步）

```
workspace_extract
  path: <xlsx相对路径>
  granularity: cells
  max_units: 400
```

向用户报告工作表名、非空单元格约数；若 truncated，说明将聚焦首表或请用户缩小范围。

### Step 3 — 按模式成文（Agent，约 2～5 步）

**A. 情况说明** → `output/情况说明.md`

- 用正式公文口吻写 1～3 段
- 凡数字/比例/排名，句末或括号标注来源定位，如 `（汇总!B3）`
- 无定位的定量句禁止写入

**B. 数据结论** → `output/数据结论.md`

```markdown
# 数据结论

1. …（来源：`汇总!B3`）
2. …
```

每条结论一句；必须带来源定位。

**C. 按表填报**

1. 识别空白表中待填字段（空单元格或表头对应空列）
2. 用 `workspace_list` / `workspace_extract` / `workspace_read` 从文件夹材料找依据
3. 能填的写入说明文档或生成填报结果；**不能填的**列入 `output/填报缺口.md`：

| 字段/单元格 | 需要的信息 | 已查材料 | 缺口说明 |
|-------------|------------|----------|----------|
| … | … | … | … |

禁止把猜测值填成确定数。

### Step 4 — 收尾（Agent，1 步）

`finish` 给出路径；提醒用户核对单元格引用是否与源表一致。

## 步数预算

| 模式 | 约计 |
|------|------|
| 情况说明 / 结论 | ≈4～6 |
| 按表填报 | ≈6～10 |

## 硬规则

1. **必须先 `granularity=cells` 抽取**，禁止凭记忆报数。
2. 定量表述无单元格定位 → 不合格，删掉或改为定性表述。
3. 填报不得捏造材料中不存在的数据。
4. 交付在 `output/`。

## 变更记录

- 1.0.0 — Wave2：情况说明 / 结论 / 填报
