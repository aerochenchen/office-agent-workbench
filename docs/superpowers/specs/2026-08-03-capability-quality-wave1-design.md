# 文书通能力与材料质量强化 · Wave 1 设计

**日期：** 2026-08-03  
**状态：** 实施中  
**范围：** 写作 × 审校 × 汇总质量三角（底座抽取/对比 + 校对/对照 skill + 加强三件套）

## 1. Objective

机关办事人在文书通里完成校对、两版对照、多份汇总、按模板起草与公文排版时，交付物应可核验（带定位/出处）、可对比（结构化改动）、可收口（排版自检）。底座只增强共用杠杆；方法进 skill。标准包保持 thin；`gongwen-rag-writing` 仍为 optional heavy。

## 2. In / Out

**In**

- `workspace_extract` 支持 `granularity=section|paragraph`；单元带可选 `meta`
- 共享脚本 `docx_diff`（段落级 add/delete/replace）
- Skill：`doc-proofread`、`doc-diff-review`
- 加强：`multidoc-digest`、`gongwen-rag-writing` 自审、`government-document-format` 收口
- 约定 `.office-agent/glossary.md` + system 短提示

**Out**

- 会议督办 / 表格成文 / 整套 PPT 生成
- 新 agent tool schema（对比走 shared script）
- 将 RAG 打进标准安装包
- App Store / 安装器改动

## 3. 验收标准

### 3.1 抽取

- 默认 `granularity=section`：既有测试与 unit_id 形态不破坏
- `granularity=paragraph`：非空段各成一 unit；`kind` 为 `paragraph` 或 `heading`；`meta` 含 `level`、`para_start`、`para_end`
- `to_dict()` 在有 meta 时包含 `meta` 字段

### 3.2 docx_diff JSON

```json
{
  "ok": true,
  "old": "a.docx",
  "new": "b.docx",
  "changes": [
    {
      "op": "replace",
      "old_para": 3,
      "new_para": 3,
      "old_text": "…",
      "new_text": "…"
    }
  ],
  "warnings": [],
  "summary": { "add": 0, "delete": 0, "replace": 1 }
}
```

- `op` ∈ `add|delete|replace`
- Wave 1 仅保证正文段落；复杂表格可进 `warnings`

### 3.3 校对报告（`output/校对报告.md`）

- 每条问题含：分类（称谓/数字/标点/术语/口径/逻辑追问）、定位（`unit_id` 或 `p{idx}`）、原文摘要、建议
- 禁止无定位空泛批评
- 若存在 `.office-agent/glossary.md`，术语/口径类须对照该文件

### 3.4 对照审校（`output/对照审校.md`）

- 先跑 `docx_diff`，再解读为主要改动列表；条款模式按标题聚类
- 改动须能回溯到 diff JSON 中的 `op` + 段落 index

### 3.5 multidoc-digest

- 审计：无效引用标红/计入失败；定量 claim 无 citation 计入失败项
- 卡片可选 `risks`；reduce 不得把 risks 写成已确认事实
- `fixtures/sample-30` smoke 不回退（无效引用基线）

### 3.6 gongwen-rag-writing

- 阶段⑤必须落盘 `.office-agent/work/gongwen-rag-writing/self_review.md` 后方可排版
- 清单覆盖：无出处数据、套话空段、语气偏离、前后数字矛盾
- 不改向量模型与标准包体积

### 3.7 government-document-format

- Step 4 自检清单：角色覆盖、空 role、西式标号、产出在 `output/`
- 禁止跳过 dump→roles→apply

### 3.8 全局

- `pytest`：`test_doc_io` + `test_docx_diff` 通过
- 标准安装包仍不含 `gongwen-rag-writing`

## 4. 命令

```
cd runtime && pytest tests/test_doc_io.py tests/test_docx_diff.py -v
```

## 5. Boundaries

- Always：默认 section 兼容；新 skill `tier: light`
- Ask first：新增 agent tool、把 heavy skill 打进标准包
- Never：联网下载 embedding；读写出工作区
