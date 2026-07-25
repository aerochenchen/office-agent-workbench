# 文书通全面体检与路线图

| 项 | 内容 |
|---|---|
| 状态 | 已批准（2026-07-25；macOS 公证排除） |
| 日期 | 2026-07-25 |
| 版本 | V1.0 |
| 范围 | 产品/架构全面体检：缺陷分级、改进方向、1～2 个季度路线图 |
| 对照基线 | `docs/superpowers/specs/2026-07-23-office-agent-runtime-design.md`（V1.1） |
| 可视化看板 | Cursor Canvas：`wenshutong-audit-roadmap.canvas.tsx` |

---

## 1. 目的与边界

### 1.1 目的

在「可内测」节点对文书通做一次全面体检：对照设计验收找出功能与安全缺口，给出可排期的改进与路线图，作为后续 Sprint 实施计划的输入。

### 1.2 证据边界

- 基于源码、设计规格、本地 Runtime pytest（**77 passed**，2026-07-25）。
- **未**做机关目标机安装、公文写作 RAG 全链路实测、正式许可证扫描。
- 标「待验证」的项需在目标环境补测后再定性。

### 1.3 交付约定（已确认）

- 交付形态：**一份总览规格 + Canvas 看板**（方案 1）。
- **macOS 公证不做**：mac 包仅供开发者笔记本内测；对外/机关交付以 **Windows 标准安装包** 为主。

---

## 2. 总体健康度

### 2.1 一句话结论

文书通已具备**内测可用的主路径**（开工作区 → 多轮对话 → 跑轻量 Skill → Win/mac 打包），但对照设计 V1.1 的 v1 验收，**安全与可追溯明显未齐**——适合小范围试用，不宜按「加固完成」对外交付。

### 2.2 分层成熟度（估）

| 层级 | 成熟度 | 说明 |
|------|--------|------|
| Runtime 底座 | 可用 | Tool loop / 会话 / Skill / Gateway 闭环；77 测全绿 |
| 桌面壳 | 可用偏糙 | 三栏成形；离线门禁弱、无取消生成、无前端测试 |
| 预置技能 ×3 | 可用 | 排版 / 批量整理 / 创建技能；写作 RAG 仍为可选包 |
| 安全基线 §7 | 缺口大 | 权限档、脚本隔离、审计落库大多未落地 |
| 打包交付 | 内测级 | Win NSIS + mac DMG（未公证，且公证不在范围）；文档仍有旧品牌名 |

粗估：**功能 ~70%**，**安全基线 ~40%**。

### 2.3 对照设计 §10.3 验收

| # | 验收项 | 状态 | 说明 |
|---|--------|------|------|
| A1 | 工作区沙箱有效 | 部分通过 | Tool 沙箱 + 脚本 env/argv 约束；脚本进程级仍可逃逸（分期） |
| A2 | 仅白名单内网 API | 部分通过 | Gateway 有 host 白名单；脚本无网络隔离 |
| A3 | Skill 权限未确认则不可用高危能力 | 部分通过/已修 | stream 路径强制确认；sync `/chat` 桌面不用（非交互自动放行） |
| A4 | 标准包不含 Torch / bge | **通过** | 分层交付符合产品原则 |
| A5 | 排版 Skill 触发共享脚本 | **通过** | `government-document-format` + `format_gongwen` |
| A6 | 选装写作 RAG 主路径 | 待验证 | 可选包存在；需目标机端到端 |
| A7 | 工具可追溯；审计落库 | 通过 | Sprint A 已接线生产 `AuditLog`；UI 有工具步骤 |
| A8 | 许可证扫描 / NOTICE | 待验证 | 设置页有 OSS 致谢；缺系统化扫描流水线 |

---

## 3. 缺陷清单

分级约定：

- **Critical**：安全/数据风险或设计安全基线未落地  
- **P0**：内测前建议必堵  
- **P1**：应尽快修  
- **P2**：技术债与打磨  

### 3.1 Critical

| ID | 域 | 问题 | 证据位置 |
|----|-----|------|----------|
| C1 | 安全 | 任意 Python 脚本 ≈ 完整用户权限，无 FS/网络 jail（Sprint B 已修·分期：env 断网 + argv 路径校验，非完整 jail） | `runtime/.../tools.py` `_run_python` |
| C2 | 安全 | 生产路径未接线 `AuditLog`（Sprint A 已修） | `app.py` `_prepare_chat` |
| C3 | 安全 | `permission_mode` / Skill `permissions` 为死字段（Sprint B 已修） | `ToolExecutor` / `skills.py` |

### 3.2 P0

| ID | 域 | 问题 | 证据位置 |
|----|-----|------|----------|
| P0-1 | 安全 | Zip 安装 `extractall`，存在 Zip Slip（Sprint A 已修） | `skills.install_zip` |
| P0-2 | 安全 | `GET /config` 返回明文 `api_key`（Sprint A 已修） | `app.py` `/config` |
| P0-3 | UX | Runtime 离线无阻断，仍可发送/开文件夹（Sprint A 已修） | `App.tsx` health |
| P0-4 | UX | 错误日志路径写死 Windows `%TEMP%`，macOS 误导（Sprint A 已修） | `runtimeClient.ts` |
| P0-5 | UX | 新建/删除会话无 try/catch（Sprint A 已修） | `App.tsx` handlers |

### 3.3 P1

| ID | 域 | 问题 |
|----|-----|------|
| P1-1 | 产品 | 无取消生成（设计 §8.3 User stop）（Sprint B 已修） |
| P1-2 | 产品 | Seed `overwrite=True` 覆盖用户改过的预置 Skill（Sprint B 已修） |
| P1-3 | 产品 | 无 Skill 卸载 API；浏览器模式几乎无导入入口（Sprint B 已修） |
| P1-4 | 文档 | README/打包文档漂移（文件树描述、旧品牌「办公智能体工作台」）（Sprint A 已修） |
| P1-5 | 安全 | WebView `CSP: null`；CORS `allow_origins=["*"]` + credentials（Sprint B 已修） |

### 3.4 P2

| ID | 域 | 问题 |
|----|-----|------|
| P2-1 | 债 | `WorkspaceTree` 死代码；`attached_paths` 无 UI |
| P2-2 | 债 | 前端零自动化测试；`logs/` 几乎未用 |
| P2-3 | 债 | 依赖清单不一致（如 `python-pptx`、`pydantic-settings`、pytest 进 runtime requirements） |

### 3.5 刻意未升 Critical

- **同机无 token 的 localhost API**：内网桌面可接受；记入 Q+2「同机加固」，不阻塞内测。  
- **写作 RAG 端到端**：标待验证，目标机实测后再定性。

---

## 4. 改进原则与能力取舍

### 4.1 原则

1. 先堵安全与内测门禁，再补产品闭环，最后做体验与生态。  
2. 新能力优先进 Skill，不堆 Runtime（延续 V1.1）。  
3. 脚本「完全 jail」可分期；**审计、权限确认、Zip/密钥脱敏** 不可再拖。

### 4.2 建议做 / 分期 / 不做

| 方向 | 建议 | 理由 |
|------|------|------|
| 权限确认 UI + 审计落库 | **必做** | 设计已写；否则无法对机关讲安全故事 |
| 脚本强隔离（容器级） | **分期** | 先禁越界写 + 断网环境；完整 jail 成本高 |
| 恢复左侧文件树 | 可选 | 「用系统默认程序打开产物」性价比可能更高 |
| 公网 Skill 市场 | **不做** | 与内网 Non-Goal 冲突 |
| 平台级 RAG | **不做** | 保持 Skill 自闭环 |
| 多工作区并行 | **暂缓** | 单工作区 + 多会话已够内测 |
| **macOS 公证 / Developer ID 分发** | **不做** | mac 仅笔记本测试；机关交付以 Windows 为主 |

---

## 5. 路线图

### 5.1 Sprint A（约 1–2 周）· 内测排雷

| 工作项 | 对应缺陷 |
|--------|----------|
| 生产接线 `AuditLog` | C2 |
| Zip 安全解压（防 Zip Slip） | P0-1 |
| `GET /config` 不再返回明文 key | P0-2 |
| Runtime 离线阻断 + 跨平台日志路径 + 会话 CRUD 错误处理 | P0-3 / P0-4 / P0-5 |
| README / 打包文档品牌与实现对齐 | P1-4 |

**完成标准：** 小范围安装可用；密钥不回明文；恶意 zip 不能写穿目录。

### Sprint A 完成记录

| 项 | 状态 |
|----|------|
| C2 AuditLog 接线 | 已完成 2026-07-25 |
| P0-1 Zip Slip | 已完成 |
| P0-2 配置脱敏 | 已完成 |
| P0-3/4/5 UX | 已完成 |
| P1-4 文档 | 已完成 |

### 5.2 Sprint B（约 3–6 周）· 安全基线

| 工作项 | 对应缺陷 |
|--------|----------|
| 落地 `permission_mode`（至少谨慎/标准 + UI） | C3 |
| 脚本约束：限制写工作区外 + 断网环境（软硬结合） | C1 |
| 取消生成、Skill 卸载、Seed 不盲覆盖 | P1-1 / P1-2 / P1-3 |
| CSP / CORS 收紧 | P1-5 |

**完成标准：** 设计 §10.3 的 A3、A7 可宣称达标；A1 对外声明「Tool 沙箱 + 脚本约束边界」清晰（完整进程级 jail 可再分期）。

**实施计划：** `docs/superpowers/plans/2026-07-25-wenshutong-sprint-b-security.md`（7 Tasks；C1 不含容器级 jail）。

### Sprint B 完成记录

| 项 | 状态 |
|----|------|
| C3 `permission_mode` + UI | 已完成 2026-07-25 |
| C1 脚本约束（env 断网 + argv 路径校验；非完整 jail） | 已完成 2026-07-25 |
| P1-1 取消生成 | 已完成 2026-07-25 |
| P1-2 Seed 不盲覆盖 | 已完成 2026-07-25 |
| P1-3 Skill 卸载 | 已完成 2026-07-25 |
| P1-5 CSP / CORS 收紧 | 已完成 2026-07-25 |

### 5.3 Q+1 · 产品闭环

- 附件 / 选中文件上下文（`attached_paths` 接 UI）  
- Markdown 气泡；产物「用系统默认程序打开」  
- ~~写作 RAG 目标机端到端验收；决定是否做「无向量降级写作 Skill」~~ → **本轮明确不做（C）**  
- 安装前结构校验（Runtime 轻量 `skill_validate`，对标 skill-builder 核心规则）

**实施计划：** `docs/superpowers/plans/2026-07-25-wenshutong-q1-product-loop.md`（Tasks 1–7；范围 A+B+D）。

### Q+1 完成记录

| 项 | 状态 |
|----|------|
| A 附件 / `attached_paths` UI | 已完成 2026-07-25 |
| B Markdown 气泡 | 已完成 2026-07-25 |
| B 产物「系统默认程序打开」 | 已完成 2026-07-25 |
| C 写作 RAG 端到端 / 无向量降级 Skill | **跳过 / 本轮不做** |
| D 安装前 `skill_validate` 结构校验 | 已完成 2026-07-25 |

**验收：** 2026-07-25 · 分支 `q1-product-loop` · Runtime pytest **126 passed** · desktop `npm run build` 通过。  
**提交摘要：** `9c377b1` plan → `b9802e6`/`e320c76` A 附件 → `6e625ef`/`e65bc7d` B Markdown/打开产物 → `9ff8765`/`71ba311` D 安装校验。

### 5.4 Q+2 · 交付与生态（Windows 为主）

- 许可证扫描流水线 + NOTICE  
- 前端冒烟测试；turn_id / 工具与审计贯通  
- 同机 API token（Skill 本地许可证 / 机器码：**本轮跳过**）  
- **本轮范围锁定：A+B+C(token only)**（2026-07-25；Task 5 不做）  
- **本轮不做：** 写作 RAG / 无向量降级 Skill；完整脚本 jail；Skill 授权文件  
- **明确排除：** macOS 公证  

**实施计划：** `docs/superpowers/plans/2026-07-25-wenshutong-q2-delivery.md`（Tasks 1–4 + 6；Task 5 跳过）。

### 5.5 规格落盘后的建议下一动作

1. 用实施计划技能把 **Sprint A** 拆成可执行任务。  
2. 在 1 台 Windows +（可选）1 台 Mac 笔记本上跑 VERIFY 清单，并各跑通排版 / 批量整理一条真用户路径。  
3. Mac 仅验证开发与内测流程；验收口径不要求公证或 Gatekeeper 正式分发。

---

## 6. 与现行设计的关系

| 文档 | 关系 |
|------|------|
| `2026-07-23-office-agent-runtime-design.md` | 产品与架构基线；本审计对照其 §7 / §8 / §10.3 |
| 本文件 | 现状差距与排期；**不修改**底座「精炼 Runtime + 选装 Skill」原则 |
| 后续 `docs/superpowers/plans/*` | Sprint A/B 的详细实施计划（待本规格批准后编写） |

冲突时：产品原则以 2026-07-23 设计为准；**缺口与优先级以本审计为准**，直至对应项合入并更新验收状态。

---

## 7. 审批记录

| 节 | 主题 | 状态 |
|----|------|------|
| §1 总评与验收对照 | 健康度 / §10.3 | 用户认同 2026-07-25 |
| §2 缺陷清单 | Critical–P2 | 用户认同 2026-07-25 |
| §3 路线图 | Sprint A/B + Q+1/Q+2 | 用户认同 2026-07-25；修正：macOS 公证不做 |

---

## Spec Self-Review

- [x] 无 TBD/空占位（待验证项已标明证据边界）  
- [x] 与 §1–§3 用户确认一致；macOS 公证已排除  
- [x] 范围可拆为 Sprint A 单一实施计划，不过大  
- [x] 「部分通过 / 未达标 / 待验证」含义在文中有定义或上下文  
