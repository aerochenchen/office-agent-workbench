---
name: material-gap
display_name: 材料摸底
description: 摸清文件夹材料类型清单，或对照写作题目列出还缺哪些关键材料。
version: 1.0.0
tier: light
permissions:
  - workspace_read
  - workspace_write
  - run_python
category: productivity
trigger_phrases:
  - 文件夹摸底
  - 缺啥补啥
  - 材料清单
  - 还缺哪些材料
  - 看看当前文件夹里有哪些材料，按类型列个清单
  - 对照要写的题目，列出文件夹里还缺哪些关键材料
target_file_type: .docx
---

# 材料摸底

两种模式：**摸底**（按类型列清单）与 **缺料**（对照题目查缺）。确定性列目录用脚本；缺什么靠 Agent 对照题目判断。

## 何时用 / 不用

- **用**：看看文件夹有哪些材料；对照要写的题目列缺料。
- **不用**：已明确要多份汇总成报告（直接走 `multidoc-digest`）；单篇校对（走 `doc-proofread`）。

## 输入与产出

```
工作区根或用户指定子目录
.office-agent/work/material-gap/inventory.json
output/材料清单.md
output/缺料检查表.md          # 仅缺料模式
```

## 三步纪律（必须按序）

### Step 1 — 摸底入库（脚本，1 步）

```
run_skill_script
  skill_id: material-gap
  script: inventory.py
  args: [<相对目录，默认 .>]
```

产出 `.office-agent/work/material-gap/inventory.json`。向用户报告：文件总数、按扩展名计数。

### Step 2 — 写材料清单（Agent，1～2 步）

读取 inventory，写 `output/材料清单.md`：

- 按类型分组（如 Word / Excel / PPT / PDF / 图片 / 其他）
- 每组下列相对路径与文件名
- 首页给总数与分组统计

仅「摸底」时到此 `finish`。

### Step 3 — 缺料检查（Agent，约 2～4 步；仅缺料模式）

用户给出或已说明「要写的题目 / 文种」。对照清单判断还缺什么，写 `output/缺料检查表.md`：

| 所需材料 | 状态（已有/缺失/存疑） | 已有路径或说明 | 建议补充来源 |
|----------|------------------------|----------------|--------------|
| … | … | … | … |

硬规则：

- 「已有」必须能指到清单中的真实路径，禁止虚构文件名。
- 「缺失」要写清为何该题目通常需要它（一句话）。
- 拿不准标「存疑」，不要假装齐套。

## 步数预算

| 模式 | 约计 |
|------|------|
| 仅摸底 | ≈3 |
| 摸底 + 缺料 | ≈5～8 |

## 硬规则

1. 必须先跑 `inventory.py`，禁止只凭记忆列目录。
2. 缺料表不得编造工作区中不存在的「已有」文件。
3. 交付在 `output/`。

## 变更记录

- 1.0.0 — Wave2：摸底 + 缺料
