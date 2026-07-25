---
name: skill-builder
display_name: 创建技能
description: 把用户反复做的事沉淀成新技能：起草、校验、自测、安装、迭代、导出分享。
version: 1.0.0
tier: light
permissions:
  - workspace_read
  - workspace_write
  - run_python
category: meta
trigger_phrases:
  - 创建技能
  - 新建技能
  - 沉淀成技能
  - 把这个流程固化
  - 做成技能
  - 修改技能
  - 迭代技能
  - 导出技能
  - 分享技能
  - 以后都这么做
target_file_type: .md
required_tools: python-docx
---

# 创建技能

把用户重复做的事务性工作固化成一个可复用的 Skill：**确定性重活写成 `scripts/*.py`，需要判断力的部分写成 SKILL.md 正文的纪律**。

草稿先落在工作区里，因此在安装之前就能用真实素材把脚本跑通；验证通过才写进应用数据目录。

工作目录（相对工作区根）：

```
.office-agent/work/skill-draft/<skill-id>/    # 草稿：可自由改、可直接跑
  SKILL.md
  scripts/*.py
  references/*.md
output/<中文名>-<skill-id>.zip                # 仅在用户要分享时产出
```

规范细则见 `references/skill-md-spec.md`（frontmatter 字段、命名、正文章节）与 `references/script-conventions.md`（脚本 CLI 约定、可用依赖、硬禁项）。**起草前必须先读这两份**。

---

## 七步纪律（必须按序）

### Step 0 — 先判断值不值得固化（Agent，0～1 步）

三问，任一为否就**不要**建技能：

1. **会重复发生吗？** 一次性的活直接做完，不要沉淀。
2. **输入输出稳定吗？** 每次素材形态、成品格式大体一致才值得固化。
3. **现有技能能覆盖吗？** 先看已启用的 Skill 目录，像的话 `read_skill` 读它的正文确认；能覆盖就走 Step 6 迭代那个技能，而不是新建。

判断为不值得时，明确告诉用户理由，然后直接把这次的活干完。技能库贵在少而准。

### Step 1 — 采集素材（Agent，1～3 步）

按用户的来意选**一个**入口：

**A. 复盘固化**（用户刚做完一件事说"以后都这么办"）——最省力也最准。直接从本次会话里提炼：调用了哪些工具、顺序如何、中途返工的地方就是要写进"硬规则"的坑、用户纠正过的口径就是硬约束。不要再问用户任何问题。

**B. 访谈**（用户凭空提一个流程）——`ask_user` **整轮只能用一次**，所以必须一条消息把五件事问全：

1. 什么情况下要用这个技能（触发场景）
2. 素材通常放在哪、什么格式
3. 成品长什么样，交付到哪
4. 有哪些必须遵守的硬规矩（口径、格式、脱敏要求）
5. 哪些步骤是机械重复、每次都一样的

**C. 样例反推**（用户给了几份成品说"照这个来"）——`workspace_extract` 读 2～3 份成品，归纳出共同的结构、字段、字号字体，把差异项标记为"每次要填的变量"。

### Step 2 — 起草（Agent，2～4 步）

1. `read_skill(skill_id=skill-builder, file=references/skill-md-spec.md)` 和 `file=references/script-conventions.md`
2. `read_skill(skill_id=skill-builder, file=templates/SKILL.md.tmpl)` 取模板
3. 定 id：纯小写 ASCII + 连字符，如 `weekly-report-digest`；`display_name` 用 4～10 字中文
4. `workspace_write` 写 `.office-agent/work/skill-draft/<skill-id>/SKILL.md`
5. 需要脚本时，`read_skill(file=templates/script.py.tmpl)` 取骨架，写到同目录 `scripts/` 下

**脚本与正文怎么分**：能用 if/else 说清的（遍历目录、抽取文本、统计汇总、格式检查、批量改名、模板填充）写成脚本；需要"看情况"的（判断口径、权衡取舍、组织语言）留在正文当纪律。

正文必须写清每一步的执行者（脚本 / Agent）和预计步数，并给出步数预算表——整轮工具步数有上限，超了任务会半途中断。

### Step 3 — 校验（脚本，1 步）

```
run_skill_script
  skill_id: skill-builder
  script: validate.py
  args: [.office-agent/work/skill-draft/<skill-id>]
```

看 JSON 里的 `errors` 与 `warnings`：**errors 必须清零**（未填的 `{{占位符}}`、id 命名不合法、引用了不存在的文件、脚本语法错误、用了 shell 或联网都在此列）；warnings 逐条判断，不合理可以保留但要向用户说明。有 error 就回 Step 2 改，改完重跑。

### Step 4 — 真实素材自测（Agent，1～3 步）

草稿脚本就在工作区里，直接跑：

```
run_workspace_script
  path: .office-agent/work/skill-draft/<skill-id>/scripts/<脚本>.py
  args: [<真实素材路径>]
```

**这一步不能省**。跑不通的脚本装进去只会在用户真正需要时才暴露问题。没有脚本的纯 SOP 技能，改为自己把正文的步骤在脑内走一遍，确认每一步都指明了用哪个工具、路径写法正确。

### Step 5 — 安装（脚本，1 步）

```
run_skill_script
  skill_id: skill-builder
  script: install.py
  args: [.office-agent/work/skill-draft/<skill-id>]
```

安装即生效，无需重启。同名旧版会自动备份。**必须告知用户：在右侧技能面板点「刷新」才能看到它**，以及这个技能下次靠哪句话触发。

### Step 6 — 迭代（脚本 + Agent，2～4 步）

改已有技能时**不要**直接动应用数据目录，先拉回草稿区：

```
run_skill_script
  skill_id: skill-builder
  script: export.py
  args: [<skill-id>, --to-draft]
```

改完必须：升 `version`（修 bug 升补丁位，加步骤升次版本位）+ 在"变更记录"里补一行说明改了什么。然后重跑 Step 3 → Step 5。

### Step 7 — 导出分享（脚本，1 步，仅按需）

```
run_skill_script
  skill_id: skill-builder
  script: export.py
  args: [<skill-id>, --zip]
```

产出 `output/<中文名>-<skill-id>.zip`。告诉用户：同事在技能面板点「导入技能」→「zip / md 文件」选这个包即可。

---

## 步数预算

| 阶段 | 约计步数 |
|------|----------|
| Step 0 判断 + Step 1 采集 | 1～4 |
| Step 2 起草（含读规范与模板） | 2～4 |
| Step 3 校验 + Step 4 自测 | 2～4 |
| Step 5 安装 | 1 |
| **合计** | **≈6～13** |

迭代或导出单独发起，各 2～4 步。若一次要造多个技能，一轮只造一个，装完再说下一个。

---

## 硬规则

- **不要把一次性任务做成技能**。Step 0 的三问是闸门，不是形式。
- **description 只写"何时启用 + 产出什么"，≤60 字**。它每轮对话都进上下文；步骤细节写正文。
- **`name` 必须与目录名逐字相同**。技能 id 取自目录名，不一致会导致 UI 与脚本调用对不上。
- **正文 ≤8000 字符**。超了把细则拆到 `references/`，让使用时按需 `read_skill` 读。
- **脚本禁止 shell 与联网**，禁止 `import office_agent`。这是内网离线环境。
- **禁止直接写应用数据目录**。一切经 `install.py`，它会校验并备份。
- 装完必须提示用户点技能面板的「刷新」。

## 交付物

1. `~/.office-agent/skills/<skill-id>/` — 已安装并启用的技能
2. `.office-agent/work/skill-draft/<skill-id>/` — 草稿留档，下次迭代的起点
3. `output/<中文名>-<skill-id>.zip` — 仅在用户要分享时产出

向用户交付时说清三件事：技能叫什么、下次用哪句话触发、去技能面板点刷新。

## 变更记录

- 1.0.0 — 首版。七步纪律 + validate/install/export 三脚本，配合 Runtime 的 `read_skill` 按需加载正文。
