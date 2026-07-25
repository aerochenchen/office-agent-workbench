# 文书通 Q+2 · 交付与生态（A+B+C）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐发版许可证闸门与 NOTICE、对话可观测与前端冒烟、本机 API token，使 Windows 标准包具备「可合规交付 + 可排障 + 同机不裸奔」的基线。

**Architecture:** 许可证以现有 `scripts/check_licenses.sh`（Python）为轴，补 npm 扫描并生成/打包 `NOTICE`。可观测在 SSE `started` 注入 `turn_id`，工具事件带上该 id，AuditLog 可选扩展列；桌面用 Vitest 做纯逻辑冒烟。同机加固：Tauri 生成 token → 环境变量注入 sidecar → FastAPI 中间件校验。

**本轮跳过：** Task 5 Skill 本地许可证（含 `license_required` / 机器码）— 用户 2026-07-25 确认先不做。

**Tech Stack:** bash · pip-licenses · license-checker（或等价）· FastAPI middleware · Tauri env · Vitest · pytest

**Spec:** `docs/superpowers/specs/2026-07-25-wenshutong-audit-roadmap-design.md` §5.4（仅 A/B/C）

## Global Constraints

- **做 A+B+C**；**不做**写作 RAG / 无向量降级 Skill（原 Q+1·C）；**不做**完整脚本 jail；**不做** macOS 公证；**不做**公网 Skill 市场。
- Skill 授权：**本轮不做机器码 / HWID**；仅本地 `licenses/{skill_id}.json`（或同类）校验。机器码留后续。
- `/health`（及可选 `/shutdown`）可无 token，便于探活；其余 API 在 **token 已配置时**强制校验。开发模式：未设置 `OFFICE_AGENT_API_TOKEN` 时保持现状（不强制），便于 `pytest` / `dev.sh`；**打包桌面路径必须设置 token**。
- 许可证：GPL/AGPL **失败退出**；LGPL 允许。NOTICE 进标准安装包资源或仓库根并由打包脚本拷贝。
- 品牌：文书通。英文 conventional commits；用户要求或执行本计划时再 commit。

---

## Locked product decisions

| 项 | 决定 |
|----|------|
| A NOTICE | 脚本生成 `NOTICE`（Python + npm 摘要）+ 打包进 Windows 标准包；设置页「关于」链到说明或展示摘要 |
| B turn_id | 每轮 chat 生成 UUID；`started` SSE 携带；工具 start/done 携带；AuditLog 增加可选 `turn_id` 列（兼容旧库） |
| B 前端测试 | Vitest：`runtimeClient` 解析 / token header / 路径工具等纯函数；不做 Playwright 全 UI |
| C token | `Authorization: Bearer <token>`；Tauri spawn 时写入 env + 前端可读（invoke 或内嵌配置），`runtimeClient` 统一带头 |
| C Skill 授权 | **本轮跳过**（原 Task 5） |

---

## File Structure

```
scripts/
  check_licenses.sh          # 扩展：可选调 npm；或并列 check_licenses_npm.sh
  generate_notice.sh         # NEW — 写出 NOTICE
NOTICE                         # NEW（生成物，可提交）
packaging/README-standard.md   # 发版步骤对齐
runtime/src/office_agent/
  auth.py                    # NEW — token 中间件 + license 读写
  app.py                     # 挂载中间件；SSE turn_id
  audit.py                   # 可选 turn_id 列
  agent_loop.py / tools.py   # 事件带 turn_id
  skills.py / skill_validate.py  # license_required
apps/desktop/
  src/lib/runtimeClient.ts   # Bearer + turn_id 类型
  src/lib/*.test.ts          # NEW vitest
  src-tauri/src/lib.rs       # 生成/注入 token；expose 给前端
  package.json               # vitest + license-checker
runtime/tests/
  test_auth.py               # NEW
  test_app_api.py / test_audit.py / test_skills.py
```

---

### Task 1: A — npm 许可证扫描 + NOTICE 生成

**Files:**
- Modify: `scripts/check_licenses.sh` 和/或 NEW `scripts/check_licenses_npm.sh`
- NEW: `scripts/generate_notice.sh`
- NEW/Update: 仓库根 `NOTICE`
- Modify: `packaging/README-standard.md`、`packaging/VERIFY-windows.md`（发版必跑）
- Modify: `apps/desktop/package.json`（devDependency + script）
- Optionally: `SettingsModal` / `brand.ts` 指向 NOTICE 存在说明

**行为:**
- Python：沿用 pip-licenses `--fail-on` GPL/AGPL。
- npm：对 `apps/desktop` 扫描，GPL/AGPL 失败。
- `generate_notice.sh` 汇总写出人类可读 `NOTICE`（包名、版本、许可证）。
- 文档写明：打 Windows 标准包前必须 `check_licenses` + `generate_notice`。

- [ ] **Step 1:** 本地跑通现有 `check_licenses.sh`；补 npm 扫描脚本与 package.json script。
- [ ] **Step 2:** 实现 `generate_notice.sh`，生成/更新 `NOTICE`。
- [ ] **Step 3:** 更新 packaging 文档与 VERIFY 清单（可选→必做或标注发版门禁）。
- [ ] **Step 4:** Commit `chore: add npm license scan and NOTICE generation`

---

### Task 2: B — chat turn_id 贯通 SSE + AuditLog

**Files:**
- Modify: `runtime/src/office_agent/app.py`、`agent_loop.py`、`audit.py`、`tools.py`（若 audit 签名变）
- Modify: `runtime/tests/test_app_api.py`、相关 audit 测试
- Modify: `apps/desktop/src/lib/types.ts` / `runtimeClient.ts`（解析 `turn_id`；UI 可仅调试展示或藏在工具行 data 属性）

**行为:**
- `_prepare_chat` / stream 路径生成 `turn_id = uuid4()`。
- SSE：`started` 含 `turn_id`；`tool_start` / `tool_done` 含同一 `turn_id`。
- `AuditLog.record(..., turn_id=...)`；旧库无列则 migration 增列或新建兼容写入。
- 桌面：dispatcher 识别字段即可；设置页或错误提示可展示「轮次 ID」方便内测反馈（可选，一行即可）。

- [ ] **Step 1:** 写测试：stream 首事件含 turn_id；audit 行带 turn_id。
- [ ] **Step 2–4:** TDD 实现。
- [ ] **Step 5:** Commit `feat: propagate chat turn_id through SSE and audit`

---

### Task 3: B — 桌面 Vitest 冒烟

**Files:**
- Modify: `apps/desktop/package.json`、必要时 `vitest.config.ts` / `tsconfig`
- NEW: `apps/desktop/src/lib/runtimeClient.test.ts`（及 token/路径小测）
- 覆盖：SSE 行解析、`runtimeLogHint`、（Task 4 后）Authorization header 组装

**行为:**
- `npm test` 跑通；不引入 Playwright。
- CI 不做强制（仓库仍无 GitHub Actions 亦可）；文档一句「发版前建议 npm test」。

- [ ] **Step 1–3:** 配置 Vitest + 2～4 个有意义用例 + `npm test` / `npm run build`。
- [ ] **Step 4:** Commit `test: add desktop vitest smoke for client helpers`

---

### Task 4: C — 本机 API token（Runtime + Tauri + 前端）

**Files:**
- NEW: `runtime/src/office_agent/auth.py`（或 middleware 进 `app.py`）
- Modify: `app.py`、`__main__.py`（读 env）
- Modify: `apps/desktop/src-tauri/src/lib.rs`（生成 token、env、`invoke` 暴露）
- Modify: `runtimeClient.ts`、`App.tsx`（启动时取 token）
- Modify: `scripts/dev.sh`（可选：不设 token，保持开发便利）
- NEW/Modify tests: `test_auth.py`、`test_app_api.py`

**行为:**
- Env：`OFFICE_AGENT_API_TOKEN`。未设置 → 中间件放行（dev/pytest）。已设置 → 除 `/health` 外需 `Authorization: Bearer …`（或约定 header `X-Office-Agent-Token`，**选定 Bearer**）。
- Tauri：进程内 `Uuid`/`OsRng` 生成 token；spawn sidecar/venv 时注入；前端 `invoke("get_runtime_token")`（或启动时一次性）写入 client。
- 错误：401 JSON `{ "detail": "..." }`；桌面健康检查仍走 `/health`。
- CORS 保持现白名单；token 不替代 CORS。

- [ ] **Step 1:** 测试：有 token 时无头 401；有头 200；无 env 时不强制。
- [ ] **Step 2–4:** Runtime 中间件 + Tauri 注入 + frontend header。
- [ ] **Step 5:** Commit `feat: require localhost API token when configured`

---

### Task 5: C — Skill 本地许可证（轻量）— **本轮跳过**

- [x] **跳过（2026-07-25）：** 不做 `license_required` / 本地 license 文件 / 机器码。仅保留 Task 4 本机 API token 作为 C 的交付。

---

### Task 6: 回归与规格回写

- [x] Full `pytest` + `npm test` + `npm run build`
- [x] 跑 `scripts/check_licenses.sh`（及 npm 扫描）+ 确认 `NOTICE` 存在
- [x] 更新审计规格 §5.4 / A8：标注 A/B 完成、C=仅 API token（Skill 授权跳过）；写作 RAG 与 jail / 机器码仍分期
- [x] Commit `docs: record Q+2 A/B/C-token completion`

---

## Self-Review

| 项 | Task |
|----|------|
| A 许可证 + NOTICE | 1 |
| B turn_id / audit | 2 |
| B Vitest 冒烟 | 3 |
| C API token | 4 |
| C Skill 本地 license | **5 跳过** |
| 回归 | 6 |
| 写作 RAG / 完整 jail / 机器码 / mac 公证 | **不做** |

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-07-25-wenshutong-q2-delivery.md`.
