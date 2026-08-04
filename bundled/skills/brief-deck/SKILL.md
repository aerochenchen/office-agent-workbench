---
name: brief-deck
display_name: 汇报成套
description: 按材料整理汇报提纲，生成基础 PPT，并写对应汇报稿。
version: 1.0.0
tier: light
permissions:
  - workspace_read
  - workspace_write
  - run_python
category: productivity
trigger_phrases:
  - 汇报提纲
  - 演示文稿
  - 汇报稿
  - 生成 PPT
  - 按这份材料整理成汇报提纲，适合做成幻灯片
  - 根据这份材料生成一套 PPT，并写一份对应的汇报稿
target_file_type: .pptx
---

# 汇报成套

把材料收成**可上台组合**：汇报提纲 → 页纲 JSON → 基础 PPT → 口播汇报稿。配色精修走 `office-visual-design`；一文三用的提纲可直接作为输入。

## 何时用 / 不用

- **用**：整理汇报提纲；生成演示文稿 + 汇报稿；已有提纲要落成 pptx。
- **不用**：只要正式配色/换皮（走 `office-visual-design`）；只要报告+答问不要幻灯（走 `one-to-three`）；红头公文（走 `government-document-format`）。

## 输入与产出

```
用户材料，或 工作成果/汇报提纲.md（可来自 one-to-three）
.office-agent/work/brief-deck/slides.json
工作成果/汇报提纲.md          # 按需
工作成果/汇报演示.pptx        # 按需（硬交付）
工作成果/汇报稿.md            # 按需
```

用户只要提纲时可不生成 pptx；要「演示文稿」时须产出 pptx + 建议同步汇报稿。

## 五步纪律（必须按序）

### Step 1 — 定位输入（Agent，1 步）

优先顺序：用户指定路径 → 已有 `工作成果/汇报提纲.md` → 源材料文件。缺路径 `ask_user` **一次**。

### Step 2 — 写或核对提纲（Agent，1～3 步）

若尚无提纲：读材料后写 `工作成果/汇报提纲.md`（结构同 `one-to-three` 的提纲：页序、一页一意、3～5 条要点）。  
若已有提纲：核对页序是否适合上台（过长则拆页，过碎则合并），必要时回写提纲。

硬规则：一页一意；定量要点须能回溯材料或标「待核实」。

### Step 3 — 落盘页纲 JSON（Agent，1 步）

将提纲写成 `.office-agent/work/brief-deck/slides.json`，供脚本生成 PPT。Schema：

```json
{
  "title": "汇报标题",
  "subtitle": "单位 / 场合 / 日期（可空）",
  "slides": [
    {"type": "title", "title": "…", "subtitle": "…"},
    {"type": "section", "title": "第一部分 …"},
    {"type": "content", "title": "页标题", "bullets": ["要点1", "要点2"]},
    {"type": "closing", "title": "汇报完毕", "bullets": ["请示事项…"]}
  ]
}
```

- `type`：`title` | `section` | `content` | `closing`
- `content` / `closing` 的 `bullets` 每条一行短句；单页建议 ≤6 条

### Step 4 — 生成 PPT（脚本，1 步）

```
run_skill_script
  skill_id: brief-deck
  script: build_pptx.py
  args: [
    --slides, .office-agent/work/brief-deck/slides.json,
    --out, 工作成果/汇报演示.pptx
  ]
```

脚本产出正式浅底深蓝风 16:9 基础稿。若用户要换场合配色，生成后再调 `office-visual-design` 套用，勿在本步重造配色体系。

### Step 5 — 写汇报稿并收尾（Agent，1～3 步）

写 `工作成果/汇报稿.md`：按页序分段，每段对应一页标题；口语可念、含过渡句；数字与提纲一致。  
`finish` 列出 `汇报提纲.md` / `汇报演示.pptx` / `汇报稿.md` 路径。

## 步数预算

| 阶段 | 约计 |
|------|------|
| 定位 + 提纲 | 2～4 |
| JSON + PPT | 2 |
| 汇报稿 | 1～3 |
| **合计** | **≈5～9** |

## 硬规则

1. 提纲页序、`slides.json`、pptx 页、汇报稿段落必须可对齐（同序同题）。
2. 禁止无来源定量页。
3. 生成 pptx 必须走 `build_pptx.py`，禁止空口宣称已生成文件。
4. 交付在 `工作成果/`；过程 JSON 在 `.office-agent/work/brief-deck/`。

## 变更记录

- 1.0.0 — Wave3：提纲 / 基础 PPT / 汇报稿
