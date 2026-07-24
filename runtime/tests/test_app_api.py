from __future__ import annotations

import json
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


def test_open_workspace_and_tree(client: TestClient, tmp_path: Path):
    ws = tmp_path / "project"
    ws.mkdir()
    (ws / "doc.txt").write_text("hi", encoding="utf-8")

    r = client.post("/workspace/open", json={"path": str(ws)})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    tree = client.get("/workspace/tree")
    assert tree.status_code == 200
    names = {e["name"] for e in tree.json()["entries"]}
    assert "doc.txt" in names


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
        "---\nname: my-skill\ndescription: install test\ntier: light\n---\n\n# y\n",
        encoding="utf-8",
    )
    r = client.post("/skills/install", json={"path": str(src)})
    assert r.status_code == 200
    assert r.json()["skill"]["id"] == "my-skill"

    off = client.post("/skills/my-skill/enabled", json={"enabled": False})
    assert off.status_code == 200
    listed = client.get("/skills").json()["skills"]
    assert listed[0]["enabled"] is False


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
