---
name: multidoc-digest
display_name: 批量文档整理
description: 把几十份 Word 材料汇总成一份带出处的报告。
version: 1.1.0
tier: light
permissions:
  - workspace_read
  - workspace_write
  - run_python
shared_scripts:
  - format_gongwen
category: productivity
trigger_phrases:
  - 批量文档整理
  - 汇总报告
  - 材料汇总
  - 多文档汇总
  - 汇编
  - 几十份文档
  - 批量文档汇总
  - 溯源核查
  - 覆盖率
target_file_type: .docx
required_tools: python-docx
---

# 批量文档整理

面向 **30～50 份** `.docx` 素材：用脚本完成确定性重活（分块、聚类、审计），LLM 只做逐份摘要（map）与主题归并（reduce）。**不改 Runtime**；每脚本调用计 1 步工具、最长 600s。

工作目录（相对工作区根）：

```
.office-agent/work/multidoc-digest/
  manifest.jsonl
  chunks.jsonl
  packs/<doc_id>.md
  cards/<doc_id>.json
  outline.json
output/
  汇总报告.md
  审计报告.md
```

引用规范详见 `references/citation-format.md`。锚点格式：`〔doc_id#sec〕`（全角方括号）。

---

## 六步纪律（必须按序）

### Step 1 — 入库分块（脚本，1 步）

```
run_skill_script
  skill_id: multidoc-digest
  script: ingest.py
  args: [<工作区内素材文件夹>]
```

产出 `manifest.jsonl`、`chunks.jsonl`、`packs/*.md`。告知用户：成功/失败份数、工作目录路径。失败文件记入 manifest（`status=error`），不中断。

### Step 2 — 逐份摘要 map（Agent，约 4～6 步）

1. `workspace_list` → `.office-agent/work/multidoc-digest/packs`
2. **分批** `workspace_read` 读取 packs（每批 5～10 份，避免撑爆上下文）
3. 对每份材料写卡片到  
   `.office-agent/work/multidoc-digest/cards/<doc_id>.json`

卡片 JSON schema：

```json
{
  "doc_id": "d001",
  "title": "文档标题或文件名",
  "points": [
    {
      "claim": "一句话要点",
      "citations": ["d001#s01"],
      "kind": "data|case|problem|measure|other",
      "has_data": true
    }
  ],
  "summary": "80～150 字摘要",
  "risks": ["待核实：某数据仅口头传达，未见文件"]
}
```

规则：

- 每个 `claim` **至少**一个本篇 `citations`（必须来自该 pack 中出现的 `doc_id#sec`）
- **定量 / `has_data` / `kind=data` 的要点若无 citations → 审计 FAIL**
- 可选 `risks`：待核实项、存疑表述；**reduce 成文时不得把 risks 写成已确认事实**（原文泄漏进报告会审计 FAIL）
- 不得编造不存在的锚点
- 50 份时务必分批；若接近工具步数上限，`finish` 并提示用户开新对话继续 map（cards 已落盘可续跑）

### Step 3 — 主题归并大纲（脚本，1 步）

```
run_skill_script
  skill_id: multidoc-digest
  script: merge_outline.py
  args: []
```

默认读取 work 目录下 `cards/` 与 `chunks.jsonl`，写出 `outline.json`（含覆盖预统计）。向用户报告主题数与预估覆盖率。

### Step 4 — 按主题成文 reduce（Agent，约 3～6 步）

1. `workspace_read` → `outline.json`
2. 按主题撰写 `output/汇总报告.md`（写入路径用相对工作区：`output/汇总报告.md`）
3. **每一段论述**末尾或句内标注 `〔doc_id#sec〕`，且必须来自该主题的 `support_citations`
4. 文末「参考文献」表：列出报告中出现的 `doc_id` → 文件名（可从 outline/manifest 映射）

禁止：无引用的定量数据；禁止杜撰锚点。

### Step 5 — 审计（脚本，1 步）

```
run_skill_script
  skill_id: multidoc-digest
  script: audit.py
  args: [output/汇总报告.md]
```

产出 `output/审计报告.md`。向用户摘要：覆盖率、未用文件数、无效引用数、单一来源数据告警数、**审计 PASS/FAIL**。

硬规则：`invalid_citations`、报告中无出处定量句、卡片定量缺 citations、`risks` 泄漏为正文 → **FAIL**（脚本退出码 1）。FAIL 时须修订报告或卡片后重跑本步，不得宣称汇总完成。

### Step 6 — 可选排版

若用户要 docx：将 Markdown 转为 docx 后，按 `government-document-format` **四步**执行（先 `dump` 标注角色，再 `apply`），禁止对未标注文档直接调用 `format_gongwen`。

---

## 步数预算（30～50 份）

| 阶段 | 约计步数 |
|------|----------|
| ingest / merge / audit | 3 |
| map（分批读+写卡） | 4～6 |
| reduce | 3～6 |
| **合计** | **≈10～15**（留余量给澄清/重试） |

材料 >50 或单篇极长时：分会话——会话 A 只做 Step1～2，会话 B 从已有 cards 继续 Step3～5。

---

## 交付物

1. `output/汇总报告.md` — 分主题正文 + 内联引用 + 参考文献
2. `output/审计报告.md` — 覆盖率、未用清单、无效引用、风险清单、抽检对照

评估时优先看审计报告：金标事实是否出现、无效引用是否为 0、未用文件是否合理、审计结论是否 PASS。

## 变更记录

- 1.1.0 — Wave1：审计阻断无效引用/无出处定量/缺 cite 数据卡/`risks` 泄漏；卡片 schema 增加 `risks`
- 1.0.0 — 首版六步流水线
