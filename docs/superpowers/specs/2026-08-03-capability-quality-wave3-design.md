# 文书通能力强化 · Wave 3 设计

**日期：** 2026-08-03  
**状态：** 已落地  
**范围：** 汇报演示与举一反三 — 一文三用编排、汇报成套（提纲 / PPT / 讲稿）

## 1. Objective

办事人能用自然语言：同一批材料一次产出报告正文 + 汇报提纲 + 答问口径；再按提纲生成可打开的 PPT 与口播汇报稿。复用前两期质量与摸底能力，标准包保持 thin。

## 2. In / Out

**In**

- Skill（light，预置）：`one-to-three`、`brief-deck`
- `brief-deck/scripts/build_pptx.py`：从页纲 JSON 生成基础 16:9 pptx（正式浅底深蓝风格）
- 配色细调仍走既有 `office-visual-design`（不重做配色体系）
- 列入 `BUNDLED_SKILL_IDS`、包装说明、system prompt 路由提示

**Out**

- 花哨动效 / 模板商城 / 自动配图
- 新向量检索；把 RAG 打进标准包
- 重写 `office-visual-design`
- 红笔 / 缺料新 skill（已由 Wave1/2 覆盖）
- App Store / 安装器

## 3. 验收

### one-to-three

- 触发：一文三用及相关 saying（报告正文 / 汇报提纲 / 答问口径）
- 交付（全流程）：`output/报告正文.md`、`output/汇报提纲.md`、`output/答问口径.md`
- 用户只要其中一环时只交对应产物
- 硬规则：定量须带来源或标「待核实」；答问口径不得编造未在材料中的事实；缺料明显时先提示走 `material-gap` 或在文首列缺口

### brief-deck

- 触发：汇报提纲、演示文稿、生成 PPT + 汇报稿
- 交付按需：`output/汇报提纲.md`、`.office-agent/work/brief-deck/slides.json`、`output/汇报演示.pptx`、`output/汇报稿.md`
- 页纲与幻灯页、讲稿段落可对齐（同序号/同标题）
- 硬规则：一页一意；禁止无来源的定量页（数字须能回溯提纲/材料或标待核实）
- 成套 PPT 须经 `run_skill_script` 调用 `build_pptx.py`；配色精修可再调 `office-visual-design`

## 4. 能力栏映射

| 叶子 | Skill |
|------|--------|
| 正式配色 | `office-visual-design`（既有） |
| 汇报提纲 / 演示文稿 | `brief-deck` |
| 一文三用 | `one-to-three` |
| 红笔找茬 / 缺啥补啥 | 既有，不新开 |

## 5. 命令

```
cd runtime && python3 -m pytest tests/test_bundled_seed.py -q
cd apps/desktop && npm test -- --run src/lib/skillUtils.test.ts
# 可选：脚本冒烟
python3 bundled/skills/brief-deck/scripts/build_pptx.py --help
```
