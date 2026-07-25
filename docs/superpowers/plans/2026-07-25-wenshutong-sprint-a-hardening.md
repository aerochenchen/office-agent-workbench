# 文书通 Sprint A · 内测排雷 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 堵住内测前必须处理的安全与 UX 缺口：生产审计落库、Zip Slip 防护、配置密钥脱敏、Runtime 离线门禁与会话错误反馈，并修正文档品牌漂移。

**Architecture:** Runtime 在 `ProcessState` 持有 `AuditLog`，`_prepare_chat` 注入 `ToolExecutor`；Zip 解压经成员路径校验后写入目标目录；`GET /config` 只回掩码与是否已设置；桌面壳在 `health !== "ok"` 时阻断开工作区/发消息，并用跨平台日志路径文案。

**Tech Stack:** Python 3.11+ · FastAPI · pytest · React · TypeScript · Tauri 2

**Spec:** `docs/superpowers/specs/2026-07-25-wenshutong-audit-roadmap-design.md` §5.1

## Global Constraints

- 严格内网：仅白名单 DeepSeek API Host；Skill/模型禁止运行时连公网下载。
- 标准底座 `runtime/requirements.txt` **不得**包含 `torch` / `sentence-transformers` / `transformers`。
- 无通用 `shell` Tool；不在本 Sprint 做完整脚本 jail（属 Sprint B / C1）。
- 文件系统沙箱 = 当前工作区根（Tool 路径 API）；本 Sprint 不扩展进程级隔离。
- 平台：Windows 10+ 为交付重点；macOS 仅笔记本内测，**不做公证**。
- 品牌对外名：**文书通**（勿再写「办公智能体工作台」作为产品名）。
- 仅在用户明确要求时 commit；message 用英文 conventional commits。
- 每个 Task 结束时跑相关 pytest / `npm run build`（桌面改动），确认绿再进入下一 Task。

---

## File Structure (touched)

```
runtime/src/office_agent/
  app.py                 # AuditLog 注入；GET /config 脱敏
  skills.py              # safe zip extract
  audit.py               # 已有；本 Sprint 仅接线（可选加 recent() 仅测试用）
  tools.py               # 已有 _audit；无需改逻辑（除非补测试）
apps/desktop/src/
  App.tsx                # 离线门禁；会话错误
  lib/runtimeClient.ts   # 跨平台日志文案；Config 类型适配
  lib/types.ts           # api_key_set / api_key_masked
  components/SettingsModal.tsx  # 留空不覆盖已保存 key
apps/desktop/README.md
packaging/README-standard.md
runtime/tests/
  test_app_api.py
  test_skills.py
  test_tools.py          # 可选：确认 audit 行写入
```

---

### Task 1: 生产路径接线 AuditLog

**Files:**
- Modify: `runtime/src/office_agent/app.py`（`ProcessState`、`_prepare_chat`）
- Modify: `runtime/tests/test_app_api.py`
- Test: `runtime/tests/test_app_api.py::test_chat_writes_audit_rows`

**Interfaces:**
- Consumes: `AuditLog(db_path: Path)` with `.record(tool, args, ok, detail)`
- Produces: `ProcessState.audit: AuditLog`；默认路径 `app_data_dir() / "db" / "audit.sqlite"`
- Produces: `_prepare_chat` 创建的 `ToolExecutor(..., audit=office.audit)`

- [ ] **Step 1: Write the failing test**

在 `runtime/tests/test_app_api.py` 追加（依赖现有 `client` / `app_state` / mock gateway 夹具；若 chat 不调用工具则改用会触发 `workspace_list` 的 mock，或直接对 `app_state` 上的 executor 路径断言——推荐：mock gateway 返回带 `workspace_list` 的 tool_call，与现有 agent 测试一致）。

若现有 `/chat` mock 不跑工具，改用更直接的方式——在 `_prepare_chat` 后检查注入。最小可测方案：

```python
def test_prepare_chat_injects_audit(client: TestClient, tmp_path: Path, app_state: ProcessState):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})
    # 直接调用内部 prepare，或通过 chat 触发一次工具
    from office_agent.tools import ToolExecutor
    tools = ToolExecutor(
        app_state.workspace,
        app_state.registry,
        permission_mode=app_state.config.permission_mode,
        audit=app_state.audit,
    )
    assert app_state.audit is not None
    tools.execute("workspace_list", {"path": "."})
    import sqlite3
    with sqlite3.connect(app_state.audit.db_path) as conn:
        rows = conn.execute("SELECT tool, ok FROM audit").fetchall()
    assert ("workspace_list", 1) in rows
```

并在同文件增加：

```python
def test_chat_uses_state_audit(client: TestClient, tmp_path: Path, app_state: ProcessState, monkeypatch):
    """Regression: _prepare_chat must pass office.audit into ToolExecutor."""
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})
    seen: dict = {}

    real_te = __import__("office_agent.tools", fromlist=["ToolExecutor"]).ToolExecutor

    class Spy(ToolExecutor):
        def __init__(self, *a, **kw):
            seen["audit"] = kw.get("audit")
            super().__init__(*a, **kw)

    monkeypatch.setattr("office_agent.app.ToolExecutor", Spy)
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert seen.get("audit") is app_state.audit
```

（若 `ToolExecutor` 在 `app` 模块是 `from office_agent.tools import ToolExecutor`，patch 目标为 `office_agent.app.ToolExecutor`。）

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd runtime && .venv/bin/python -m pytest tests/test_app_api.py::test_chat_uses_state_audit tests/test_app_api.py::test_prepare_chat_injects_audit -v
```

Expected: FAIL（`ProcessState` 无 `audit` 属性，或 `seen["audit"]` 为 `None`）

- [ ] **Step 3: Minimal implementation**

在 `app.py`：

```python
from office_agent.audit import AuditLog

def _default_audit() -> AuditLog:
    return AuditLog(app_data_dir() / "db" / "audit.sqlite")

@dataclass
class ProcessState:
    config: AppConfig = field(default_factory=load_config)
    registry: SkillRegistry = field(default_factory=SkillRegistry)
    sessions: SessionStore = field(default_factory=SessionStore)
    audit: AuditLog = field(default_factory=_default_audit)
    workspace: Workspace | None = None
    gateway_factory: Callable[[AppConfig], Any] = ModelGateway
    zh_locale_tried: set[str] = field(default_factory=set)
```

`_prepare_chat` 内：

```python
        tools = ToolExecutor(
            ws,
            office.registry,
            permission_mode=office.config.permission_mode,
            audit=office.audit,
        )
```

`conftest` / `test_app_api` 里若手工构造 `ProcessState(...)`，确保不传 `audit` 时走 default_factory，或显式 `AuditLog(tmp_path / "db" / "a.sqlite")`（测试隔离）。

检查 `test_app_api` 夹具：若 `OFFICE_AGENT_DATA` 已指向 tmp，则 default audit 也落在 tmp 下——OK。

- [ ] **Step 4: Run tests to verify pass**

```bash
cd runtime && .venv/bin/python -m pytest tests/test_app_api.py tests/test_tools.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**（仅当用户要求时）

```bash
git add runtime/src/office_agent/app.py runtime/tests/test_app_api.py
git commit -m "$(cat <<'EOF'
feat: wire AuditLog into production chat tool path

EOF
)"
```

---

### Task 2: Zip 安全解压（防 Zip Slip）

**Files:**
- Modify: `runtime/src/office_agent/skills.py`
- Modify: `runtime/tests/test_skills.py`
- Test: `test_install_zip_rejects_path_escape`、`test_inspect_zip_rejects_path_escape`

**Interfaces:**
- Produces: `_safe_extractall(zf: zipfile.ZipFile, dest: Path) -> None`  
  - 对每个 `ZipInfo.filename`：拒绝绝对路径、含 `..` 的成员、解压后 `resolve()` 不在 `dest.resolve()` 下的路径  
  - 违例抛 `SkillError("unsafe zip entry: ...")`  
- `_inspect_zip` / `install_zip` 均改用 `_safe_extractall`，禁止裸 `extractall`

- [ ] **Step 1: Write the failing tests**

```python
def test_install_zip_rejects_path_escape(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../escape/SKILL.md", "---\nname: evil\ndescription: x\ntier: light\n---\n\n#\n")
        zf.writestr("evil/SKILL.md", "---\nname: evil\ndescription: x\ntier: light\n---\n\n#\n")
    with pytest.raises(SkillError, match="unsafe zip"):
        SkillRegistry().install_zip(z)
    assert not (tmp_path / "escape").exists()


def test_inspect_zip_rejects_path_escape(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    z = tmp_path / "evil2.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("/tmp/evil-skill/SKILL.md", "---\nname: evil\ndescription: x\ntier: light\n---\n\n#\n")
    with pytest.raises(SkillError, match="unsafe zip"):
        SkillRegistry().inspect_path(z)
```

保留现有 `test_install_zip_heavy_tier` 必须继续通过。

- [ ] **Step 2: Run tests to verify fail**

```bash
cd runtime && .venv/bin/python -m pytest tests/test_skills.py::test_install_zip_rejects_path_escape tests/test_skills.py::test_inspect_zip_rejects_path_escape -v
```

Expected: FAIL（当前 `extractall` 不抛或未匹配）

- [ ] **Step 3: Implement `_safe_extractall`**

在 `skills.py`（靠近 zip 相关函数）加入：

```python
def _safe_extractall(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    for info in zf.infolist():
        name = info.filename
        if not name or name.endswith("/"):
            # allow directory entries after validation
            target_check = name.rstrip("/")
        else:
            target_check = name
        # Normalize separators; reject absolute / drive / parent refs
        parts = Path(target_check).parts
        if Path(target_check).is_absolute() or any(p in ("..", "") for p in parts if p == ".."):
            raise SkillError(f"unsafe zip entry: {name}")
        if any(p == ".." for p in Path(name).parts):
            raise SkillError(f"unsafe zip entry: {name}")
        target = (dest / name).resolve()
        try:
            target.relative_to(dest)
        except ValueError as e:
            raise SkillError(f"unsafe zip entry: {name}") from e
    zf.extractall(dest)
```

注意：Windows 上 `Path("/tmp/...")` 可能被当成相对；对以 `/` 或 `\\` 开头、或含 `:` 的成员名也要拒绝：

```python
        raw = name.replace("\\", "/")
        if raw.startswith("/") or raw.startswith("../") or "/../" in f"/{raw}/" or (len(raw) > 1 and raw[1] == ":"):
            raise SkillError(f"unsafe zip entry: {name}")
```

将 `_inspect_zip` / `install_zip` 中的 `zf.extractall(extract)` 换成 `_safe_extractall(zf, extract)`。

- [ ] **Step 4: Run skill tests**

```bash
cd runtime && .venv/bin/python -m pytest tests/test_skills.py tests/test_app_api.py::test_install_zip_via_api -q
```

Expected: PASS

- [ ] **Step 5: Commit**（仅当用户要求时）

```bash
git add runtime/src/office_agent/skills.py runtime/tests/test_skills.py
git commit -m "$(cat <<'EOF'
fix: reject Zip Slip paths when installing skills

EOF
)"
```

---

### Task 3: GET /config 脱敏 + 设置页留空不覆盖

**Files:**
- Modify: `runtime/src/office_agent/app.py`（`get_config`）
- Modify: `runtime/tests/test_app_api.py`
- Modify: `apps/desktop/src/lib/types.ts`
- Modify: `apps/desktop/src/App.tsx`（加载 config）
- Modify: `apps/desktop/src/components/SettingsModal.tsx`
- Modify: `apps/desktop/src/lib/runtimeClient.ts`（若 `RuntimeConfig` 类型收紧）

**Interfaces:**
- `GET /config` 响应：
  - **不得**包含明文 `api_key` 字段（或恒为 `""` 且测试断言无真实 key——推荐直接省略 `api_key`）
  - 保留 `api_key_masked: str`
  - 新增 `api_key_set: bool`
- `POST /config`：`api_key` 为 `null`/缺省 → 不修改；非空字符串 → 更新；空字符串 `""` → 清空密钥（显式清除）
- UI：输入框 placeholder 展示 masked；保存时若输入为空且 `api_key_set`，则 **不传** `api_key`

- [ ] **Step 1: Write failing API tests**

```python
def test_get_config_does_not_return_plaintext_key(client: TestClient, app_state: ProcessState):
    app_state.config.api_key = "sk-secret-value-123456"
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert "sk-secret-value-123456" not in json.dumps(body)
    assert body.get("api_key") in (None, "")  # 推荐实现为字段不存在或空
    assert body["api_key_set"] is True
    assert body["api_key_masked"]
    assert "sk-secret" not in body["api_key_masked"] or "…" in body["api_key_masked"]


def test_post_config_omitted_key_keeps_previous(client: TestClient, app_state: ProcessState):
    app_state.config.api_key = "keep-me"
    r = client.post("/config", json={"model": "m2"})
    assert r.status_code == 200
    assert app_state.config.api_key == "keep-me"
```

- [ ] **Step 2: Run to verify fail**

```bash
cd runtime && .venv/bin/python -m pytest tests/test_app_api.py::test_get_config_does_not_return_plaintext_key -v
```

Expected: FAIL（当前返回明文）

- [ ] **Step 3: Implement GET 脱敏**

```python
    @app.get("/config")
    def get_config() -> dict[str, Any]:
        cfg = office.config
        key = cfg.api_key or ""
        masked = (key[:6] + "…" + key[-4:]) if len(key) > 12 else ("***" if key else "")
        return {
            "api_base": cfg.api_base,
            "api_key_masked": masked,
            "api_key_set": bool(key),
            "model": cfg.model,
            "allowed_hosts": cfg.allowed_hosts,
            "permission_mode": cfg.permission_mode,
            "max_tool_steps": cfg.max_tool_steps,
        }
```

`POST` 已有 `if body.api_key is not None`——保持：前端省略字段即不改；若要清空则传 `""`。

- [ ] **Step 4: Update desktop types + Settings**

`types.ts`：

```typescript
export type RuntimeConfig = {
  api_base: string;
  api_key: string; // 仅本地表单草稿；GET 后应为空
  api_key_masked?: string;
  api_key_set?: boolean;
  model: string;
  allowed_hosts: string[];
};
```

`App.tsx` 加载：

```typescript
        setConfig({
          api_base: cfg.api_base,
          api_key: "",
          api_key_masked: cfg.api_key_masked,
          api_key_set: cfg.api_key_set,
          model: cfg.model,
          allowed_hosts: cfg.allowed_hosts,
        });
```

（同步扩展 `runtimeClient.getConfig` 返回类型。）

`SettingsModal.tsx` `handleSave`：

```typescript
      const partial: Partial<RuntimeConfig> = {
        api_base: apiBase.trim(),
        model: model.trim(),
        allowed_hosts: allowedHosts
          .split(",")
          .map((h) => h.trim())
          .filter(Boolean),
      };
      const trimmedKey = apiKey.trim();
      if (trimmedKey) {
        partial.api_key = trimmedKey;
      } else if (!initial.api_key_set) {
        partial.api_key = "";
      }
      // api_key_set && 空输入 → 不传 api_key，保留服务端原值
      await onSave(partial);
```

placeholder：`initial.api_key_set ? \`已保存 ${initial.api_key_masked || "***"}；留空不修改\` : "粘贴 API Key"`

确认 `App` 的 `onSave` → `runtimeClient.saveConfig` 使用 JSON，省略字段不会被序列化为 `null`（`JSON.stringify` 默认忽略 `undefined`；勿显式传 `api_key: undefined` 以外的 null，除非后端把 null 当省略——当前 Pydantic `None` 不更新，OK）。

- [ ] **Step 5: Verify**

```bash
cd runtime && .venv/bin/python -m pytest tests/test_app_api.py -q
cd apps/desktop && npm run build
```

Expected: 测试 PASS；`tsc && vite build` 成功

- [ ] **Step 6: Commit**（仅当用户要求时）

```bash
git add runtime/src/office_agent/app.py runtime/tests/test_app_api.py \
  apps/desktop/src/lib/types.ts apps/desktop/src/lib/runtimeClient.ts \
  apps/desktop/src/App.tsx apps/desktop/src/components/SettingsModal.tsx
git commit -m "$(cat <<'EOF'
fix: stop returning plaintext API keys from GET /config

EOF
)"
```

---

### Task 4: 桌面离线门禁 + 跨平台日志路径 + 会话错误

**Files:**
- Modify: `apps/desktop/src/lib/runtimeClient.ts`
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/components/SessionList.tsx`（若需禁用按钮 props）
- Modify: `apps/desktop/src/components/ChatPanel.tsx`（禁用发送 / placeholder）

**Interfaces:**
- Produces: `runtimeOfflineHint(): string` —— macOS/Linux 用 `$TMPDIR` 或「系统临时目录下的 `office-agent-desktop.log`」；Windows 保留 `%TEMP%\\office-agent-desktop.log`
- Produces: `health !== "ok"` 时：不可打开工作区、不可发送、会话新建/删除按钮禁用或早退并提示

- [ ] **Step 1: Fix log path helper in `runtimeClient.ts`**

替换写死 Windows 文案的两处（约 L65、L82）为共享函数：

```typescript
export function runtimeLogHint(): string {
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  const isWin = /Windows/i.test(ua);
  if (isWin) {
    return "%TEMP%\\office-agent-desktop.log";
  }
  return "系统临时目录中的 office-agent-desktop.log（macOS 多为 $TMPDIR）";
}

// 在 mapError / 连接失败分支：
`无法连接本地运行时（127.0.0.1:8765）。请关闭后重新打开本应用；若仍失败，查看 ${runtimeLogHint()}`
```

- [ ] **Step 2: Gate actions in `App.tsx`**

```typescript
  const runtimeReady = health === "ok";

  const handleOpenPath = useCallback(
    async (path: string) => {
      if (!runtimeReady) {
        setWorkspaceError("本地运行时未就绪，请稍候或重启应用");
        return;
      }
      // ... existing
    },
    [runtimeReady, loadSessionMessages, refreshSessions],
  );

  const handleNewSession = useCallback(async () => {
    if (!workspacePath || sending || !runtimeReady) return;
    try {
      const created = await runtimeClient.createSession(workspacePath);
      setSessionId(created.session.id);
      setMessages([]);
      await refreshSessions(workspacePath);
    } catch (err) {
      setMessages([
        {
          id: nextId(),
          role: "error",
          content: err instanceof RuntimeClientError ? err.message : "新建会话失败",
        },
      ]);
    }
  }, [workspacePath, sending, runtimeReady, refreshSessions]);

  const handleDeleteSession = useCallback(
    async (id: string) => {
      if (sending || !runtimeReady) return;
      try {
        await runtimeClient.deleteSession(id);
        const list = await refreshSessions(workspacePath);
        // ... existing branch logic
      } catch (err) {
        setMessages([
          {
            id: nextId(),
            role: "error",
            content: err instanceof RuntimeClientError ? err.message : "删除会话失败",
          },
        ]);
      }
    },
    [sending, runtimeReady, workspacePath, refreshSessions, loadSessionMessages],
  );

  const handleSend = useCallback(
    async (text: string) => {
      if (!workspacePath || !runtimeReady) return;
      // ... existing
    },
    [workspacePath, runtimeReady, /* ... */],
  );
```

向 `SessionList` / `ChatPanel` 传入 `runtimeReady`（或 `disabled={!runtimeReady}`）：

- 打开文件夹按钮 disabled  
- 发送按钮 disabled；placeholder 在 `!runtimeReady` 时为「本地运行时未就绪…」  
- 顶栏已有红点；可选在中栏增加一行简短 banner（不要大改布局）

- [ ] **Step 3: Build check**

```bash
cd apps/desktop && npm run build
```

Expected: PASS

- [ ] **Step 4: Manual smoke（开发者）**

1. `./scripts/dev.sh --web` 启动后停掉 Runtime，确认 UI 显示未就绪且无法发送。  
2. 恢复 Runtime，确认可打开文件夹。  
3. 在 macOS 上看连接失败文案是否不再出现 `%TEMP%`。

- [ ] **Step 5: Commit**（仅当用户要求时）

```bash
git add apps/desktop/src/lib/runtimeClient.ts apps/desktop/src/App.tsx \
  apps/desktop/src/components/SessionList.tsx apps/desktop/src/components/ChatPanel.tsx
git commit -m "$(cat <<'EOF'
fix: block UI actions when runtime is down and fix log path copy

EOF
)"
```

---

### Task 5: 文档与品牌对齐

**Files:**
- Modify: `apps/desktop/README.md`
- Modify: `packaging/README-standard.md`
- Modify: `apps/desktop/src-tauri/resources/README.md`（若仍只提 Windows，补一句 mac 脚本存在且不公证）
- Optional: `packaging/VERIFY-macos.md` 开头注明「内测用，不做公证」

**要求：**
- 产品名统一为 **文书通**；安装器文件名若代码已是文书通则文档同步；勿把「办公智能体工作台」当作现行产品名（可在历史说明中一句带过）。
- README 左栏描述改为「会话列表 + 工作区选择」，删除或标注 `WorkspaceTree` 为未挂载/历史组件。
- 删除「浏览器模式高级：粘贴路径导入 Skill」等与代码不符的句子；改为实际能力（浏览器可粘贴工作区路径；Skill 导入仅 Tauri）。

- [ ] **Step 1: Edit docs**（按上表逐文件改）

- [ ] **Step 2: Grep 残留**

```bash
rg -n "办公智能体工作台|WorkspaceTree|粘贴路径" apps/desktop/README.md packaging/README-standard.md packaging/VERIFY-macos.md || true
```

Expected: 无不当现行描述（历史路径除外）

- [ ] **Step 3: Commit**（仅当用户要求时）

```bash
git add apps/desktop/README.md packaging/README-standard.md \
  apps/desktop/src-tauri/resources/README.md packaging/VERIFY-macos.md
git commit -m "$(cat <<'EOF'
docs: align packaging copy with 文书通 and current UI

EOF
)"
```

---

### Task 6: Sprint A 回归与规格回写

**Files:**
- Modify: `docs/superpowers/specs/2026-07-25-wenshutong-audit-roadmap-design.md`（§3 中 C2/P0-1/P0-2/P0-3/P0-4/P0-5/P1-4 状态可注「Sprint A 已修」——仅在实现合并后）

- [ ] **Step 1: Full runtime tests**

```bash
cd runtime && .venv/bin/python -m pytest -q
```

Expected: 全部 PASS（不少于实现前的 77，且新增用例通过）

- [ ] **Step 2: Desktop build**

```bash
cd apps/desktop && npm run build
```

Expected: PASS

- [ ] **Step 3: Update audit spec checklist**（实现完成后）

在规格 §5.1 下增加：

```markdown
### Sprint A 完成记录

| 项 | 状态 |
|----|------|
| C2 AuditLog 接线 | 已完成 YYYY-MM-DD |
| P0-1 Zip Slip | 已完成 |
| P0-2 配置脱敏 | 已完成 |
| P0-3/4/5 UX | 已完成 |
| P1-4 文档 | 已完成 |
```

- [ ] **Step 4: Offer user commit / start Sprint B planning**

---

## Self-Review（对照规格 §5.1）

| 规格工作项 | Task |
|------------|------|
| 生产接线 AuditLog (C2) | Task 1 |
| Zip 安全解压 (P0-1) | Task 2 |
| GET /config 不回明文 (P0-2) | Task 3 |
| 离线阻断 + 日志路径 + 会话 CRUD 错误 (P0-3/4/5) | Task 4 |
| README/打包文档对齐 (P1-4) | Task 5 |
| 完成标准验证 | Task 6 |

Placeholder scan: 无 TBD；类型名与现有 `ProcessState` / `SkillError` / `RuntimeConfig` 一致。  
未纳入（属 Sprint B）：C1 脚本 jail、C3 permission_mode、取消生成、Skill 卸载、Seed 覆盖、CSP/CORS。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-25-wenshutong-sprint-a-hardening.md`.
