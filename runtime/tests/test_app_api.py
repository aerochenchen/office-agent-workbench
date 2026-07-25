from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from office_agent.agent_loop import AgentResult
from office_agent.app import ProcessState, create_app
from office_agent.config import AppConfig
from office_agent.session_store import SessionStore
from office_agent.skills import SkillRegistry


def _completion(*, content: str | None = None, tool_calls: list[Any] | None = None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


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
        "---\nname: my-skill\ndescription: install test\ntier: light\n"
        "permissions:\n  - run_python\n---\n\n# y\n",
        encoding="utf-8",
    )
    preview = client.post("/skills/inspect", json={"path": str(src)})
    assert preview.status_code == 200
    assert preview.json()["skill"]["permissions"] == ["run_python"]

    r = client.post("/skills/install", json={"path": str(src), "enabled": True})
    assert r.status_code == 200
    assert r.json()["skill"]["id"] == "my-skill"
    assert r.json()["skill"]["permissions"] == ["run_python"]

    off = client.post("/skills/my-skill/enabled", json={"enabled": False})
    assert off.status_code == 200
    listed = client.get("/skills").json()["skills"]
    assert listed[0]["enabled"] is False


def test_install_zip_via_api(client: TestClient, tmp_path: Path):
    src = tmp_path / "pkg" / "zip-skill"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: zip-skill\ndescription: from zip\ntier: light\n---\n\n# z\n",
        encoding="utf-8",
    )
    z = tmp_path / "s.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(src / "SKILL.md", arcname="zip-skill/SKILL.md")
    r = client.post("/skills/install", json={"path": str(z)})
    assert r.status_code == 200
    assert r.json()["skill"]["id"] == "zip-skill"


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
