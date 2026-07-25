# 文书通 Sprint B · 安全基线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地权限模式与确认流、脚本环境/路径约束、取消生成、Skill 卸载、Seed 不盲覆盖、CORS/CSP 收紧，使设计 §10.3 的 A3（权限）与脚本边界声明可验收。

**Architecture:** `ToolExecutor` 在谨慎模式下通过可注入的 `PermissionGate` 阻塞写/跑脚本；SSE 发出 `permission_request`，UI 确认后 `POST /chat/permissions/{id}`。`CancelToken` 挂在会话级运行上，在 `run_agent` 每步检查。脚本子进程强制离线环境变量并对 path-like argv 做工作区边界校验。Seed 对已存在 Skill 默认不覆盖。CORS/CSP 收紧到本地壳来源。

**Tech Stack:** Python 3.11+ · FastAPI · pytest · React · TypeScript · Tauri 2

**Spec:** `docs/superpowers/specs/2026-07-25-wenshutong-audit-roadmap-design.md` §5.2；权限语义对照 `2026-07-23-office-agent-runtime-design.md` §7.2–7.3

## Global Constraints

- 严格内网；标准底座不得引入 torch / sentence-transformers / transformers。
- **不做**完整进程/容器级 jail（属后续分期）；本 Sprint 的 C1 = 环境断网软约束 + path-like argv 硬校验 + 文档化边界。
- **不做** macOS 公证。
- 权限三档：`cautious` | `standard`（默认）| `trust_workspace`。本 Sprint：`trust_workspace` 行为 = 本会话内自动允许写/跑脚本（仍禁路径越界）；`standard` = 同会话同脚本名记住后免确认，首次写/跑需确认；`cautious` = 每次写/跑确认。
- 品牌：**文书通**。
- 仅在用户要求或执行本计划时 commit；英文 conventional commits。
- 每个 Task 结束跑相关 pytest / 桌面 `npm run build`（若改 UI）。

---

## File Structure (touched)

```
runtime/src/office_agent/
  permissions.py          # NEW: PermissionGate, request ids, session remember
  cancel.py               # NEW: CancelToken
  script_policy.py        # NEW: env + argv path checks for _run_python
  tools.py                # gate + policy + skill permission checks
  agent_loop.py           # cancel between steps
  app.py                  # confirm/cancel/uninstall APIs; CORS; wire gates
  bundled_seed.py         # default overwrite=False for existing skills
  config.py               # (unchanged fields; ensure modes documented)
apps/desktop/src/
  App.tsx / ChatPanel.tsx / SettingsModal.tsx
  lib/runtimeClient.ts / types.ts
  components/PermissionModal.tsx   # NEW (or inline in ChatPanel)
apps/desktop/src-tauri/tauri.conf.json   # CSP
runtime/tests/
  test_permissions.py     # NEW
  test_script_policy.py   # NEW
  test_cancel.py          # NEW
  test_bundled_seed.py / test_skills.py / test_app_api.py / test_tools.py
```

---

### Task 1: PermissionGate + ToolExecutor 强制

**Files:**
- Create: `runtime/src/office_agent/permissions.py`
- Modify: `runtime/src/office_agent/tools.py`
- Create: `runtime/tests/test_permissions.py`
- Modify: `runtime/tests/test_tools.py`（默认 gate 自动放行，保持旧测绿）

**Interfaces:**
- Produces:

```python
# permissions.py
class PermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"

@dataclass
class PermissionRequest:
    id: str
    tool: str
    summary: str
    args: dict

class PermissionGate:
    def __init__(self, mode: str = "standard") -> None: ...
    def remember_key(self, tool: str, args: dict) -> str: ...
    def check(self, tool: str, args: dict) -> None:
        """Raise PermissionDenied or block until allow. No-op for read-only tools."""
    def resolve(self, request_id: str, allow: bool) -> None: ...
    # For tests / non-UI:
    def set_auto(self, allow: bool | None) -> None:  # None = interactive waiter
```

- Risky tools: `workspace_write`, `workspace_extract`（会改文件时）、`run_workspace_script`, `run_skill_script`, `run_shared_script`。`workspace_extract` 可能写规范化产物——按写类处理。
- Read-only: `workspace_list`, `workspace_read`, `read_skill`, `ask_user`, `finish` — 不确认。
- `PermissionDenied` → `ToolExecutor.execute` 返回 `{"ok": false, "error": "permission denied: ..."}`。
- Skill `permissions`：若 frontmatter 含列表，则 `run_skill_script` / `run_shared_script` 需要 `run_python`；`workspace_write` 需要 `workspace_write`。缺省空列表 = 兼容旧 Skill，不额外拦截（仅 mode gate）。

- [ ] **Step 1: Failing tests**

```python
# test_permissions.py
def test_cautious_blocks_write_until_resolved(tmp_path, monkeypatch):
    # gate mode cautious, auto=None; start check in thread; resolve allow; write succeeds
    ...

def test_standard_remembers_same_script(tmp_path):
    # first run_shared_script needs resolve; second same name auto-allows
    ...

def test_skill_missing_run_python_denied(tmp_path, monkeypatch):
    # skill with permissions: [workspace_read] only → run_skill_script denied
    ...
```

- [ ] **Step 2: RED** — `pytest tests/test_permissions.py -v`

- [ ] **Step 3: Implement `permissions.py` + wire `ToolExecutor`**

在 `execute` 开头对 risky tools 调用 `self.gate.check(...)`（若 `self.gate` 非 None）。构造时默认 `PermissionGate(mode)` 且 `set_auto(True)` 以保持无 UI 测试行为；生产由 app 注入 interactive gate。

- [ ] **Step 4: GREEN** — `pytest tests/test_permissions.py tests/test_tools.py -q`

- [ ] **Step 5: Commit**（执行本计划时）

```bash
git commit -m "$(cat <<'EOF'
feat: add PermissionGate for cautious/standard tool confirmation

EOF
)"
```

---

### Task 2: SSE 权限确认 API + 设置页 permission_mode

**Files:**
- Modify: `runtime/src/office_agent/app.py`（`ConfigBody` 含 `permission_mode`；`ProcessState.gates`；stream 注入 gate；`POST /chat/permissions/{request_id}`）
- Modify: `apps/desktop/src/lib/types.ts`、`runtimeClient.ts`、`SettingsModal.tsx`、`App.tsx`
- Create: `apps/desktop/src/components/PermissionModal.tsx`（或 ChatPanel 内嵌）
- Modify: `runtime/tests/test_app_api.py`

**Interfaces:**
- `GET/POST /config` 读写 `permission_mode`（已有 GET 字段；POST 补上）。
- SSE 新事件：`permission_request` → `{id, tool, summary, session_id}`。
- `POST /chat/permissions/{request_id}` body `{"allow": true|false}` → 调用 `gate.resolve`。
- Gate 在 `_prepare_chat` 创建：`PermissionGate(office.config.permission_mode)`，interactive：`set_auto(None)`；`check` 内 `on_request` 回调 → `emit("permission_request", ...)` 并 `Event.wait(timeout=300)`。
- UI：收到事件弹确认框；允许/拒绝调 API；Settings 增加三档下拉。

- [ ] **Step 1: API test** — stream + mock gateway 触发 `workspace_write`，并行线程 `POST .../permissions/{id}` allow，最终 final 成功。

- [ ] **Step 2: Implement backend wiring**

- [ ] **Step 3: Desktop Settings + PermissionModal + chatStream handler**

`chatStream` / XHR dispatcher 识别 `event: permission_request`。

- [ ] **Step 4:** `pytest tests/test_app_api.py -q` && `cd apps/desktop && npm run build`

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat: wire permission confirmation SSE and settings mode

EOF
)"
```

---

### Task 3: 脚本策略（C1 分期）

**Files:**
- Create: `runtime/src/office_agent/script_policy.py`
- Modify: `runtime/src/office_agent/tools.py` `_run_python`
- Create: `runtime/tests/test_script_policy.py`

**Interfaces:**

```python
def build_script_env(base: dict | None = None) -> dict[str, str]:
    """Force HF/TRANSFORMERS offline; clear HTTP(S)_PROXY; set NO_PROXY=*."""

def assert_argv_within_roots(argv: list[str], roots: list[Path]) -> None:
    """
    For each arg that looks like a filesystem path (exists or has path sep
    or suffix .py/.docx/...), resolve and require relative_to one of roots.
    Raise ToolError otherwise.
    """
```

- `_run_python` roots = `[workspace.root, skill_dir?, shared-scripts parent]` — 对 skill/shared 把脚本所在目录加入 allowed roots。
- **不做** OS 网络 namespace。

- [ ] **Step 1–4: TDD** 测拒绝 `/etc/passwd` 风格 argv；允许工作区内相对路径；env 含 `HF_HUB_OFFLINE=1`。

- [ ] **Step 5: Commit** `feat: constrain script env and path-like argv`

---

### Task 4: 取消生成（User stop）

**Files:**
- Create: `runtime/src/office_agent/cancel.py`
- Modify: `runtime/src/office_agent/agent_loop.py`、`app.py`
- Modify: `apps/desktop/src/App.tsx`、`ChatPanel.tsx`、`runtimeClient.ts`
- Create: `runtime/tests/test_cancel.py`

**Interfaces:**

```python
class CancelToken:
    def cancel(self) -> None: ...
    def check(self) -> None:  # raises CancelledError
```

- `ProcessState.active_cancel: dict[str, CancelToken]` keyed by `session_id`。
- `run_agent(..., cancel: CancelToken | None)`：每步循环开头 `cancel.check()`；工具执行前再 check。
- `POST /chat/cancel` body `{"session_id": "..."}` → token.cancel()；若无活跃运行返回 404 或 `{ok:false}`。
- 前端：发送中显示「停止」；点击 → `runtimeClient.cancelChat(sessionId)` + abort 当前 XHR/fetch（需把 AbortController/XHR 提升到可外部 abort 的 handle）。
- 取消后：SSE `error` 或 `final` with truncated summary；会话写入已产生的消息（尽力）。

- [ ] **Step 1: Test** — 启动 stream worker，立即 cancel，断言循环停止且不跑满 max_steps。

- [ ] **Step 2–4: Implement + UI Stop button**

- [ ] **Step 5: Commit** `feat: support cancelling in-flight chat turns`

---

### Task 5: Skill 卸载 + Seed 不盲覆盖

**Files:**
- Modify: `runtime/src/office_agent/skills.py` — `uninstall(skill_id) -> None`
- Modify: `runtime/src/office_agent/app.py` — `DELETE /skills/{skill_id}`
- Modify: `runtime/src/office_agent/bundled_seed.py` — skills: 仅当 `not target.exists()` 时 copy；`overwrite` 默认 **False**；shared-scripts 仍可用 `overwrite=True` 刷新产品脚本（或同样 False——**选定：skills 默认不覆盖；shared-scripts 仍覆盖**，因排版脚本属产品组件）
- Modify: `apps/desktop/src/components/SkillPanel.tsx` + `runtimeClient.ts` — 卸载按钮（确认对话框）
- Modify: `runtime/tests/test_skills.py`、`test_bundled_seed.py`

- [ ] **Step 1: Tests**

```python
def test_uninstall_removes_skill(tmp_path, monkeypatch): ...
def test_seed_does_not_clobber_user_skill(tmp_path, monkeypatch):
    # pre-create skill with marker file; seed; marker still present
    ...
```

- [ ] **Step 2–4: Implement + UI**

- [ ] **Step 5: Commit** `feat: uninstall skills and stop seed clobbering user copies`

---

### Task 6: CORS + CSP 收紧

**Files:**
- Modify: `runtime/src/office_agent/app.py` CORS
- Modify: `apps/desktop/src-tauri/tauri.conf.json` `app.security.csp`
- Modify: `runtime/tests/test_app_api.py`（若有 CORS 断言则更新；可选）

**CORS allow_origins（精确列表，禁止 `*`）：**
- `http://127.0.0.1:1420`
- `http://localhost:1420`
- `http://tauri.localhost`
- `https://tauri.localhost`
- `tauri://localhost`

`allow_credentials=True` 可保留；若某 origin 不需要可再收。

**CSP（Tauri）示例：**

```
default-src 'self'; connect-src 'self' http://127.0.0.1:8765 http://localhost:8765 ipc: http://ipc.localhost; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:
```

（按 Tauri 2 实际需要微调；`npm run tauri build` 不做强制，但 `npm run build` + 开发态 Vite 需仍能打 Runtime。）

- [ ] **Step 1: 改 CORS + 测 health 仍可从 TestClient 访问**（TestClient 不受 CORS 限制）

- [ ] **Step 2: 设 CSP；本地 `npm run build`**

- [ ] **Step 3: Commit** `fix: tighten CORS allowlist and Tauri CSP`

---

### Task 7: Sprint B 回归与规格回写

**Files:**
- Modify: `docs/superpowers/specs/2026-07-25-wenshutong-audit-roadmap-design.md` §5.2 完成记录；§3 中 C1/C3/P1-1/2/3/P1-5 状态

- [ ] **Step 1:** `cd runtime && .venv/bin/python -m pytest -q` — 全绿  
- [ ] **Step 2:** `cd apps/desktop && npm run build` — 通过  
- [ ] **Step 3:** 规格回写完成表  
- [ ] **Step 4:** Commit `docs: record Sprint B completion in audit roadmap`

---

## Self-Review（对照 §5.2）

| 规格项 | Task |
|--------|------|
| permission_mode + UI (C3) | Task 1–2 |
| 脚本约束分期 (C1) | Task 3 |
| 取消生成 (P1-1) | Task 4 |
| Skill 卸载 (P1-3) | Task 5 |
| Seed 不盲覆盖 (P1-2) | Task 5 |
| CSP / CORS (P1-5) | Task 6 |
| 回归 + 规格 | Task 7 |

**明确不在范围：** 容器/Seatbelt jail；同机 API token；附件 UI；macOS 公证。

---

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-07-25-wenshutong-sprint-b-security.md`.
