from __future__ import annotations

import json
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from office_agent.agent_loop import AgentResult
from office_agent.app import ProcessState, create_app
from office_agent.audit import AuditLog
from office_agent.config import AppConfig
from office_agent.session_store import SessionStore
from office_agent.skills import SkillRegistry


def _completion(*, content: str | None = None, tool_calls: list[Any] | None = None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_call(call_id: str, name: str, arguments: dict[str, Any]):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments, ensure_ascii=False)),
    )


@dataclass
class FakeGateway:
    responses: list[Any]

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
        if self.responses:
            return self.responses.pop(0)
        # Default: echo last user content so multi-turn API tests keep working
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = str(m.get("content") or "")
                break
        return _completion(content=f"收到：{last_user}")


@pytest.fixture
def app_state(tmp_path: Path, monkeypatch) -> ProcessState:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    cfg = AppConfig(
        api_base="http://127.0.0.1:8000/v1",
        api_key="test-key",
        model="deepseek-v4-flash",
        allowed_hosts=["127.0.0.1", "localhost"],
    )
    gateway = FakeGateway(responses=[_completion(content="你好，已就绪。")])
    state = ProcessState(
        config=cfg,
        registry=SkillRegistry(),
        sessions=SessionStore(),
        gateway_factory=lambda _cfg: gateway,
    )
    return state


@pytest.fixture
def client(app_state: ProcessState) -> TestClient:
    return TestClient(create_app(app_state))


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_shutdown_localhost_ok(client: TestClient, monkeypatch):
    import office_agent.app as app_mod

    monkeypatch.setattr(app_mod, "ALLOW_PROCESS_EXIT", False)
    r = client.post("/shutdown")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_open_workspace_and_tree(client: TestClient, tmp_path: Path):
    ws = tmp_path / "project"
    ws.mkdir()
    (ws / "doc.txt").write_text("hi", encoding="utf-8")

    r = client.post("/workspace/open", json={"path": str(ws)})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert (ws / ".office-agent" / "work").is_dir()
    assert (ws / "output").is_dir()

    tree = client.get("/workspace/tree")
    assert tree.status_code == 200
    names = {e["name"] for e in tree.json()["entries"]}
    assert "doc.txt" in names
    assert ".office-agent" in names
    assert "output" in names


def test_workspace_tree_requires_open(client: TestClient):
    r = client.get("/workspace/tree")
    assert r.status_code == 400


def test_list_skills_includes_tier_and_enabled(client: TestClient, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = tmp_path / "skills" / "demo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: d\ntier: heavy\nmin_ram_gb: 8\n---\n\n# x\n",
        encoding="utf-8",
    )
    r = client.get("/skills")
    assert r.status_code == 200
    items = r.json()["skills"]
    assert len(items) == 1
    assert items[0]["tier"] == "heavy"
    assert items[0]["min_ram_gb"] == 8
    assert items[0]["enabled"] is True


def test_install_skill_and_set_enabled(client: TestClient, tmp_path: Path):
    src = tmp_path / "pkg" / "my-skill"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: install test\nversion: 0.1.0\ntier: light\n"
        "permissions:\n  - run_python\n---\n\n# y\n",
        encoding="utf-8",
    )
    preview = client.post("/skills/inspect", json={"path": str(src)})
    assert preview.status_code == 200
    assert preview.json()["skill"]["permissions"] == ["run_python"]
    assert "validation" in preview.json()
    assert preview.json()["validation"]["ok"] is True

    r = client.post("/skills/install", json={"path": str(src), "enabled": True})
    assert r.status_code == 200
    assert r.json()["skill"]["id"] == "my-skill"
    assert r.json()["skill"]["permissions"] == ["run_python"]
    assert r.json()["validation"]["ok"] is True

    off = client.post("/skills/my-skill/enabled", json={"enabled": False})
    assert off.status_code == 200
    listed = client.get("/skills").json()["skills"]
    assert listed[0]["enabled"] is False


def test_install_zip_via_api(client: TestClient, tmp_path: Path):
    src = tmp_path / "pkg" / "zip-skill"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: zip-skill\ndescription: from zip\nversion: 0.1.0\ntier: light\n---\n\n# z\n",
        encoding="utf-8",
    )
    z = tmp_path / "s.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(src / "SKILL.md", arcname="zip-skill/SKILL.md")
    r = client.post("/skills/install", json={"path": str(z)})
    assert r.status_code == 200
    assert r.json()["skill"]["id"] == "zip-skill"


def test_install_rejects_invalid_package_with_validation(client: TestClient, tmp_path: Path):
    src = tmp_path / "pkg" / "no-version"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: no-version\ndescription: d\ntier: light\n---\n\n#\n",
        encoding="utf-8",
    )
    preview = client.post("/skills/inspect", json={"path": str(src)})
    assert preview.status_code == 200
    assert preview.json()["validation"]["ok"] is False
    assert any("version" in e for e in preview.json()["validation"]["errors"])

    r = client.post("/skills/install", json={"path": str(src)})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert any("version" in e for e in detail["errors"])
    assert detail["validation"]["ok"] is False


def test_post_config_updates_state(client: TestClient, app_state: ProcessState):
    r = client.post(
        "/config",
        json={
            "api_base": "http://10.0.0.8:8000/v1",
            "allowed_hosts": ["10.0.0.8"],
            "api_key": "k2",
            "model": "other-model",
        },
    )
    assert r.status_code == 200
    assert app_state.config.api_base == "http://10.0.0.8:8000/v1"
    assert app_state.config.allowed_hosts == ["10.0.0.8"]
    assert app_state.config.api_key == "k2"
    assert app_state.config.model == "other-model"


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


def test_chat_rejects_attached_path_outside_workspace(client: TestClient, tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})

    r = client.post(
        "/chat",
        json={"message": "处理文件", "attached_paths": ["../outside.txt"]},
    )
    assert r.status_code == 400
    assert "escapes workspace" in r.json()["detail"]


def test_chat_stream_rejects_attached_path_outside_workspace(client: TestClient, tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})

    r = client.post(
        "/chat/stream",
        json={"message": "处理文件", "attached_paths": ["/etc/passwd"]},
    )
    assert r.status_code == 400
    assert "escapes workspace" in r.json()["detail"]


def test_chat_attached_paths_in_session_history(
    client: TestClient, tmp_path: Path, app_state: ProcessState
):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "doc.txt").write_text("hi", encoding="utf-8")
    client.post("/workspace/open", json={"path": str(ws)})

    r = client.post(
        "/chat",
        json={"message": "处理", "attached_paths": ["doc.txt"]},
    )
    assert r.status_code == 200
    sid = r.json()["session_id"]
    user_contents = [
        m.get("content", "")
        for m in app_state.sessions.get_messages(sid)
        if m.get("role") == "user"
    ]
    assert any("doc.txt" in c for c in user_contents)
    assert any("用户附带的文件路径" in c for c in user_contents)


def test_chat_returns_reply_and_session(client: TestClient, tmp_path: Path, app_state: ProcessState):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})

    r = client.post("/chat", json={"message": "列出文件"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "你好，已就绪。"
    assert body["tool_events"] == []
    assert body["session_id"]
    msgs = app_state.sessions.get_messages(body["session_id"])
    assert any(m.get("role") == "user" for m in msgs)


def _parse_sse_events(text: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data: dict[str, Any] | None = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if data is not None:
            events.append((event_name, data))
    return events


def test_chat_stream_started_includes_turn_id(client: TestClient, tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})

    with client.stream("POST", "/chat/stream", json={"message": "你好"}) as r:
        assert r.status_code == 200
        text = "".join(r.iter_text())

    started = next((data for ev, data in _parse_sse_events(text) if ev == "started"), None)
    assert started is not None
    assert started.get("session_id")
    turn_id = started.get("turn_id")
    assert isinstance(turn_id, str)
    assert turn_id


def test_chat_stream_tool_events_include_turn_id(
    client: TestClient, tmp_path: Path, app_state: ProcessState
):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})

    app_state.gateway_factory = lambda _cfg: FakeGateway(
        responses=[
            _completion(
                tool_calls=[_tool_call("t1", "workspace_list", {"path": "."})],
            ),
            _completion(content="已列出"),
        ]
    )

    with client.stream("POST", "/chat/stream", json={"message": "列出文件"}) as r:
        assert r.status_code == 200
        text = "".join(r.iter_text())

    events = _parse_sse_events(text)
    started = next(data for ev, data in events if ev == "started")
    turn_id = started["turn_id"]
    tool_starts = [data for ev, data in events if ev == "tool_start"]
    tool_dones = [data for ev, data in events if ev == "tool_done"]
    assert tool_starts and tool_dones
    assert all(data.get("turn_id") == turn_id for data in tool_starts)
    assert all(data.get("turn_id") == turn_id for data in tool_dones)


def test_chat_stream_audit_records_turn_id(
    client: TestClient, tmp_path: Path, app_state: ProcessState
):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})

    app_state.gateway_factory = lambda _cfg: FakeGateway(
        responses=[
            _completion(
                tool_calls=[_tool_call("t1", "workspace_list", {"path": "."})],
            ),
            _completion(content="已列出"),
        ]
    )

    with client.stream("POST", "/chat/stream", json={"message": "列出文件"}) as r:
        assert r.status_code == 200
        text = "".join(r.iter_text())

    started = next(data for ev, data in _parse_sse_events(text) if ev == "started")
    turn_id = started["turn_id"]
    import sqlite3

    with sqlite3.connect(app_state.audit.db_path) as conn:
        rows = conn.execute(
            "SELECT tool, turn_id FROM audit WHERE tool = ?",
            ("workspace_list",),
        ).fetchall()
    assert rows
    assert all(row[1] == turn_id for row in rows)


def test_audit_log_migrates_old_db_without_turn_id(tmp_path: Path):
    db_path = tmp_path / "legacy.sqlite"
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE audit (
                ts REAL,
                tool TEXT,
                args_json TEXT,
                ok INTEGER,
                detail TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO audit (ts, tool, args_json, ok, detail) VALUES (?, ?, ?, ?, ?)",
            (1.0, "legacy_tool", "{}", 1, ""),
        )

    audit = AuditLog(db_path)
    audit.record("new_tool", {"x": 1}, True, turn_id="turn-abc")

    with sqlite3.connect(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(audit)").fetchall()}
        assert "turn_id" in cols
        rows = conn.execute("SELECT tool, turn_id FROM audit ORDER BY ts").fetchall()
    assert rows[0] == ("legacy_tool", None)
    assert rows[1] == ("new_tool", "turn-abc")


def test_chat_stream_emits_started_and_final(client: TestClient, tmp_path: Path, app_state: ProcessState):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})

    with client.stream("POST", "/chat/stream", json={"message": "你好"}) as r:
        assert r.status_code == 200
        text = "".join(r.iter_text())
    assert "event: started" in text
    assert "event: final" in text
    assert "你好，已就绪。" in text
    sid = None
    for block in text.split("\n\n"):
        if "event: final" in block:
            for line in block.splitlines():
                if line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    sid = data.get("session_id")
    assert sid
    msgs = app_state.sessions.get_messages(sid)
    assert any(m.get("role") == "user" for m in msgs)


def test_chat_second_turn_includes_history(client: TestClient, tmp_path: Path, app_state: ProcessState):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})

    r1 = client.post("/chat", json={"message": "第一句"})
    sid = r1.json()["session_id"]
    r2 = client.post("/chat", json={"message": "第二句", "session_id": sid})
    assert r2.status_code == 200
    msgs = app_state.sessions.get_messages(sid)
    user_contents = [m.get("content") for m in msgs if m.get("role") == "user"]
    assert "第一句" in user_contents
    assert "第二句" in user_contents
    # Fake gateway echoes last user via default - ensure history length grew
    assert len(msgs) >= 4


def test_session_store_persists_in_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    store = SessionStore()
    sid = store.create_session("/tmp/ws")
    store.append_messages(sid, [{"role": "user", "content": "hi"}])
    assert (tmp_path / "db" / "sessions.sqlite").is_file()
    assert store.get_messages(sid)[0]["content"] == "hi"
    meta = store.get_session(sid)
    assert meta is not None
    assert meta["title"] == "hi"


def test_sessions_api_list_create_delete(client: TestClient, tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})

    created = client.post("/sessions", json={})
    assert created.status_code == 200
    sid = created.json()["session"]["id"]
    assert created.json()["session"]["title"] == "新对话"

    listed = client.get("/sessions")
    assert listed.status_code == 200
    ids = {s["id"] for s in listed.json()["sessions"]}
    assert sid in ids

    client.post("/chat", json={"message": "整理会议纪要", "session_id": sid})
    msgs = client.get(f"/sessions/{sid}/messages")
    assert msgs.status_code == 200
    roles = [m["role"] for m in msgs.json()["messages"]]
    assert "user" in roles

    meta = client.get(f"/sessions/{sid}").json()["session"]
    assert meta["title"] == "整理会议纪要"

    deleted = client.delete(f"/sessions/{sid}")
    assert deleted.status_code == 200
    assert client.get(f"/sessions/{sid}").status_code == 404


def test_prepare_chat_injects_audit(client: TestClient, tmp_path: Path, app_state: ProcessState):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})
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


def test_chat_uses_state_audit(client: TestClient, tmp_path: Path, app_state: ProcessState, monkeypatch):
    """Regression: _prepare_chat must pass office.audit into ToolExecutor."""
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})
    seen: dict = {}

    from office_agent.tools import ToolExecutor

    class Spy(ToolExecutor):
        def __init__(self, *a, **kw):
            seen["audit"] = kw.get("audit")
            super().__init__(*a, **kw)

    monkeypatch.setattr("office_agent.app.ToolExecutor", Spy)
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert seen.get("audit") is app_state.audit


def test_post_config_permission_mode(client: TestClient, app_state: ProcessState):
    r = client.post("/config", json={"permission_mode": "cautious"})
    assert r.status_code == 200
    assert app_state.config.permission_mode == "cautious"
    got = client.get("/config")
    assert got.json()["permission_mode"] == "cautious"


def test_sync_chat_cautious_auto_allows_risky_tool(
    client: TestClient, tmp_path: Path, app_state: ProcessState
):
    """Sync /chat uses non-interactive gate; cautious + workspace_write completes without hanging."""
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})

    app_state.config.permission_mode = "cautious"
    app_state.gateway_factory = lambda _cfg: FakeGateway(
        responses=[
            _completion(
                tool_calls=[
                    _tool_call(
                        "c1",
                        "workspace_write",
                        {"path": "notes.txt", "content": "hello\n"},
                    )
                ]
            ),
            _completion(content="已写入 notes.txt"),
        ]
    )

    start = time.time()
    r = client.post("/chat", json={"message": "写个文件"})
    elapsed = time.time() - start

    assert r.status_code == 200
    assert elapsed < 5.0
    assert r.json()["reply"] == "已写入 notes.txt"
    assert (ws / "notes.txt").read_text(encoding="utf-8") == "hello\n"


def test_chat_stream_permission_request_then_allow(
    client: TestClient, tmp_path: Path, app_state: ProcessState
):
    """SSE emits permission_request; POST allow unblocks workspace_write; final succeeds."""
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})

    app_state.config.permission_mode = "cautious"
    app_state.gateway_factory = lambda _cfg: FakeGateway(
        responses=[
            _completion(
                tool_calls=[
                    _tool_call(
                        "c1",
                        "workspace_write",
                        {"path": "notes.txt", "content": "hello\n"},
                    )
                ]
            ),
            _completion(content="已写入 notes.txt"),
        ]
    )

    resolved = threading.Event()
    errors: list[BaseException] = []

    def resolve_when_ready() -> None:
        try:
            deadline = time.time() + 5.0
            while time.time() < deadline:
                if app_state.gates:
                    request_id = next(iter(app_state.gates))
                    r = client.post(
                        f"/chat/permissions/{request_id}",
                        json={"allow": True},
                    )
                    assert r.status_code == 200, r.text
                    assert r.json()["ok"] is True
                    resolved.set()
                    return
                time.sleep(0.02)
            raise AssertionError("permission gate was never registered")
        except BaseException as e:
            errors.append(e)

    t = threading.Thread(target=resolve_when_ready, daemon=True)
    t.start()

    with client.stream("POST", "/chat/stream", json={"message": "写个文件"}) as r:
        assert r.status_code == 200
        text = "".join(r.iter_text())

    t.join(timeout=5)
    assert not errors, errors
    assert resolved.is_set()
    assert "event: permission_request" in text
    assert "event: final" in text
    assert "已写入 notes.txt" in text
    assert (ws / "notes.txt").read_text(encoding="utf-8") == "hello\n"
