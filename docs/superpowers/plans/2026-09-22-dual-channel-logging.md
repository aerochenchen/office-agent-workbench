# 双通道日志（诊断 + 安全审计）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地规格 B：诊断 JSONL 可还原一次失败对话；审计事件表可证明配置/权限/技能/会话等安全决策。

**Architecture:** Runtime 用 `diagnostic.emit` 写 `logs/runtime-YYYY-MM-DD.jsonl`；桌面壳写 `logs/desktop-YYYY-MM-DD.jsonl` 并下发 `OFFICE_AGENT_BOOT_ID`。`AuditLog.record` 保持工具调用兼容，新增 `record_event` 写同一 `audit.sqlite`（补列、不新建库）。写审计失败只记诊断 `audit_write_failed`，不中断对话。

**Tech Stack:** Python 3.11+ · FastAPI · pytest · TypeScript · React · Tauri 2 / Rust

**Spec:** `docs/superpowers/specs/2026-09-22-dual-channel-logging-design.md`

## Global Constraints

- 默认不上报到开发者；不做 syslog、hash 链强制非空、会话全文进审计（P2 / Out）。
- 脱敏：`content` 只记长度；`api_key`/`token`/`password` 遮罩；`api_base` 只记 host；工作区绝对路径审计用 sha256。
- 品牌：文书通。诊断/审计文件在 `app_data_dir()`（`OFFICE_AGENT_DATA` 或 `~/.office-agent`）。
- 本计划覆盖规格 P0+P1；P2 不实施。
- 执行时每个 Task 先写失败测试。Commit 仅在用户明确要求时做（计划步骤保留 message，代理人勿擅自 push）。
- 每个 Task 结束跑对应 pytest；改 UI 时再 `cd apps/desktop && npx vitest run`（若有相关测）与类型检查。

---

## File Structure (touched)

```
runtime/src/office_agent/
  diagnostic.py          # NEW: JSONL emit、按日滚动、保留 30 天、20MB 切分
  audit.py               # record_event、补列、instance_id、workspace_hash
  paths.py               # instance_id() 可放这里或 audit.py
  gateway.py             # GatewayError.error_code / host_class；chat() 翻译 SDK 错误
  tools.py               # session_id、error_code、script_denied、TURN_ID env
  permissions.py         # on_decision 回调 → permission_decision
  auth.py                # 401 时 api_auth_fail
  app.py                 # chat 起止、config/skill/session/workspace、export/recent
  script_policy.py       # 可选：逃逸时稳定码（也可在 tools 捕获 ToolError）
  __main__.py            # configure_diagnostic_logging()；runtime_start
apps/desktop/src-tauri/src/lib.rs
                         # JSONL log_event、boot_id、sidecar env
apps/desktop/src/
  lib/runtimeClient.ts   # listAudit / exportAudit；runtimeLogHint → logs/
  lib/types.ts           # AuditRow
  lib/tauri.ts           # invoke desktop_log（health_fail）
  App.tsx                # health → down 时 desktop_log
  components/SettingsModal.tsx  # 「使用审计」页
runtime/tests/
  test_diagnostic.py     # NEW
  test_audit.py          # NEW 或扩 test_app_api 里已有 audit 测
  test_app_api.py / test_tools.py / test_permissions.py / test_auth.py / test_gateway.py
apps/desktop/src/lib/runtimeClient.test.ts
docs/文书通-数据类型清单-中国合规.md   # D07 扩展 + 诊断 JSONL 新行
```

---

### Task 1: 诊断 JSONL 模块

**Files:**
- Create: `runtime/src/office_agent/diagnostic.py`
- Create: `runtime/tests/test_diagnostic.py`

**Interfaces:**
- Produces:

```python
def emit(
    event: str,
    *,
    level: str = "info",
    turn_id: str | None = None,
    session_id: str | None = None,
    **fields: object,
) -> None: ...

def configure(log_dir: Path | None = None) -> Path:
    """Create log dir, prune >30 days, return directory used."""

def current_log_path(kind: str = "runtime") -> Path:
    """logs/{kind}-YYYY-MM-DD.jsonl (UTC date)."""
```

- [ ] **Step 1: Write the failing tests**

```python
# runtime/tests/test_diagnostic.py
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from office_agent.diagnostic import configure, current_log_path, emit


def test_emit_writes_json_line(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    configure()
    emit("chat_started", level="info", turn_id="t1", session_id="s1", route="/chat/stream")
    path = current_log_path("runtime")
    row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert row["event"] == "chat_started"
    assert row["level"] == "info"
    assert row["turn_id"] == "t1"
    assert row["session_id"] == "s1"
    assert row["route"] == "/chat/stream"
    assert "T" in row["ts"]
    assert "api_key" not in row


def test_emit_omits_forbidden_fields(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    configure()
    emit("x", api_key="sk-secret", messages=[{"role": "user", "content": "全文"}])
    row = json.loads(current_log_path().read_text(encoding="utf-8").splitlines()[0])
    assert "sk-secret" not in json.dumps(row)
    assert "messages" not in row
    assert "api_key" not in row


def test_configure_prunes_old_files(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    logs = tmp_path / "logs"
    logs.mkdir()
    old = logs / "runtime-2000-01-01.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    configure()
    assert not old.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd runtime && .venv/bin/python -m pytest tests/test_diagnostic.py -q`

Expected: FAIL `ModuleNotFoundError: office_agent.diagnostic`

- [ ] **Step 3: Implement `diagnostic.py`**

```python
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from office_agent.paths import app_data_dir

_FORBIDDEN = frozenset({"api_key", "key", "token", "password", "passwd", "messages", "content"})
_KEEP_DAYS = 30
_MAX_BYTES = 20 * 1024 * 1024
_LEVELS = frozenset({"error", "warn", "info", "debug"})


def _min_level() -> str:
    raw = (os.environ.get("OFFICE_AGENT_LOG_LEVEL") or "info").strip().lower()
    return raw if raw in _LEVELS else "info"


def _enabled(level: str) -> bool:
    order = ("debug", "info", "warn", "error")
    try:
        return order.index(level) >= order.index(_min_level())
    except ValueError:
        return True


def configure(log_dir: Path | None = None) -> Path:
    root = Path(log_dir) if log_dir is not None else (app_data_dir() / "logs")
    root.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=_KEEP_DAYS)
    for path in root.glob("runtime-*.jsonl"):
        _prune_if_old(path, cutoff)
    for path in root.glob("desktop-*.jsonl"):
        _prune_if_old(path, cutoff)
    return root


def _prune_if_old(path: Path, cutoff) -> None:
    # filename runtime-YYYY-MM-DD.jsonl or runtime-YYYY-MM-DD.N.jsonl
    stem = path.name
    parts = stem.replace(".jsonl", "").split("-")
    if len(parts) < 4:
        return
    try:
        day = datetime(int(parts[1]), int(parts[2]), int(parts[3][:2]), tzinfo=timezone.utc).date()
    except ValueError:
        return
    if day < cutoff:
        path.unlink(missing_ok=True)


def current_log_path(kind: str = "runtime") -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    root = app_data_dir() / "logs"
    root.mkdir(parents=True, exist_ok=True)
    base = root / f"{kind}-{day}.jsonl"
    if base.is_file() and base.stat().st_size >= _MAX_BYTES:
        n = 1
        while True:
            cand = root / f"{kind}-{day}.{n}.jsonl"
            if not cand.is_file() or cand.stat().st_size < _MAX_BYTES:
                return cand
            n += 1
    return base


def emit(event: str, *, level: str = "info", turn_id: str | None = None, session_id: str | None = None, **fields: Any) -> None:
    lvl = level if level in _LEVELS else "info"
    if not _enabled(lvl):
        return
    row: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "level": lvl,
        "event": event,
        "turn_id": turn_id or "-",
    }
    if session_id:
        row["session_id"] = session_id
    boot = os.environ.get("OFFICE_AGENT_BOOT_ID", "").strip()
    if boot:
        row["boot_id"] = boot
    for key, value in fields.items():
        if key in _FORBIDDEN or key in row:
            continue
        if value is None:
            continue
        row[key] = value
    line = json.dumps(row, ensure_ascii=False) + "\n"
    path = current_log_path("runtime")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
```

`emit` 自身失败应静默（`try/except OSError`），避免日志拖垮对话。

- [ ] **Step 4: Run tests**

Run: `cd runtime && .venv/bin/python -m pytest tests/test_diagnostic.py -q`

Expected: PASS

- [ ] **Step 5: Commit** (only if user asked)

```bash
git add runtime/src/office_agent/diagnostic.py runtime/tests/test_diagnostic.py
git commit -m "$(cat <<'EOF'
feat: 增加 Runtime 诊断 JSONL（按日滚动、字段脱敏）

EOF
)"
```

---

### Task 2: 审计表补列 + `record_event`

**Files:**
- Modify: `runtime/src/office_agent/audit.py`
- Modify: `runtime/src/office_agent/paths.py`（增加 `instance_id()`）
- Modify: `runtime/tests/test_app_api.py`（已有 `test_audit_log_migrates_old_db_without_turn_id`、`test_audit_log_redacts_sensitive_args`）
- Create: `runtime/tests/test_audit.py`

**Interfaces:**
- Consumes: Task 1 `diagnostic.emit`（INSERT 失败时）
- Produces:

```python
def workspace_hash(path: Path | str) -> str: ...
def instance_id(app_data: Path | None = None) -> str: ...

class AuditLog:
    def record(self, tool: str, args: dict, ok: bool, detail: str = "", *, turn_id: str | None = None, session_id: str | None = None, error_code: str | None = None) -> None: ...
    def record_event(self, event_type: str, *, outcome: str = "ok", turn_id: str | None = None, session_id: str | None = None, tool: str | None = None, args: dict | None = None, detail: str = "", error_code: str | None = None, attrs: dict | None = None) -> None: ...
    def list_recent(self, limit: int = 20) -> list[dict]: ...
    def export_rows(self, since: float | None = None) -> list[dict]: ...
```

- [ ] **Step 1: Write failing tests**

```python
# runtime/tests/test_audit.py
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

from office_agent.audit import AuditLog, workspace_hash


def test_record_event_adds_columns(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    log = AuditLog(tmp_path / "a.sqlite")
    log.record_event(
        "config_changed",
        outcome="ok",
        session_id="s1",
        attrs={"keys": ["allow_workspace_scripts"], "allow_workspace_scripts": {"old": False, "new": True}},
    )
    with sqlite3.connect(tmp_path / "a.sqlite") as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(audit)")}
        assert "event_type" in cols
        assert "prev_hash" in cols
        row = conn.execute(
            "SELECT event_type, outcome, session_id, actor, instance_id, attrs_json FROM audit"
        ).fetchone()
    assert row[0] == "config_changed"
    assert row[1] == "ok"
    assert row[2] == "s1"
    assert row[3]  # actor non-empty
    assert row[4]  # instance_id
    assert "allow_workspace_scripts" in row[5]


def test_legacy_record_maps_to_tool_invoked(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    log = AuditLog(tmp_path / "a.sqlite")
    log.record("workspace_list", {"path": "."}, True, turn_id="t1", session_id="s1")
    with sqlite3.connect(tmp_path / "a.sqlite") as conn:
        event, ok, sid = conn.execute(
            "SELECT event_type, ok, session_id FROM audit"
        ).fetchone()
    assert event == "tool_invoked"
    assert ok == 1
    assert sid == "s1"


def test_workspace_hash_stable_and_not_raw_path(tmp_path: Path):
    p = tmp_path / "机密文件夹"
    p.mkdir()
    h = workspace_hash(p)
    assert len(h) == 64
    assert "机密" not in h


def test_record_event_failure_does_not_raise(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    log = AuditLog(tmp_path / "a.sqlite")
    log.db_path.write_text("not-a-db", encoding="utf-8")
    log.record_event("chat_started", outcome="ok")  # must not raise
```

Also extend `test_audit_log_migrates_old_db_without_turn_id` to assert `event_type` column appears after `AuditLog(db_path)`.

- [ ] **Step 2: Run to verify FAIL**

Run: `cd runtime && .venv/bin/python -m pytest tests/test_audit.py -q`

Expected: FAIL import or `record_event` missing

- [ ] **Step 3: Implement**

`paths.py` 增加：

```python
def instance_id_path() -> Path:
    return app_data_dir() / "instance_id"


def instance_id() -> str:
    path = instance_id_path()
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    import uuid
    value = str(uuid.uuid4())
    write_private_text(path, value + "\n")
    return value
```

`audit.py`：

- `_NEW_COLS = [("event_type", "TEXT"), ("session_id", "TEXT"), ("actor", "TEXT"), ("instance_id", "TEXT"), ("outcome", "TEXT"), ("error_code", "TEXT"), ("attrs_json", "TEXT"), ("prev_hash", "TEXT")]`
- `_init_db` 对缺失列 `ALTER TABLE`
- `workspace_hash(path)` = `hashlib.sha256(str(Path(path).expanduser().resolve()).encode("utf-8")).hexdigest()`
- `_actor()` = `getpass.getuser()`，失败则 `"unknown"`
- `_redact_attrs` 删 `_SENSITIVE_ARG_FIELDS` 键；若 attrs 含 `api_base` 则改为 host（`from office_agent.deployment import model_host_from_api_base`）
- `record(...)` 调 `record_event("tool_invoked", outcome="ok" if ok else "error", tool=tool, args=args, ...)`
- `record_event`：`INSERT` 全列；`ok = 1 if outcome == "ok" else 0`；`tool` 默认 `"-"`；`detail` 截断 500；`try/except sqlite3.Error` 里 `from office_agent.diagnostic import emit` 然后 `emit("audit_write_failed", level="error", error_code="sqlite")`，不再抛出
- `list_recent` / `export_rows`：`SELECT *` 按 `ts DESC`；把行打成 dict（`event_type` 空则 `"tool_invoked"`）

- [ ] **Step 4: Run tests**

Run: `cd runtime && .venv/bin/python -m pytest tests/test_audit.py tests/test_app_api.py::test_audit_log_redacts_sensitive_args tests/test_app_api.py::test_audit_log_migrates_old_db_without_turn_id -q`

Expected: PASS

- [ ] **Step 5: Commit** (if authorized) `feat: 审计表升级为通用事件并兼容旧 tool 记录`

---

### Task 3: Runtime 启动 + 对话起止 + Gateway 错误码

**Files:**
- Modify: `runtime/src/office_agent/gateway.py`
- Modify: `runtime/src/office_agent/__main__.py`
- Modify: `runtime/src/office_agent/app.py`（`_prepare_chat` / `chat` / `chat_stream` / lifespan 或 `create_app` 开头 `configure()`）
- Create: `runtime/tests/test_gateway.py`（若尚无）
- Modify: `runtime/tests/test_app_api.py`

**Interfaces:**
- Consumes: `diagnostic.configure` / `emit`；`AuditLog.record_event`
- Produces:

```python
class GatewayError(ValueError):
    def __init__(self, message: str, *, error_code: str = "gateway_error", host_class: str = "") -> None: ...
    error_code: str
    host_class: str

class ModelGateway:
    def chat(...) -> Any:  # wrap OpenAI errors → GatewayError
```

- [ ] **Step 1: Failing tests**

```python
def test_local_profile_public_host_sets_error_code():
    from office_agent.config import AppConfig
    from office_agent.gateway import GatewayError, ModelGateway
    cfg = AppConfig(
        api_base="https://api.deepseek.com",
        api_key="k",
        model="m",
        allowed_hosts=["api.deepseek.com"],
        deployment_profile="local",
    )
    try:
        ModelGateway(cfg)
        assert False, "expected GatewayError"
    except GatewayError as e:
        assert e.error_code == "model_host_rejected"
        assert e.host_class == "denied"


def test_chat_stream_writes_chat_started(client, tmp_path, app_state, monkeypatch):
    from office_agent.diagnostic import current_log_path, configure
    configure()
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})
    with client.stream("POST", "/chat/stream", json={"message": "你好"}) as r:
        "".join(r.iter_text())
    text = current_log_path().read_text(encoding="utf-8")
    assert "chat_started" in text
    assert "chat_finished" in text
```

GatewayError 现有构造是 `GatewayError("...")`。测试会因没有 `error_code` 失败。

`create_app` 开头调用 `diagnostic.configure()`，`__main__.py` 在 `uvicorn.run` 前同样调用，并 `emit("runtime_start", boot_id=os.environ.get("OFFICE_AGENT_BOOT_ID"))`。

`host_class`：loopback（127.0.0.1/localhost）、intranet（`is_intranet_model_host`）、denied（本地部署拒公网）。

`ModelGateway.chat`：

```python
def chat(self, messages, tools=None):
    try:
        ...
        return self._client.chat.completions.create(**kwargs)
    except GatewayError:
        raise
    except Exception as e:
        code = "timeout" if "timeout" in type(e).__name__.lower() else "gateway_error"
        raise GatewayError(str(e), error_code=code, host_class=self._host_class()) from e
```

`app.py`：

- `_prepare_chat` 捕获 `GatewayError`：已是 HTTP 400；补 `record_event("model_host_rejected" if error_code=="model_host_rejected" else "gateway_error")` 与 `emit("gateway_error", level="error", ...)`
- `chat` / `chat_stream` worker 开始：`emit("chat_started", ...)` + `record_event("chat_started", attrs={"route": "/chat" or "/chat/stream", "workspace_hash": ...})`
- 结束：`emit("chat_finished", duration_ms=..., status=..., steps=len(tool_events))`
- `append_messages` 的 `except`：`emit("session_persist_failed", level="error", session_id=...)`

`workspace_hash`：无工作区时省略 attrs 中的 hash。

- [ ] **Step 2–4:** 红 → 实现 → `pytest tests/test_gateway.py tests/test_app_api.py::test_chat_stream_writes_chat_started tests/test_app_api.py::test_chat_stream_emits_started_and_final -q`

- [ ] **Step 5: Commit** `feat: 对话与模型网关写入诊断日志和审计起点`

---

### Task 4: 工具调用补 session_id / 稳定错误码 / 脚本拒绝

**Files:**
- Modify: `runtime/src/office_agent/tools.py`
- Modify: `runtime/src/office_agent/app.py`（`ToolExecutor(..., session_id=session_id)`）
- Modify: `runtime/src/office_agent/script_policy.py`（可选：错误消息前缀 `sandbox_escape:`）
- Modify: `runtime/tests/test_tools.py`、`runtime/tests/test_script_policy.py`、`runtime/tests/test_script_jail.py`

**Interfaces:**
- Consumes: `AuditLog.record(..., session_id=, error_code=)`
- Produces: `ToolExecutor(session_id: str | None = None)`；jail/关闭脚本时 `error_code` 为 `script_denied` / `workspace_scripts_disabled` / `sandbox_escape_blocked`

- [ ] **Step 1: Failing tests**

在 `test_tools.py` 增加：`allow_workspace_scripts=False` 时 `run_workspace_script` 的审计行 `error_code` 含 `workspace_scripts_disabled` 或 detail 含 `disabled`，且 `event_type=tool_invoked`、`session_id` 有值。

对 argv 逃逸：`test_run_workspace_script_rejects_outside_argv` 之后查审计或返回 `error` 以 `path outside` 开头；`tools.py` 在捕获 `ToolError` 且 message 含 escape/outside 时 `record_event("sandbox_escape_blocked", outcome="deny", error_code="sandbox_escape_blocked")`。

`_run_python` 在 `build_script_env()` 后：`if self.turn_id: env["OFFICE_AGENT_TURN_ID"] = self.turn_id`。`script_policy` 敏感剥离不会删这个名字（不含 TOKEN/KEY）。加测：`OFFICE_AGENT_TURN_ID` 保留。

超时：若 `_run_python` 已有 timeout 返回，设 `error_code=script_timeout` 并 `emit("script_timeout")`。

- [ ] **Step 3: Implement `_audit`**

```python
def _audit(self, tool: str, args: dict, ok: bool, detail: str, error_code: str | None = None) -> None:
    if self.audit is None:
        return
    code = error_code
    if not ok and code is None:
        err = detail.lower()
        if "disabled" in err:
            code = "workspace_scripts_disabled"
        elif "outside" in err or "escape" in err or "jail" in err:
            code = "sandbox_escape_blocked"
        elif "permission denied" in err:
            code = "permission_denied"
        elif "timeout" in err:
            code = "script_timeout"
    try:
        self.audit.record(
            tool, args, ok, detail, turn_id=self.turn_id,
            session_id=self.session_id, error_code=code,
        )
    except Exception:
        from office_agent.diagnostic import emit
        emit("audit_write_failed", level="error", turn_id=self.turn_id)
    if not ok and code in {"workspace_scripts_disabled", "sandbox_escape_blocked", "script_timeout", "script_denied"}:
        from office_agent.diagnostic import emit
        ev = "script_timeout" if code == "script_timeout" else "script_denied"
        emit(ev, level="warn", turn_id=self.turn_id, error_code=code, tool=tool)
        if code == "sandbox_escape_blocked":
            self.audit.record_event(
                "sandbox_escape_blocked", outcome="deny",
                turn_id=self.turn_id, session_id=self.session_id,
                error_code=code, tool=tool,
            )
```

`execute` 里 `PermissionDenied("workspace scripts are disabled")` 继续走现有 except。

- [ ] **Step 4:** `pytest tests/test_tools.py tests/test_script_policy.py tests/test_script_jail.py tests/test_permissions.py -q`

- [ ] **Step 5: Commit** `feat: 工具审计补 session 与脚本拒绝稳定码`

---

### Task 5: 桌面壳 JSONL + boot_id + health_fail

**Files:**
- Modify: `apps/desktop/src-tauri/src/lib.rs`
- Modify: `apps/desktop/src/lib/tauri.ts`
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/lib/runtimeClient.ts`（P0 **仍**提示临时目录，规格允许双写；P1 Task 11 再改 hint）
- Test: 无现成 Rust 单测则加一段注释化验收；TypeScript 可测 `desktopLogPayload` 抽到 `apps/desktop/src/lib/desktopLog.ts`

**Interfaces:**
- Produces: env `OFFICE_AGENT_BOOT_ID`；`logs/desktop-YYYY-MM-DD.jsonl`；Tauri command `desktop_log { event, level?, fields? }`

- [ ] **Step 1: Failing test (TS helper)**

```typescript
// apps/desktop/src/lib/desktopLog.test.ts
import { describe, expect, it } from "vitest";
import { desktopLogLine } from "./desktopLog";

describe("desktopLogLine", () => {
  it("emits boot fields without token", () => {
    const line = desktopLogLine({
      event: "boot",
      bootId: "b1",
      extra: { token: "secret", version: "1.6.0" },
    });
    const row = JSON.parse(line);
    expect(row.event).toBe("boot");
    expect(row.boot_id).toBe("b1");
    expect(row.version).toBe("1.6.0");
    expect(JSON.stringify(row)).not.toContain("secret");
  });
});
```

Rust 侧也可手写同等 JSON，不必依赖 TS。更干净：Rust 自己组 JSON；TS `desktopLogLine` 仅给前端 `health_fail` 经 invoke 传到 Rust 再写盘。

推荐只在 Rust 写盘，TS 测 invoke 形状即可。若抽 TS helper 麻烦，本 Task 以 `desktopLog.ts` 生成 payload、Rust append 为准。

- [ ] **Step 3: Rust `log_event`**

在 `lib.rs`：

- `app_data_dir()`: `std::env::var("OFFICE_AGENT_DATA")` 或 `home/.office-agent`
- 启动生成 `boot_id = Uuid::new_v4()` 存 `Mutex<String>`
- `fn log_event(event: &str, level: &str, boot_id: &str, extra: &str /* already json object or empty */)`
  - 写入 `app_data/logs/desktop-YYYY-MM-DD.jsonl`（UTC）
  - **同时** `writeln` 旧 `temp_dir/office-agent-desktop.log`（纯文本一行，兼容现有 hint）
- `setup` 最早 `log_event("boot", "info", ...)`
- `try_spawn_sidecar` / `try_spawn_venv`：`cmd.env("OFFICE_AGENT_BOOT_ID", boot_id)`；成功 `sidecar_spawn`，失败仍 `sidecar_spawn` 但 extra `ok:false`
- `stop_owned_runtime`：`sidecar_exit` + `returncode`（`child.wait` 已有则记录）
- `#[tauri::command] fn desktop_log(event: String, level: Option<String>)` 供 `health_fail`

`App.tsx` 在 `setHealth("down")` 前：

```typescript
import { logDesktopEvent } from "./lib/tauri";
void logDesktopEvent("health_fail");
```

`tauri.ts`：`invoke("desktop_log", { event })`，非 Tauri 时 no-op。

- [ ] **Step 4:** `cd apps/desktop && npx vitest run src/lib/desktopLog.test.ts`（若有）；`cargo check` 在 `apps/desktop/src-tauri` 若环境允许

- [ ] **Step 5: Commit** `feat: 桌面壳结构化日志并下发 boot_id`

---

### Task 6: `config_changed` + `model_host_rejected`

**Files:**
- Modify: `runtime/src/office_agent/app.py` `update_config`
- Modify: `runtime/tests/test_app_api.py`

- [ ] **Step 1: Failing tests**

```python
def test_config_change_allow_workspace_scripts_is_audited(client, app_state):
    r = client.post("/config", json={"allow_workspace_scripts": True})
    assert r.status_code == 200
    import sqlite3, json as _json
    with sqlite3.connect(app_state.audit.db_path) as conn:
        rows = conn.execute(
            "SELECT event_type, attrs_json FROM audit WHERE event_type = 'config_changed'"
        ).fetchall()
    assert rows
    attrs = _json.loads(rows[-1][1])
    assert attrs["allow_workspace_scripts"]["old"] is False
    assert attrs["allow_workspace_scripts"]["new"] is True


def test_local_deploy_rejects_public_model_and_audits(client, app_state, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DEPLOYMENT", "local")
    app_state.config.deployment_profile = "local"
    r = client.post("/config", json={"api_base": "https://api.deepseek.com"})
    assert r.status_code == 400
    import sqlite3
    with sqlite3.connect(app_state.audit.db_path) as conn:
        n = conn.execute(
            "SELECT count(*) FROM audit WHERE event_type = 'model_host_rejected'"
        ).fetchone()[0]
    assert n >= 1
```

注意：`resolved_profile()` 可能读 env；测试需与 `test_deployment.py` 一致。拒绝发生在 `save_config` **之前**。attrs 只含 host，不含 key。

`permission_mode` 变更同样写入 `config_changed` 的 `keys` 列表。

- [ ] **Step 3:** 在赋值前快照 old，拒绝公网时 `record_event("model_host_rejected", outcome="deny", error_code="model_host_rejected", attrs={"host": host, "profile": "local"})`。成功保存时一条 `config_changed`，`keys` 为实际改动键。

- [ ] **Step 4:** `pytest tests/test_app_api.py -q -k "config_change or local_deploy_rejects"` 以及现有 config 测试全绿

- [ ] **Step 5: Commit** `feat: 审计配置变更与本地部署拒公网模型`

---

### Task 7: `permission_decision`（允许也记）

**Files:**
- Modify: `runtime/src/office_agent/permissions.py`
- Modify: `runtime/src/office_agent/app.py`（gate 回调里带 audit）
- Modify: `runtime/tests/test_permissions.py`
- Modify: `runtime/tests/test_app_api.py`（stream 权限路径若已有测试则扩）

**Interfaces:**

```python
class PermissionGate:
    on_decision: Callable[[str, str, str], None] | None
    # (tool, decision, mode) decision in allow|deny|timeout
```

在 `check` 里：timeout 分支、deny 分支、allow 成功后各调 `on_decision`。`app.py` chat_stream 设置：

```python
def on_decision(tool: str, decision: str, mode: str) -> None:
    office.audit.record_event(
        "permission_decision",
        outcome="ok" if decision == "allow" else "deny",
        session_id=session_id,
        turn_id=turn_id,
        tool=tool,
        error_code="permission_timeout" if decision == "timeout" else None,
        attrs={"decision": decision, "mode": mode},
    )
    if decision == "timeout":
        from office_agent.diagnostic import emit
        emit("permission_timeout", level="warn", session_id=session_id, turn_id=turn_id, tool=tool)
gate.on_decision = on_decision
```

trust 模式跳过弹窗：不记 `permission_decision`（无人工决策）。`NeedsInteractivePermission`（非交互 `/chat`）记 `chat_started` 的 route=`/chat` 已够；可选 `outcome=deny` 的 `permission_decision` 且 `decision=needs_interactive`——规格未列此码，**不要发明**；409 已有。

- [ ] **Step 1:** 单测 `PermissionGate`：`set_auto(None)` 难测 wait；改为测 `resolve` 后 `on_decision` 被调用。现有测试用 `set_auto(True/False)`。增加：自定义 `on_decision` 列表，对 `set_auto(False)` 期望无 wait（Raises NeedsInteractive）。对 interactive：构造 gate、线程 `check`、主线程 `resolve(id, True)`，断言 callback `allow`。

超时：把 `wait_timeout=0.05`，无 resolve，断言 `decision=timeout`。

- [ ] **Step 4:** `pytest tests/test_permissions.py -q`

- [ ] **Step 5: Commit** `feat: 权限允许/拒绝/超时写入审计`

---

### Task 8: 技能 / 会话 / 工作区 / API 鉴权失败

**Files:**
- Modify: `runtime/src/office_agent/app.py`
- Modify: `runtime/src/office_agent/auth.py`
- Modify: `runtime/src/office_agent/skills.py`（install 返回 path 以便 sha256，或 app 层对 `body.path` 哈希）
- Modify: `runtime/tests/test_app_api.py`、`runtime/tests/test_auth.py`

- [ ] **Step 1: Tests**

```python
def test_delete_session_audits_before_row_gone(client, tmp_path):
    ws = tmp_path / "ws"; ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})
    sid = client.post("/sessions", json={}).json()["session"]["id"]
    client.delete(f"/sessions/{sid}")
    import sqlite3
    with sqlite3.connect(...) as conn:
        ev = conn.execute("SELECT event_type FROM audit WHERE event_type='session_deleted'").fetchone()
    assert ev
    assert client.get(f"/sessions/{sid}").status_code == 404


def test_workspace_open_stores_hash_not_path(client, tmp_path):
    ws = tmp_path / "ws"; ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})
    # attrs_json 不含 str(ws)


def test_skill_install_audits(client, tmp_path):
    # 最小 zip 或 dir；复用现有 install 测试素材
    ...


def test_auth_fail_writes_audit(app_state, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_API_TOKEN", "secret-token")
    client = TestClient(create_app(app_state))
    client.get("/config")  # 401
    with sqlite3.connect(app_state.audit.db_path) as conn:
        n = conn.execute("SELECT count(*) FROM audit WHERE event_type='api_auth_fail'").fetchone()[0]
    assert n >= 1
```

`auth.py` 中间件在 401 前：`office = getattr(request.app.state, "office", None)`；`office.audit.record_event("api_auth_fail", outcome="deny", attrs={"route": request.url.path, "reason": "missing" if not auth else "mismatch"})`。无 office 时跳过。

`delete_session`：**先** `record_event` **再** `sessions.delete_session`。

`install_skill` 成功后 `sha256` 用 `hashlib.sha256(src.read_bytes()).hexdigest()`（大文件可只读前 1MB+size，规格写文件 sha256——zip 通常不大；>50MB 则记 `sha256="omitted"` 与 `size`）。

`set_skill_enabled` / `uninstall_skill` 同样 `record_event`。

- [ ] **Step 4:** `pytest tests/test_auth.py tests/test_app_api.py -q`

- [ ] **Step 5: Commit** `feat: 审计技能安装、删会话、打开文件夹与 API 鉴权失败`

---

### Task 9: 审计导出与最近列表 API

**Files:**
- Modify: `runtime/src/office_agent/app.py`
- Modify: `runtime/tests/test_app_api.py`
- Modify: `runtime/tests/test_auth.py`（export 无 token → 401）

**Interfaces:**

```
GET /audit/recent?limit=20  → {"entries": [ {ts, event_type, outcome, tool, error_code, session_id, attrs, detail} ]}
GET /audit/export?since=     → text/plain 或 application/x-ndjson；每行 JSON
```

不要把 `args_json` 里已脱敏字段再展开成公文。`limit` 上限 100。

- [ ] **Step 1:**

```python
def test_audit_export_ndjson_and_redacted(client, app_state):
    app_state.audit.record("workspace_write", {"path": "a.docx", "content": "密"}, True)
    r = client.get("/audit/export")
    assert r.status_code == 200
    assert "密" not in r.text
    line = r.text.strip().splitlines()[-1]
    row = json.loads(line)
    assert "event_type" in row


def test_audit_recent_limit(client, app_state):
    for i in range(3):
        app_state.audit.record_event("chat_started", outcome="ok", session_id=str(i))
    r = client.get("/audit/recent", params={"limit": 2})
    assert r.status_code == 200
    assert len(r.json()["entries"]) == 2
```

- [ ] **Step 3:** 用 `StreamingResponse` 或直接 `"\n".join(...)` 返回。`since` 过滤 `ts >= since`。

- [ ] **Step 4:** pytest 上述 + `test_token_env_requires_bearer` 仍 401 `/audit/export`

- [ ] **Step 5: Commit** `feat: 提供本机审计导出与最近记录接口`

---

### Task 10: 交付物魔数核对

**Files:**
- Modify: `runtime/src/office_agent/tools.py` `_finish`
- Modify: `runtime/src/office_agent/app.py` 或 `agent_loop.py`（`chat_finished.status`）
- Modify: `runtime/tests/test_tools.py`

规格：缺文件仍失败 finish（已有）。后缀为 docx/xlsx/pptx 但魔数不是 ZIP（`PK`）时 **不拦截回复**，诊断 `deliverable_verified` `kind=other`，`chat_finished.status=unverified_deliverable`。

- [ ] **Step 1:**

```python
def test_finish_non_zip_docx_still_ok_but_unverified(tmp_path, monkeypatch):
    ...
    (ws / "工作成果").mkdir()
    (ws / "工作成果" / "a.docx").write_text("not-zip", encoding="utf-8")
    result = ex.execute("finish", {"summary": "x", "deliverables": ["工作成果/a.docx"]})
    assert result["ok"] is True
    assert result.get("unverified") is True
```

现有 `_finish` 对存在的非空文件返回 ok。增加：读前 4 字节；office 后缀且非 `PK\x03\x04` / `PK\x05\x06` / `PK\x07\x08` 则 `unverified=True`。`emit("deliverable_claimed")` + `emit("deliverable_verified", exists=True, kind="other"|"docx"|...)`。

`chat_finished`：若本轮 tool_events 里 finish 带 unverified，status 用 `unverified_deliverable`，否则 `ok` / `error`。

- [ ] **Step 4:** `pytest tests/test_tools.py -q -k finish`

- [ ] **Step 5: Commit** `feat: finish 核对 Office 交付物魔数并记诊断`

---

### Task 11: 设置页「使用审计」+ 日志路径提示 + 合规清单

**Files:**
- Modify: `apps/desktop/src/lib/types.ts`
- Modify: `apps/desktop/src/lib/runtimeClient.ts` + `runtimeClient.test.ts`
- Modify: `apps/desktop/src/components/SettingsModal.tsx`
- Modify: `apps/desktop/src/App.css` 或现有 settings 样式类（能复用则不新增花哨样式）
- Modify: `docs/文书通-数据类型清单-中国合规.md`
- Modify: `docs/superpowers/specs/2026-09-22-dual-channel-logging-design.md` 状态 → 已实施（本 Task 收尾时）

**Interfaces:**

```typescript
export interface AuditEntry {
  ts: number;
  event_type: string;
  outcome: string;
  tool?: string;
  error_code?: string;
  session_id?: string;
  detail?: string;
}

listAuditRecent(limit = 20): Promise<{ entries: AuditEntry[] }>
exportAudit(since?: number): Promise<Blob>
```

`runtimeLogHint()` 改为：「本机日志目录：用户目录/.office-agent/logs（诊断 JSONL）；使用记录在设置「使用审计」导出。」Windows 可用 `%USERPROFILE%\.office-agent\logs`。更新 `runtimeClient.test.ts`。

设置新 tab `audit` 标签「使用审计」：

- 表格：时间（本地）、event_type、outcome、摘要（tool 或 error_code）
- 按钮「导出 JSONL」→ `URL.createObjectURL` 下载 `文书通-审计.jsonl`
- 文案：不提供清空；删除应用数据会丢掉记录。无「删除」按钮。

打开 tab 时 fetch `/audit/recent`。

- [ ] **Step 1:** 扩 `runtimeLogHint` 测试；可加 `formatAuditSummary` 纯函数测。

- [ ] **Step 4:** `cd apps/desktop && npx vitest run src/lib/runtimeClient.test.ts`

数据类型清单：D07 改为安全事件审计（event_type 等）；新增 D12 诊断 JSONL（本机、不上报、故障定位）。

- [ ] **Step 5: Commit** `feat: 设置页导出使用审计并更新合规数据清单`

---

## Spec coverage

| 规格节 | Task |
|---|---|
| §5 诊断 JSONL 滚动/字段/禁止项 | 1 |
| §5.3 boot/sidecar/health/runtime_start | 5, 3 |
| §5.3 chat_*/gateway_error/session_persist/audit_write_failed/permission_timeout | 3, 7 |
| §5.3 script_denied/timeout | 4 |
| §6.1 表迁移、record 包装、instance_id、prev_hash 可空 | 2 |
| §6.2 tool_invoked 补全 | 4 |
| §6.2 chat_started route | 3 |
| §6.2 permission_decision | 7 |
| §6.2 config_changed / model_host_rejected | 6 |
| §6.2 skill_* / session_deleted / workspace_opened / api_auth_fail | 8 |
| §6.2 script_denied / sandbox_escape_blocked | 4 |
| §6.2 deliverable_* | 10 |
| §6.3 导出 UI 无清空 | 9, 11 |
| §7 boot_id / turn_id / TURN_ID env | 5, 3, 4 |
| §8 脱敏、清单回写 | 1, 2, 11 |
| §8 P2 hash/syslog | **不做** |
| §10 P0 验收（断模型/杀 sidecar） | 3+5 手工补一轮：改坏 api_base 看 logs；杀进程看 desktop jsonl |
| §10 P1 四条导出 | 6–9 测试覆盖 |

## Placeholder / 类型自检

- 无 TBD。`record_event` / `emit` / `GatewayError.error_code` 在后续 Task 与 Task 1–2 一致。
- `on_decision(tool, decision, mode)` 三字符串，decision 仅 `allow|deny|timeout`。
- 旧 `AuditLog.record(tool, args, ok, ...)` 全部现有测试无需改调用，除非要传 `session_id`。
