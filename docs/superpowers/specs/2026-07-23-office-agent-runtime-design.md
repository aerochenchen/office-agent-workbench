# 内网办公 Agent 工作台（Office Agent Runtime）设计规格

| 项 | 内容 |
|---|---|
| 状态 | 已评审通过（§1–§4 + 产品方式 V1.1）；实现计划见 `docs/superpowers/plans/2026-07-23-office-agent-runtime.md` |
| 日期 | 2026-07-23 |
| 版本 | V1.1 |
| 定位 | 类 Claude Code 的**办公域** Agent 底座：工作区 + 对话 + 可安装混合型 Skill；严格内网 |
| 产品方式 | **精炼底座 + 按机器/场景选装·改装 Skill**（重能力留在 Skill，不进 Runtime） |

---

## 1. Problem Statement

How might we 提供一个精炼、定位准确、架构充分的桌面 Agent 运行时，使用户打开本地工作区文件夹后可用自然语言完成办公任务，并通过本地导入的混合型 Skill（`SKILL.md` + scripts）扩展能力——同时仅连接单位私有 DeepSeek、不访问公网，且最大化复用宽松协议开源组件以保留商业闭源盈利空间？

---

## 2. Product Principles（产品方式 · V1.1 定稿）

### 2.1 核心判断（已确认）

1. **当前 Agent 架构底座足够**：工作区、对话、Tool Loop、Skill 加载、内网 Model Gateway 即办公版 Claude Code 的充分集。  
2. **吃配置、占安装体积的是具体 Skill，不是底座**。典型例：公文写作 Skill 内的 DIY RAG（`sentence-transformers` + PyTorch + `bge-small-zh` + numpy/JSON）显著增加磁盘与内存；排版类 Skill 则轻得多。  
3. **理想交付方式**：保持底座精炼统一；按机关电脑配置与业务场景 **安装 / 不装 / 改装 / 降级 Skill**，而不是把重能力堆进 Runtime。

### 2.2 产品分层

| 层 | 职责 | 体积与性能 | 交付 |
|---|---|---|---|
| **Runtime 底座** | UI、工作区沙箱、会话、Tool、Skill 注册、内网 API | 刻意保持轻；面向多数 4GB+ 办公机可用 | 标准安装包（默认） |
| **轻量 Skill** | 如公文排版（脚本触发为主） | 低 | 可随标准包或独立小包 |
| **重量 Skill** | 如公文写作 + 本地向量 RAG | 高（Torch/模型为主） | **可选离线包**；标明推荐内存 |
| **改装 / 降级 Skill** | 同场景无向量或弱检索变体 | 低～中 | 面向老旧机或无 RAG 需求工位 |

### 2.3 能力演进规则

- **默认**：新能力优先做成 Skill（或 Skill 变体），不修改 Runtime 核心。  
- **仅当** ≥2 个 Skill 强共用且复制成本过高时，才评估「可选共享组件」（仍非默认安装）。  
- **禁止**：因单一重量 Skill 的依赖，把 PyTorch/embedding 打进所有人的底座包。

### 2.4 机器基线（对外口径）

| 档位 | 建议配置 | 可用能力 |
|---|---|---|
| 最低 | Win10 / 约 4GB 内存 | 底座对话 + 轻量 Skill（如排版） |
| 推荐 | 约 8GB 内存 | 可启用「公文写作 + 本地 RAG」重量 Skill |
| 交付动作 | 按工位选装 | 导入对应 Skill 包；弱机用不带向量的写作变体或仅排版 |

---

## 3. Goals and Non-Goals

### 3.1 Goals

- 桌面 UI：选择工作区文件夹 + 自然语言多轮对话。
- 自研薄 Runtime：Tool Loop、工作区沙箱、Skill 加载、受控脚本执行、本地审计。
- 兼容现有混合型 Skill：公文写作（Agent 叙事 + 脚本侧 RAG）、公文排版（脚本为主）。
- **Skill 可选装**：标准包不含重量 RAG 依赖；写作/RAG 以可选离线包交付。
- 严格内网：LLM 仅白名单私有 API；Skill 仅本地/内网离线包导入；embedding 模型离线随包装，禁止运行时连 HuggingFace。
- 开源降本 + 闭源盈利：壳与通用零件用 MIT/Apache 等；Skill/模板/方法论/加固闭源可售。

### 3.2 Non-Goals（首版）

- 公网 Skill 市场、自动在线更新、账号体系。
- 任意 Shell、公网 MCP 生态。
- CrewAI 等重型多 Agent 框架（可预留嵌套会话接口）。
- 完整 IDE（diff、调试器、终端仿真器）。
- 将产品本身做成「综治固定四步流水线」；该类能力以下沉 Skill 形式提供。
- **平台级 RAG 引擎**（无内置 LlamaIndex/Chroma/统一 `rag_*` Tool）；RAG 由需要它的 Skill 自闭环实现。
- 因写作 Skill 而强制加重大家的默认安装包。

---

## 4. Recommended Direction

**方案 B：自研 Office Agent Runtime**，用开源组件装配桌面壳与通用 Agent 零件，自研并闭源办公 Skill 与内网加固。

不整仓 fork 不明 Coding Agent 桌面项目；不默认引入 CrewAI。复杂业务流程与重依赖写在 Skill 内；**底座保持薄，能力靠选装 Skill 扩展**。

---

## 5. Architecture Overview

```
UI (Tauri WebView：文件树 | 对话 | Skill 面板)
        ↕ invoke / event
Runtime Core
  ├─ WorkspaceService    工作区根、文件树、路径沙箱
  ├─ SessionService      多会话、消息、SQLite 持久化
  ├─ SkillRegistry       安装/启用、摘要注入、共享脚本解析
  ├─ ToolExecutor        内置 Tool、权限确认、审计日志
  └─ ModelGateway        OpenAI 兼容 → 仅白名单内网 DeepSeek
        ↕
{app_data}/skills/*  +  {app_data}/shared-scripts/*
{workspace}/         用户文件（不复制进 app_data）
```

Runtime **不包含** embedding、向量库、RAG 检索服务。重依赖仅随已安装 Skill 出现。

### 5.1 Open Source vs Proprietary Split

| 层 | 策略 | 示例 |
|---|---|---|
| 桌面壳 | 开源组件 | Tauri 2（MIT） |
| 会话存储 | 开源组件 | SQLite |
| 模型客户端 | 开源/自封装 | OpenAI 兼容 SDK |
| 办公编解码 | 开源库（Skill 脚本使用） | python-docx、openpyxl、pdfplumber 等 |
| 胶水与内网策略 | 自研（可不开源） | 白名单、沙箱、审计、导入校验 |
| Skill / 模板 / 方法论 | **闭源商品** | gongwen-rag-writing、government-document-format |
| 重量 Skill 依赖 | **随可选 Skill 包**，不进标准底座 | PyTorch、bge-small-zh、sentence-transformers |

禁止默认引入 AGPL 壳、带强制公网遥测且难关闭的框架作为核心依赖。依赖树每次发版做许可证扫描。

---

## 6. Skill Package Specification

### 6.1 Directory Layout

```
{skill-id}/
  SKILL.md                 # required
  scripts/                 # optional
  references/              # optional
  templates/               # optional
  assets/                  # optional
  skill.lock.json          # optional: deps / shared scripts
```

### 6.2 SKILL.md Frontmatter (minimum)

```yaml
---
name: gongwen-rag-writing
description: 何时启用：基于素材与模板做机关文稿叙事写作
version: 1.0.0
tier: heavy                    # light | heavy —— 影响安装提示与推荐配置
min_ram_gb: 8                  # 可选；weight Skill 建议填写
permissions:
  - workspace_read
  - workspace_write
  - run_python
shared_scripts:
  - format_gongwen
---
```

正文为 Agent 可执行的方法论/阶段说明（写作 Skill 的核心智力资产）；排版类 Skill 可将正文作为脚本说明书与失败时参考。

### 6.3 Install and Discovery (air-gapped)

- 导入：本地 `.zip` 或文件夹 → 结构校验 → `{app_data}/skills/{id}/`。
- 启用/禁用：全局或按工作区；系统提示注入「已启用 Skill」的 name/description。
- 共享脚本：`{app_data}/shared-scripts/`；Skill 用逻辑名引用（如 `format_gongwen`）。
- 兼容：可选只读兼容 `~/.hermes/scripts/`；**新安装默认只写 app_data**。
- 不做：公网市场、客户端自动下载。
- **重量 Skill**：导入时展示 `tier` / `min_ram_gb` 与体积提示；允许用户在低配机仍强制安装（自行承担卡顿风险）。

导入时展示权限清单，用户确认后启用。

### 6.4 Mapping Existing Skills

**公文写作 `gongwen-rag-writing`（混合，Agent 不可替代性高 · tier=heavy）**

1. 读 SKILL.md 六阶段  
2. `run_skill_script` → `build_index.py`  
3. `run_skill_script` → `analyze_template.py`  
4. Agent 叙事规划  
5. 循环：`search_argument.py` + Agent 撰写 → `workspace_write`  
6. Agent 自审  
7. `run_shared_script(format_gongwen)`（或包内入口）

**公文排版 `government-document-format`（混合，Agent 多为触发器 · tier=light）**

1. 识别目标 `.docx`  
2. `run_shared_script(format_gongwen, path)`  
3. 失败或用户追问规则时再读 SKILL.md / references  

### 6.5 RAG 职责边界（Skill 自闭环）

平台层 **不提供** RAG。公文写作 Skill 现状即目标形态：

| 能力 | 提供者 |
|---|---|
| Embedding（如 `BAAI/bge-small-zh-v1.5`） | Skill 脚本（`sentence-transformers`） |
| 存储与检索 | Skill 脚本（numpy + JSON，非 Chroma/FAISS） |
| 结构感知分块 | Skill 脚本（公文编号体系解析） |
| 叙事与撰文 | Agent 纯推理 |
| Runtime | 仅 `run_skill_script` 等调度 |

**内网交付约定：**

- Embedding 模型随 **重量 Skill 离线包** 携带，脚本只读本地模型目录；禁止首次运行联网下载。  
- 索引默认落在 **当前工作区**（如 `.office-agent/rag/<skill-id>/`），随项目可重建。  
- 模型 **按需加载**，任务结束后宜释放，避免空闲常驻占满 4GB 机内存。  
- 弱机可选 **无向量写作变体 Skill**（关键词/指定素材文件），不装 Torch 包。

规模假设：适合几十份公文素材；非百万级语料库。超出后再评估可选共享组件，仍不默认进底座。

---

## 7. Tools and Permissions

### 7.1 Built-in Tools

| Tool | Purpose | Notes |
|---|---|---|
| `workspace_list` | 列目录 | 仅工作区内 |
| `workspace_read` | 读文件 | 仅工作区内 |
| `workspace_write` | 写/另存 | 仅工作区内；可要求确认 |
| `run_skill_script` | 运行某 Skill 的 `scripts/*.py` | 无任意 shell |
| `run_shared_script` | 运行共享脚本 | 逻辑名解析到 shared-scripts |
| `ask_user` | 澄清 / 选文件 | |
| `finish` | 结束并汇总 | |

首版**不提供**通用 `shell`。二期若需要，默认拒绝，需显式高权限。

### 7.2 Permission Modes (UI)

1. **谨慎**：每次写文件 / 跑脚本确认  
2. **标准（默认）**：同会话同脚本可记住；写文件可按策略确认  
3. **信任工作区**：本工作区会话内自动允许已声明权限（仍禁越界与任意 shell）

### 7.3 Security Baseline

- 文件系统：沙箱根 = 当前工作区；越界拒绝。  
- 网络：仅配置的 DeepSeek API Host；脚本默认无外网（含禁止拉 HuggingFace）。  
- 执行：仅允许应用配置的 Python；记录 skill、脚本、参数、退出码、耗时。  
- 审计：本地 SQLite；不上报。

### 7.4 Tool Loop

```
user message
  → inject: workspace summary + enabled skill catalog
  → LLM (intranet DeepSeek) → text or tool_calls
  → execute tools → append results
  → repeat until finish / step limit / user stop
```

复杂多步编排优先写在 Skill 内；底座预留未来嵌套会话，不上 CrewAI。

---

## 8. UI Information Architecture

```
┌──────────────┬─────────────────────────────┬──────────────────┐
│ 工作区文件树  │  对话 / 任务流               │ Skill / 运行详情  │
│ 打开/刷新     │  消息 + 工具卡片 + 输入框     │ 安装/启用/导入    │
└──────────────┴─────────────────────────────┴──────────────────┘
设置：API · 模型 · 权限模式 · 日志
```

Skill 面板需区分 **已装轻量 / 重量 Skill**，重量项显示推荐内存提示。

### 8.1 Key Interactions

- 打开工作区 → 设沙箱根 → 浅层文件树。  
- 多会话绑定同一工作区。  
- 可附带/选中文件作为上下文。  
- 工具卡片展示脚本名、状态、耗时、可展开输出。  
- 产物路径可调系统默认程序打开。  
- **导入 Skill**：标准流程；若 `tier=heavy`，确认框含配置建议。

### 8.2 Local Storage

```
{app_data}/
  config.json
  db/sessions.sqlite
  skills/                 # 仅已选装 Skill
  shared-scripts/
  logs/
```

工作区内可选：`.office-agent/rag/<skill-id>/`（索引等缓存，不进安装包）。

### 8.3 Error / Interrupt Behavior

| Case | Behavior |
|---|---|
| API unreachable | 明确内网模型不可用；不回落公网 |
| Script non-zero | 卡片失败 + stderr；结果回灌 Agent |
| User stop | 取消进行中的请求/子进程（尽力） |
| Step limit | 停止并汇总已完成步骤与产物 |
| Missing shared script | 启用前校验失败 |
| 重量 Skill 缺本地模型目录 | 启用/运行前失败并提示「需完整离线包」 |

### 8.4 UI Non-Goals (v1)

无代码 diff、无终端仿真、无公网插件市场、无多工作区复杂分屏（先单工作区 + 多会话）。

---

## 9. Data Flow (one turn)

1. UI 提交 `user_message` + optional `attached_paths`。  
2. Session 组装：系统角色（办公 Agent）+ 启用 Skill 摘要 + 历史消息。  
3. ModelGateway 流式响应；解析 `tool_calls`。  
4. ToolExecutor 执行并写审计；结果追加为 tool 消息。  
5. 循环直至文本回复或 `finish`。  
6. UI 订阅 token 流与工具事件；持久化 SQLite。

工作区切换：结束或确认中断进行中任务后切换沙箱根。

---

## 10. Packaging, Milestones and Acceptance

### 10.1 Packaging（与产品方式对齐）

| 包 | 内容 | 目标机 |
|---|---|---|
| **标准底座包** | Runtime + 可选轻量 Skill（如排版）+ 共享排版脚本；**无** Torch/bge | 多数办公机（含约 4GB） |
| **写作 RAG 可选包** | `gongwen-rag-writing` + 离线 embedding 模型 + 声明依赖 | 推荐约 8GB |
| **降级写作包（可选）** | 无向量或弱检索变体 | 老旧机仍要「辅助写作」时 |

### 10.2 Milestones

| Phase | Goal | Indicative effort | Done when |
|---|---|---|---|
| M0 | Tauri + 工作区 + 对话连内网 API | 3–5 days | 流式聊天可用 |
| M1 | Tool Loop + 文件工具 + 受控 Python（轻依赖） | 5–8 days | 无重量 Skill 也能读写与跑白名单脚本 |
| M2 | Skill 导入/启用/权限 + tier 提示 | 3–5 days | zip 安装；开关影响行为；heavy 有提示 |
| M3 | 迁入排版（轻）+ 写作 RAG（重，可选包） | 5–10 days | 两路径均可；标准包可不含写作 |
| M4 | 内网加固、双包/可选包安装、许可证 | 3–5 days | 断网策略；标准包体积不受 Torch 绑架 |

### 10.3 Acceptance Criteria (v1)

1. 工作区沙箱有效（越界读写失败）。  
2. 仅白名单内网 DeepSeek；断公网无偷偷外联。  
3. 本地导入 Skill；权限未确认则不可用高危能力。  
4. **标准底座包不含** PyTorch / bge 等写作 RAG 重依赖。  
5. 排版 Skill 可对 docx 触发共享脚本并回传结果。  
6. 选装写作 RAG 包后，主路径可完成（允许少量人工澄清）；模型离线可用。  
7. 工具与脚本结果可在 UI 追溯；审计落库。  
8. 许可证扫描无 AGPL/GPL 污染；NOTICE 齐备。

---

## 11. Relationship to Prior Internal Spec

| Document | Role |
|---|---|
| `docs/综治办公私有AI智能体-内部技术定稿版-V1.0.docx` | 历史场景/流水线视角；内网、避 AGPL、模板导出等约束仍有效 |
| **本设计** | **现行产品基线**：精炼 Runtime + 按配置选装 Skill |

冲突时以本设计为准。原「默认四步 Pipeline」改为「可由 Skill 实现的一种编排」。原「平台默认 LlamaIndex/Chroma」**不采用**。

---

## 12. Commercial Model Alignment

- 项目定制：机关模板、Skill 选装组合、联调。  
- 年维：Skill/模板/规则更新、按工位加减包、内网问题排查。  
- 单机授权：二期可对 skill id / 安装实例做授权校验。  
- 「互联网成熟 Skill」落地：人工精选 → 打离线包 → 本地导入；重量包单独标注配置要求。

---

## 13. Key Risks and Mitigations

| Risk | Mitigation |
|---|---|
| 长任务 Tool 步数爆炸 | Skill 分阶段；步数上限；UI「继续」 |
| Agent/脚本职责不清 | SKILL.md 标明谁执行；排版尽量纯脚本 |
| Windows 嵌入 Python 打包难 | M1 尽早打通轻量 `run_python`；Torch 仅进可选包 |
| 写作 RAG 拖垮 4GB 机 | 不默认安装；tier 提示；按需加载；提供降级 Skill |
| Hermes 路径习惯 | M3 兼容层；默认 app_data |
| 误把 RAG 做进底座 | 本规格 §2 / §6.5 明确禁止 |

---

## 14. Key Assumptions

- [ ] 内网 DeepSeek（OpenAI 兼容）可用，含鉴权与足够上下文。  
- [ ] 现有两个混合 Skill 可迁路径（共享脚本进入 Runtime 管理）。  
- [ ] 首版用户接受「本地导入 / 选装 Skill」，不要求公网商店。  
- [ ] 商用盈利主要靠闭源 Skill/模板/交付，而非开源壳本身。  
- [ ] 机关接受「底座轻 + 写作包可选」的交付说明与内存基线。

---

## 15. Open Questions (non-blocking for M0)

- 前端栈具体选型（React/Svelte/纯 HTML）——实现计划阶段定，不影响本架构。  
- Skill 授权校验（机器码）是否进 M4 还是更后。  
- 是否未来开源「无 Skill 的社区版壳」——可选，非首版范围。  
- 降级写作 Skill 是否与 RAG 版并行维护，或仅项目定制时提供。

---

## 16. Approval Record

| Section | Topic | Status |
|---|---|---|
| §1–§4 原设计块 | 架构 / Skill·Tool / UI / 里程碑 | Approved 2026-07-23 |
| V1.1 产品方式 | 精炼底座 + 按配置选装/改装 Skill；RAG 留在 Skill；双包交付 | Approved 2026-07-23（用户确认） |

---

## Spec Self-Review Checklist

- [x] 无 TBD/占位未解释项（Open Questions 已标明非阻塞）  
- [x] 与旧「综治流水线默认实现」冲突已声明以本设计为准  
- [x] 严格内网与「互联网 Skill」表述一致（离线导入）  
- [x] 范围：首版不做项已列出  
- [x] 现有两个 Skill 的混合分工已映射到 Tool  
- [x] RAG 职责在 Skill；底座不内置；重量依赖不进标准包  
- [x] 机器基线与选装策略已写入产品原则  
