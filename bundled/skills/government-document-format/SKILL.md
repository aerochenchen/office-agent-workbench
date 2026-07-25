---
name: government-document-format
display_name: 公文格式排版
description: 对工作区内 .docx 按 GB/T 9704-2012 做党政机关公文排版（结构角色需先判定）。
version: 2.1.0
tier: light
permissions:
  - workspace_read
  - workspace_write
  - run_python
shared_scripts:
  - format_gongwen
category: productivity
trigger_phrases:
  - 公文格式
  - 公文排版
  - 公文格式排版
  - 红头文件
  - GB/T 9704
  - 党政机关公文
target_file_type: .docx
required_tools: python-docx
---

# 公文格式排版

依据 GB/T 9704-2012。**禁止**跳过结构分析直接跑排版脚本：层次标号与字体绑定靠语义判断，脚本只按已标注角色施加样式。

细则：`references/hierarchy.md`（层次/标号/roles）、`references/layout.md`（版心/版头版记）、`references/python-docx-pitfalls.md`。

## 何时用 / 不用

- **用**：用户要对 `.docx`「按公文格式排版 / 红头 / GB/T 9704」。
- **不用**：只改措辞不改版式；非党政机关公文版式；纯 Markdown 未转 docx。

## 四步纪律（必须按序）

### Step 1 — 导出段落（脚本，1 步）

```
run_shared_script
  name: format_gongwen
  args: [dump, <docx路径>]
```

或 `run_skill_script` → `government-document-format` / `format_gongwen.py`，args 相同。

产出：`<原名>_paragraphs.json`（含每段 `index`/`text`/`empty`）。向用户确认路径与非空段数量。

### Step 2 — 结构标注 + 标号规范化（Agent，约 2～4 步）

1. `read_skill` 读 `references/hierarchy.md`（必要时再读 `layout.md`）。
2. 通读 `_paragraphs.json`，为**每一段**判定 `role`（版头/标题/主送/`h1`–`h4`/正文/附件/署名日期/版记/`empty`/`skip`）。
3. 西式二级标号（`1.1` / `2.3`）：**必须标 `h2`**（可抄 dump 里的 `hint_role` / `hint_text`）。若漏填 `text`，**apply 仍会自动改为「（一）（二）」**；半角 `(一)` 同理。
4. 发文字号段 index 写入 `red_line_after`；印章等写进 `notes`。
5. 将 `roles.json` 写到与源文件同目录（推荐 `<原名>_roles.json`）。

```json
{
  "source": "示例.docx",
  "red_line_after": 3,
  "notes": ["印章需人工插入"],
  "paragraphs": [
    {"index": 0, "role": "masthead"},
    {"index": 5, "role": "title"},
    {"index": 8, "role": "h2", "text": "（一）贯通业务流程"},
    {"index": 9, "role": "body"}
  ]
}
```

**硬规则**：不得凭 `startswith('一、')` 之类启发式代替本步；拿不准标 `skip` 或 `body` 并在 `notes` 说明。

### Step 3 — 按角色施加样式（脚本，1 步）

```
run_shared_script
  name: format_gongwen
  args: [apply, <docx路径>, <roles.json路径>]
```

产出：`<原名>_formatted.docx`。检查 stdout 的 `numbering_fixed`（西式→国标次数）、`warnings`、`applied_roles`。

### Step 4 — 复核（Agent，1 步）

对照 `hierarchy.md` 抽查：一级是否黑体、二级是否楷体、西式编号是否已改、主送是否顶格。向用户报告输出路径、`notes`、以及脚本 warnings；印章/页码/垂直精确定位标为人工项。

## 角色 → 样式（速查）

| role | 字体 | 要点 |
|------|------|------|
| `masthead` | 方正小标宋 · 红 · 居中 | 发文机关标志 |
| `title` | 方正小标宋 · 二号 · 居中 | 公文标题 |
| `h1` | 黑体三号 | 「一、」 |
| `h2` | 楷体_GB2312 三号 | 「（一）」 |
| `h3` / `h4` / `body` | 仿宋_GB2312 三号 | 「1.」/「（1）」/正文 |
| `main_recipient` | 仿宋 · 顶格 | 末全角冒号 |
| `doc_number` | 仿宋 · 居中 | 可挂红线 |
| `empty` / `skip` | — | 空段 / 不改 |

完整表与转换规则见 `hierarchy.md`。

## 步数预算

| 阶段 | 约计 |
|------|------|
| dump / apply | 2 |
| 标注 + 写 roles | 2～4 |
| 复核 | 1 |
| **合计** | **≈5～7** |

超长文可分段标注同一 `roles.json`（按 index 合并），再一次性 apply。

## 硬规则

1. **先 dump → 再 roles → 后 apply**；禁止对未标注文档直接 apply。
2. 保留正文语义；仅改版式与序数形态。西式二级（`1.1`）由 **apply 自动转「（一）」**（按每个 `h1` 下顺序重计）；Agent 仍应标对 `h2`。
3. 修改多段落 XML 时遵守 `python-docx-pitfalls.md`。
4. stdout 以脚本 JSON 为准；失败看 stderr `ERROR:`。

## 变更记录

- **2.1.0**：apply 自动将 `1.1`/`2.1` 等西式二级及半角 `(一)` 转为「（一）（二）」；dump 增加 `hint_text` / `needs_numbering_fix`。
- **2.0.0**：改为 Agent 结构分析 + 脚本按角色施加；`dump`/`apply` 双命令；废弃纯启发式一键排版。
- **1.1.0**：固定行距/缩进与部分标题启发式。
