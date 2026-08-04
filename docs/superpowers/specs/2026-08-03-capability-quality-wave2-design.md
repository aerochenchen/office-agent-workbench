# 文书通能力强化 · Wave 2 设计

**日期：** 2026-08-03  
**状态：** 实施中  
**范围：** 日常办事闭环 — 会议督办、材料摸底/缺料、表格成文、口径模板

## 1. Objective

机关办事人能用自然语言完成：会议纪要→待办台账→催办说明；文件夹摸底与缺料清单；表格写情况说明/结论/按表填报（结论可指回单元格）。口径文件有可复制模板。标准包保持 thin。

## 2. In / Out

**In**

- Skill（light，预置）：`meeting-followup`、`material-gap`、`sheet-to-brief`
- `workspace_extract` 对 xlsx 增加 `granularity=cells`（单元格级定位）
- glossary 示例模板（skill-builder / doc-proofread references）
- 列入 `BUNDLED_SKILL_IDS` 与包装说明

**Out**

- 整套 PPT+讲稿、一文三用编排（Wave 3）
- 会议多人协同/项目管理
- 将 RAG 打进标准包
- App Store / 安装器

## 3. 验收

### meeting-followup
- 触发：整理纪要、待办分人、催办说明及相关 saying
- 交付：`工作成果/会议纪要.md`、`工作成果/待办台账.md`（含责任人/时限/事项）、`工作成果/催办说明.md`（按需）
- 待办项不得缺少「事项」；缺责任人或时限须在台账标注「待明确」

### material-gap
- 触发：文件夹摸底、缺啥补啥
- 交付：`工作成果/材料清单.md`；缺料模式另交 `工作成果/缺料检查表.md`
- 清单按扩展名/类型分组；缺料表对照用户题目列「已有 / 缺失 / 建议来源」

### sheet-to-brief
- 触发：表写情况说明、数据结论、按表填报
- 抽取：`workspace_extract` + `granularity=cells`
- 情况说明/结论中的定量表述须带来源定位（如 `汇总!B3`）；填报产出缺口清单
- 交付：`工作成果/情况说明.md` 或 `工作成果/数据结论.md` 或填好的表 + `工作成果/填报缺口.md`

### glossary
- 存在可复制的 `glossary.example.md`；产品说明/技能说明指向 `.office-agent/glossary.md`

## 4. 命令

```
cd runtime && python3 -m pytest tests/test_doc_io.py tests/test_bundled_seed.py -q
cd apps/desktop && npm test -- --run src/lib/skillUtils.test.ts
```
