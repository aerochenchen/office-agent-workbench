---
name: ppt-maker
display_name: PPT制作
description: 做成或修改正式幻灯片，含提纲、配色、图表与口播稿。
version: 2.0.0
tier: light
permissions:
  - workspace_read
  - workspace_write
  - run_python
category: productivity
trigger_phrases:
  - 做PPT
  - 制作PPT
  - PPT制作
  - 生成幻灯片
  - 生成 PPT
  - 修改PPT
  - 读取幻灯片
  - 有没有PPT能力
  - 汇报提纲
  - 演示文稿
  - 汇报稿
  - 正式配色
  - PPT配色
  - 汇报配色
  - 幻灯片风格
  - 套个配色
  - 按这份材料整理成汇报提纲，适合做成幻灯片
  - 根据这份材料生成一套 PPT，并写一份对应的汇报稿
target_file_type: .pptx
---

# PPT制作

从材料做成或修改正式 `.pptx`。版式、字号、配色由脚本引擎负责。不要在工作区重写 python-pptx。

红头公文走 `government-document-format`。只要报告/答问不要幻灯走 `one-to-three`。独立 PNG/插入 Word 的图走 `chart-generation`。旧版 `.ppt` 不能直接打开，先说明限制。

## 何时用 / 不用

- **用**：做或改幻灯片；汇报提纲要落成 PPT；要口播稿；换正式配色；套单位模板；用户问有没有 PPT 能力。
- **不用**：红头公文；只要报告正文或答问；把表做成独立 PNG 去插 Word。

## 输入与产出

```
用户材料 / 已有 .pptx / 工作成果/汇报提纲.md
.office-agent/work/ppt-maker/deck.json
工作成果/*.pptx
工作成果/汇报提纲.md     # 按需
工作成果/汇报稿.md       # 用户要口播稿才写
```

页类型、字段见 `references/layouts.md` 与 `references/deck.schema.md`。

## 四条路径

### 新建（必须按序）

1. 读材料：`workspace_extract` 或已有提纲。缺路径 `ask_user` **一次**。
2. 需要提纲时写 `工作成果/汇报提纲.md`：一页一意，每页 3～5 条短句；定量须能回溯或标「待核实」。
3. 写成 `.office-agent/work/ppt-maker/deck.json`。`type` 只许从表里抄，不要写 left/top/pt/裸 hex。
4. 校验：

```
run_skill_script
  skill_id: ppt-maker
  script: pptx_validate.py
  args: [.office-agent/work/ppt-maker/deck.json]
```

`ok` 不为 true 就改 JSON，禁止跳过。
5. 生成：

```
run_skill_script
  skill_id: ppt-maker
  script: pptx_create.py
  args: [.office-agent/work/ppt-maker/deck.json, 工作成果/汇报演示.pptx]
```

6. `pptx_read.py --outline` 核对页数、标题、表格和图表数字。
7. 用户要口播稿才写 `工作成果/汇报稿.md`：按页序分段，同序同题。

场合配色：`palette` 用 `zhengwu-navy`（默认）/`dangjian-crimson`/`fazhan-teal`/`shuzhi-steel`/`anquan-slate`/`peixun-warmgray`/`zhongdian-amber`/`dayin-paper`。有单位主色则 `"palette": {"primary": "003A70"}`。

### 读取

```
run_skill_script
  skill_id: ppt-maker
  script: pptx_read.py
  args: [工作成果/汇报演示.pptx, --outline]
```

备注加 `--notes`。导出图片：`--images .office-agent/work/ppt-maker/images`。要改文件时以本脚本回读为准。

### 修改

在原文件上改，或 `--output` 另存到 `工作成果/`。页序号从 0 开始。

| 目的 | args 片段 |
|------|-----------|
| 换配色 | `--palette`, zhengwu-navy（或主色 JSON） |
| 换字 | `--replace-text`, 旧文, 新文 |
| 改图表 | `--chart-data`, 参数.json |
| 换图 | `--swap-image`, 页序号, 形状名, 新图片路径 |
| 复制页 | `--duplicate-slide`, 页序号 |
| 删页 | `--remove-slide`, 页序号 |
| 调序 | `--move-slide`, 从, 到 |
| 备注 | `--set-notes` / `--append-notes` |
| 页脚 | `--set-footer`, 页序号, 文字 |

含图表的页不能复制，应新建一页。换皮不改文案。改完再 `pptx_read.py --outline`。

### 套模板

模板里写 `{{名称}}`，values JSON 为 `{"名称": "替换文字"}`。

```
run_skill_script
  skill_id: ppt-maker
  script: pptx_from_template.py
  args: [模板.pptx, 工作成果/演示文稿.pptx, --values, .office-agent/work/ppt-maker/values.json]
```

按模板版式追加页时加 `--add-slides`。

## 步数预算

| 阶段 | 约计 |
|------|------|
| 读技能 + 材料/提纲 | 2～4 |
| 写 JSON + 校验 + 生成 | 3 |
| 回读；口播稿按需 | 1～3 |
| **合计** | **≈6～10** |

改已有文件：先读大纲，改完再回读。

## 硬规则

1. 生成或修改 pptx 必须走上面脚本，禁止在工作区重写 python-pptx 程序，禁止当场重写 python-pptx。
2. 新建必须先 `pptx_validate.py`；`ok` 不为 true 时不得对用户说已经做好。
3. 页 `type` 只能用封闭列表；坐标和裸 hex 仅 `type: canvas` 且颜色须为 palette token。
4. 交付放在 `工作成果/`；过程 JSON 放在 `.office-agent/work/ppt-maker/`。
5. 图片和输出路径必须在当前文件夹内。
6. 用户问有没有 PPT 或幻灯片能力时，直接说明可以新建、读取、修改、换配色，并按本技能做。

## 变更记录

- 2.0.0 — 合并汇报成套与正式配色：语义页纲 + 版式引擎 + 校验；分档靠 variant/canvas。
- 1.0.0 — 由 Nous Research powerpoint 1.1.0（MIT）改编为文书通预置技能。
