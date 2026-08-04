# 文书通 · 通用 Plan + 执行 设计规格（推进方案）

| 项 | 内容 |
|---|---|
| 日期 | 2026-08-04 |
| 状态 | P1 已落地；P2 已落地（确认关 + HTML 简要展示 + 续跑 guide） |
| 实施计划 | P1：`docs/superpowers/plans/2026-08-04-agent-plan-execute.md`；P2：`docs/superpowers/plans/2026-08-04-agent-plan-execute-p2.md` |
| 对照基线 | `2026-07-23-office-agent-runtime-design.md` §2 / §7 / §13；现行 `agent_loop` + `ToolExecutor` |
| 动机例 | 多材料重量任务（如本级规定对照多份上位规章审查）；**例证非范围本身** |

---

## 1. Objective

让单 Agent 底座具备**跨领域**的「先规划、再按项执行、可中断续跑」能力，使复杂重量型任务在步数上限与上下文限制下仍可管理、可交付、可恢复——领域方法仍由 Skill / 模型提供，编排协议进底座。

成功口径（产品一句话）：

> 复杂任务不再赌一轮跑完；而是留下可续跑的工作计划，用户说「继续」就能接着干。

---

## 2. Problem

| 现状 | 后果 |
|------|------|
| 单轮 `max_tool_steps`（默认 40）+ 无外置任务状态 | 重量任务中途被截断，进度丢失 |
| Skill 内「步数预算 / 开新对话继续」仅覆盖已知流水线 | 新复杂任务无通用抓手 |
| UI `phase: planning` 只是思考中状态名 | 用户看不到可勾选的工作计划 |
| 规格已预警「长任务步数爆炸」 | 缓解写在纸上，底座未产品化 |

---

## 3. Principles（与产品方式对齐）

1. **单 Agent 足够**：不引入多 Agent / Crew 框架（仍为 Non-Goal）。
2. **状态外置**：Plan 落在工作区，不依赖对话记忆扛全程。
3. **薄协议、厚领域**：底座只规定 Plan 形态、读写/推进工具、触发与续跑纪律；步骤内容与验收标准留给模型与可选 Skill。
4. **Skill 优先补充模板**：若某领域反复出现，再用 Skill 提供「默认步骤模板」；≥2 场景强共用的编排逻辑才进 Runtime（本能力本身已是跨场景共用，故进底座）。
5. **人审关口可表达**：步骤可标 `needs_user`；法律/签发类结论不宣称机器终局。
6. **简单任务不强制 Plan**：避免「通篇校对也先写计划」的仪式感税。

---

## 4. In / Out

### In（全推进范围）

- Plan 工件 schema（JSON）与固定路径约定
- 底座工具：创建/更新/读取 Plan、推进步骤状态（Phase 1起）
- System 纪律：何时建 Plan、如何执行、如何续跑、`finish` 与未完成 Plan 的关系
- 续跑话术约定（用户侧一句话即可恢复）
- 验收夹具：至少 1 个「多步可中断」合成任务
- 分阶段 UI（Phase 3）：进度可见（只读展示优先）

### Out

- 多 Agent、自动并行工人、层级任务图引擎
- 领域专用审查逻辑（规章合规等）进底座——属后续可选 Skill
- 取消 `max_tool_steps` 或改为无限循环
- 公网调度 / 云端队列
- 改动 App Store / 安装器体积策略

---

## 5. Plan 工件

### 5.1 路径

| 文件 | 用途 |
|------|------|
| `.office-agent/work/plan.json` | **唯一权威**机器可读 Plan（当前工作区至多一份 active plan） |
| `工作成果/工作计划.html` | **给人看的简要说明**（从 JSON 渲染；非权威、不支持回写） |

同时只允许一个 `status=active` 的 Plan。新复杂任务若已有 active plan：先 `ask_user` 一次（继续旧计划 / 归档旧计划并新建），或用户明确说「重新规划」则将旧 plan 标 `cancelled` 后新建。

### 5.2 Schema（v1）

```json
{
  "version": 1,
  "id": "plan_<ulid_or_uuid>",
  "goal": "一句话目标",
  "status": "active",
  "approval": "pending",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "steps": [
    {
      "id": "s1",
      "title": "短标题",
      "detail": "可选：怎么做、注意什么",
      "status": "pending",
      "depends_on": [],
      "inputs": ["相对路径或说明"],
      "outputs": ["预期产物相对路径"],
      "needs_user": false,
      "notes": ""
    }
  ],
  "resume_hint": "按工作计划未完成项继续"
}
```

**枚举**

- Plan `status`：`active` | `completed` | `blocked` | `cancelled`
- Plan `approval`（P2）：`pending` | `approved` | `rejected`
  - 缺省字段（P1 旧文件）：按 **`approved`** 兼容，避免卡住续跑
- Step `status`：`pending` | `in_progress` | `done` | `failed` | `skipped`

**硬约束**

- `steps` 至少 2 项（否则不值得建 Plan，应直接执行）
- 任意时刻至多一个 `in_progress` 步骤（串行执行；v1 不做并行）
- `depends_on` 仅引用本 Plan 内 step id；被依赖项非 `done|skipped` 时不得将本步标为 `in_progress`
- `finish` 时若仍存在 `pending|in_progress|failed`：Plan 不得标 `completed`；`finish.summary` 必须含剩余步骤数 + `resume_hint`

### 5.3 触发条件（建 Plan）

满足任一即应先写/更新 Plan 再大批量动手：

1. 用户显式要求规划 / 分步 / 工作计划
2. 预估需要 **>1 个会话** 或 **明显超过约 15 工具步**（多文件批处理、多阶段流水线）
3. 材料规模大（经验阈值：同类源文件 ≥10，或「1 份主件 + ≥3 份对照件」且需逐件产出）
4. 任务含明确人工确认关口（用户说「先列方案给我确认」）

**不触发**：单文件校对、两版对照、单一脚本排版、用户只要改几句措辞。

---

## 6. 工具面（底座）

### 6.1 Phase 1 最小工具集

| Tool | 作用 | 权限 |
|------|------|------|
| `plan_get` | 读取当前 Plan；无则 `ok:false, reason: missing` | 只读 |
| `plan_create` | 写入新 Plan（拒绝在已有 active 上静默覆盖） | 写入类 |
| `plan_update_step` | 更新指定 step 的 status / notes / outputs | 写入类 |
| `plan_set_status` | 更新整个 Plan 的 status（含 cancelled） | 写入类 |

实现要点：

- 读写均经 Workspace 沙箱；路径固定，禁止 Agent 改权威路径参数
- `plan_create` / `plan_update_step` 做 schema 校验，失败返回结构化错误，不写半文件
- 可选副作用：`plan_update_step` 在全部步骤 `done|skipped` 时自动将 Plan → `completed`
- `TOOL_LABELS` 中文名：查看工作计划 / 创建工作计划 / 更新计划步骤 / 更新计划状态

**不在 Phase 1 做**：通用 `plan_patch` 自由 JSON 合并（易脏）；并行 step；Plan 历史多版本库（取消即改 status，文件可另存 `.office-agent/work/plan.archived.<id>.json` 可选）。

### 6.1.1 Phase 2 增补工具 / 行为

| Tool / 行为 | 作用 |
|------|------|
| `plan_set_approval` | 将 `approval` 设为 `approved` / `rejected`（拒绝时可顺带 `cancelled`） |
| `plan_create` 默认 | 新计划 `approval=pending`；并渲染/刷新 `工作成果/工作计划.html`（简要说明，非权威） |
| `plan_update_step` 硬闸 | `approval != approved`（含缺省兼容后的非 approved）时，禁止把任一步标为 `in_progress` / `done`（可允许只改 notes） |
| `render_plan_html` | 纯函数：从 JSON 生成静态 HTML（转义文本、无脚本）；页内写明「如需修改请在对话框提出」 |

### 6.2 与现有工具关系

- 真正干活仍用 `workspace_*` / `run_*` / `read_skill`
- Plan 工具只管家务状态；禁止把业务正文塞进 `notes` 代替 `工作成果/`
- 命中领域 Skill 时：**先 `read_skill`，再决定是否用 Skill 步骤模板填 Plan**（有 Skill 用 Skill 纪律；无 Skill 用通用 Plan）

### 6.3 System 纪律（摘录，实施时写入 `_build_system_prompt`）

**P1 已有**

- 触发条件满足时：先 `plan_create`；禁止无 Plan 空转大批量读写
- 每轮优先 `plan_get`；若有 active plan，只推进**一个**可执行步骤（依赖已满足且非 `needs_user` 待确认）
- `needs_user=true` 的步骤：`ask_user` 一次问清后，用 `plan_update_step` 记下结论再继续
- 接近步数上限或本轮只能完成部分：`finish` 并写明剩余项与「按工作计划继续」
- 用户说「继续 / 按计划继续 / 接着做」：禁止重新规划，除非用户明确要求重来

**P2 增补：确认关（推荐规则）**

1. **新建复杂任务工作计划后，在推进任何业务步骤之前**必须：
   - 确保 `工作成果/工作计划.html` 已写出（目标 + 编号步骤 + **修改须走对话框**的说明）
   - 用 `ask_user` **一次**请用户确认：按此执行 / 要改哪里（对话里说） / 取消  
   - 用户同意 → `plan_set_approval(approved)` 后再执行  
   - 用户要改 → **仅在对话中**按反馈更新 `plan.json`，重渲染 HTML，`approval` 保持/拉回 pending，再确认  
   - 用户取消 → `plan_set_approval(rejected)` + `plan_set_status(cancelled)`，`finish` 说明已取消
2. **跳过确认（不弹 ask_user）**当且仅当：
   - 本轮是续跑（用户说继续/接着做，且已有 `approval=approved` 或 P1 兼容缺省）  
   - 用户明确说「不用确认、直接做完 / 按计划开干不用问我」  
   - 未建工作计划的简单任务（校对/两版对照/单一排版等）
3. **放宽 ask_user 用途**：除缺路径外，**工作计划确认**与 **`needs_user` 步骤**也允许使用；整轮仍最多一次 `ask_user`（确认关占一次则本轮不再问路径——缺路径应在建计划前问清）
4. `finish` 时若 plan 未完成：摘要须含剩余步骤数或标题列表 + resume_hint

### 6.4 用户修改工作计划（简化定稿）

**只支持对话框修改。不支持、不解析用户对展示文件的手改。**

| 做法 | 行为 |
|------|------|
| 对话里提修改意见 | 更新 `plan.json` → 重渲染 `工作计划.html` → `approval=pending` → 再确认 → 再执行 |
| 用户改了 HTML/其它展示文件 | **忽略**；不比对、不同步。确认话术已说明「展示文件仅供查阅」 |

确认 / HTML 页脚固定文案（可微调）：

> 本页为工作计划简要说明，仅供查阅。如需修改步骤或目标，请在对话框中直接提出修改意见，不要改本文件。

**不做：** MD 双写、MD/HTML↔JSON 漂移检测、三选一同步。

---

## 7. 执行与续跑协议

```
用户提出复杂任务
    →（若缺关键路径：ask_user 一次澄清）
    → plan_create（approval=pending）+ 写 工作成果/工作计划.html
    → ask_user 确认工作计划（改计划请对话说明）
    → 用户同意：plan_set_approval(approved)
    → loop:
         plan_get → 选下一可执行 step
         → 若 needs_user: ask_user → update_step
         → 用业务工具完成该步 → plan_update_step(done|failed)
         → 若步数将尽: finish(摘要+resume_hint) 并保持 plan active
    → 全 done: plan_set_status(completed) → finish

续跑（已 approved）：
    → plan_get → 直接推进，不再弹全盘确认
```

**跨会话续跑**：同一工作区、新用户消息含「继续」语义 → Agent `plan_get` → 从首个未完成项推进。不要求同一 `session_id`（工作区即状态边界）。

**失败**：步骤 `failed` + `notes` 写原因；Plan → `blocked` 当且仅当无法自动跳过且需用户决策；否则可 `skipped`（须在 notes 说明）或留给用户「继续」时重试。

---

## 8. 分阶段推进

| 阶段 | 目标 | 交付 | 预估体量 |
|------|------|------|----------|
| **P0 定稿** | 规格确认 | 本文 + Phase1 计划勾选范围 | 评审 |
| **P1 底座 MVP** | 工具 + schema + system 纪律 + 单测 + 合成续跑夹具 | 可 API/对话驱动的 Plan+执行+续跑 | **已完成** |
| **P2 体验加固** | **确认关** + `工作成果/工作计划.html` 简要展示 + guide 续跑话术 + finish 摘要；改计划**仅对话** | 办事人先看见计划、确认后再干、可发现续跑 | 小～中 |
| **P3 UI** | 右侧或对话区只读 Plan 进度（步骤列表 + 状态） | 可见可控，仍不引入多 Agent | 中 |
| **P4 领域模板（可选）** | 如「规章对照审查」Skill：默认 steps 模板 + 脚本分批 | 例证场景达标，反哺通用层 | 按业务单独立项 |

**推荐执行顺序：** P0 → P1 → **P2（当前）** → P3 视内测；P4 不阻塞。

---

## 9. 验收标准

### 9.1 P1 必须

1. Schema 非法写入被拒绝；合法 `plan_create` 落在 `.office-agent/work/plan.json`
2. 存在 active plan 时再次 `plan_create` 失败（除非先 cancelled）
3. `plan_update_step` 尊重 `depends_on` 与「至多一个 in_progress」
4. 合成任务：≥4 步 Plan，人为在中途 `finish` 后，新一轮仅凭「按工作计划继续」能完成剩余步骤并 `completed`
5. 简单任务路径（如单文件「通篇校对」话术）**不强制**建 Plan（评测或提示词用例抽样）
6. 既有 agent_loop / tools 单测不回归；`max_tool_steps` 行为不变

### 9.2 P2 必须

1. 新建计划默认 `approval=pending`；未批准前 `plan_update_step(…, in_progress|done)` 被拒绝
2. 确认路径：写 `工作成果/工作计划.html`（含「仅供查阅、修改走对话框」说明）+ `ask_user` 确认 + `plan_set_approval(approved)` 后方可推进步骤
3. 续跑 / 「不用确认直接做」**不**强制再次全盘确认（规则见 §6.3）；改计划**仅**对话路径（§6.4）
4. 空态/办事能力树可一键填入「按工作计划未完成项继续」
5. `finish.summary` 在未完成时稳定包含剩余步数或步骤标题列表（可用 helper 生成建议摘要，prompt 纪律兜底）
6. system 含 `needs_user` 步骤须先问用户的纪律
7. HTML 对 goal/步骤标题做转义；**无**内联脚本；不实现展示文件→JSON 回写

### 9.3 P3 必须

- UI 能展示 active plan 的步骤与状态（只读即可）；无 plan 时不占版面

### 9.4 非目标验收（明确不测）

- 规章审查法理正确率（属 P4 + 人审）
- 无 Plan 时模型「自己心里有数」的隐式规划质量

---

## 10. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 模型忽略 Plan 工具空转 | System 硬纪律 + 评测夹具 |
| 模型跳过确认直接干 | `approval` 硬闸禁止未批准推进；评测夹具断言 |
| 用户改展示文件期望生效 | 产品明文「仅供查阅」；不解析、不同步（§6.4） |
| 确认关与「ask_user 每轮一次」冲突 | 建计划前问路径；确认占用本轮唯一 ask_user |
| Plan 颗粒度过细导致步数浪费 | 指导：步骤对齐「可独立交付的中间产物」，一般 3～12 步 |
| 与 Skill 四步纪律打架 | 有 Skill 则 Plan 步骤映射 Skill 阶段，不另起炉灶 |
| 写入权限打扰（谨慎模式） | `plan_*` 写入走与 `workspace_write` 同类策略；可评估列入「会话内记住」 |
| 范围膨胀成工作流引擎 | 冻结 Out 列表；并行/子 Plan 一律延期 |

---

## 11. 关键假设

1. 复杂任务以「打开的文件夹」为状态边界，用户接受工作区内过程文件。
2. 内网模型能稳定按 tool schema 调用；偶发违规用校验错误收回，而非静默改文件。
3. 机关用户接受「先看计划再确认执行 / 说继续接着做」，不要求黑盒一次出全量。
4. 默认 `max_tool_steps=40` 短期不变；靠 Plan 分轮，不靠抬上限硬扛。

---

## 12. Open Questions

1. P3 Plan 面板放右侧办事能力区还是对话区顶部？——实现前用一张线框定。
2. ~~展示用 md 还是 html~~ — **P2 已定：静态 HTML 简要说明**；权威仍为 JSON。
3. `plan_*` 是否全部豁免每次确认（标准权限模式）？——建议：标准模式会话内记住，谨慎模式仍确认。

---

## 13. 决策摘要

| # | 决策 |
|---|------|
| D1 | 做**通用** Plan+执行，进 Runtime；领域例证不进本规格 In |
| D2 | 单 Agent + 落盘 `plan.json` + 专用薄工具；不上多 Agent |
| D3 | 先 P1 工具与纪律，再 P2 体验（含确认关），再 P3 UI |
| D4 | 简单任务不强制 Plan；续跑以工作区 Plan 为准 |
| D5（P2） | 复杂任务新建计划后**必须用户确认**再执行；续跑与显式跳过确认除外 |
| D6（P2） | 给人看的简要说明为 `工作成果/工作计划.html`（静态、转义、无脚本）；机器权威仍在 `work/plan.json` |
| D7（P2） | 改计划**只走对话框**；展示文件手改忽略、不回写 |

P1 已执行完毕。P2 按 `docs/superpowers/plans/2026-08-04-agent-plan-execute-p2.md` 实施。
