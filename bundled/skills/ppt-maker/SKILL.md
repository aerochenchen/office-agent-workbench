---
name: ppt-maker
display_name: PPT制作
description: 创建、读取、修改任意幻灯片，产出或改写 .pptx。
version: 1.0.0
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
  - 修改PPT
  - 读取幻灯片
  - 有没有PPT能力
target_file_type: .pptx
---

# PPT制作

用预置脚本创建、读取、修改 `.pptx`。不需要本机安装 PowerPoint。

上台汇报若只要「提纲 + 基础要点页 + 口播稿」，走 `brief-deck`。只要换配色，走 `office-visual-design`。

## 何时用 / 不用

- **用**：用户问能否做 PPT 或幻灯片；新建演示文稿（含表格、图表、图片、形状、备注）；读取已有 pptx 的文字、表格、图表数据和备注；修改已有 pptx（换字、改图表、换图、增删移页、背景、页脚、备注）；按单位模板填充 `{{标记}}`。
- **不用**：只要汇报提纲和口播稿、且接受基础要点页（走 `brief-deck`）；只要换正式配色（走 `office-visual-design`）；红头公文（走 `government-document-format`）。旧版 `.ppt` 不能直接打开，先说明限制。

## 输入与产出

```
用户材料 / 已有 .pptx / 单位模板.pptx
.office-agent/work/ppt-maker/*.json
工作成果/*.pptx
```

## 四条路径

先读本文件。字段细节见 `references/create-spec.md`。

### 新建

把页纲写成 `.office-agent/work/ppt-maker/deck.json`，再运行：

```
run_skill_script
  skill_id: ppt-maker
  script: pptx_create.py
  args: [.office-agent/work/ppt-maker/deck.json, 工作成果/演示文稿.pptx]
```

常用版式：`title`、`title_content`、`section`、`two_content`、`title_only`、`blank`。默认 16:9。

### 读取

```
run_skill_script
  skill_id: ppt-maker
  script: pptx_read.py
  args: [工作成果/演示文稿.pptx, --outline]
```

备注加 `--notes`。导出内嵌图片：`--images .office-agent/work/ppt-maker/images`。只核对正文时也可以用 `workspace_extract`；要改文件时以本脚本回读为准。

### 修改

在原文件上改，或用 `--output` 另存到 `工作成果/`。页序号从 0 开始。

| 目的 | args 片段 |
|------|-----------|
| 换字 | `--replace-text`, 旧文, 新文 |
| 改图表 | `--chart-data`, 参数.json |
| 换图 | `--swap-image`, 页序号, 形状名, 新图片路径 |
| 复制页 | `--duplicate-slide`, 页序号 |
| 删页 | `--remove-slide`, 页序号 |
| 调序 | `--move-slide`, 从, 到 |
| 背景色 | `--set-background`, 页序号, RRGGBB |
| 备注 | `--set-notes`, 页序号, 文字 |
| 追加备注 | `--append-notes`, 页序号, 文字 |
| 页脚 | `--set-footer`, 页序号, 文字 |

含图表的页不能复制，脚本会拒绝；应新建一页重做图表。

### 套模板

模板里写 `{{名称}}`，values JSON 为 `{"名称": "替换文字"}`。

```
run_skill_script
  skill_id: ppt-maker
  script: pptx_from_template.py
  args: [模板.pptx, 工作成果/演示文稿.pptx, --values, .office-agent/work/ppt-maker/values.json]
```

要按模板版式追加页，再加上 `--add-slides` 和对应 JSON。

## 步数预算

| 阶段 | 约计 |
|------|------|
| 读技能 + 写 JSON | 2 |
| 跑脚本 | 1 |
| 回读核对 | 1 |
| **合计** | **≈4** |

改已有文件时先读大纲，改完再回读一次。

## 硬规则

1. 生成或修改 pptx 必须走上面四个脚本，禁止在工作区重写 python-pptx 程序。
2. 脚本返回的 `ok` 不为 true 时，不得对用户说已经做好。
3. 新建或另存的交付放在 `工作成果/`；过程 JSON 放在 `.office-agent/work/ppt-maker/`。
4. 改完必须再用 `pptx_read.py --outline` 核对页数、文字、表格和图表数字。
5. 图片和输出路径必须在当前文件夹内。
6. 用户问有没有 PPT 或幻灯片能力时，直接说明可以新建、读取、修改，并按本技能做。

## 变更记录

- 1.0.0 — 由 Nous Research powerpoint 1.1.0（MIT）改编为文书通预置技能。不含页面渲染。
