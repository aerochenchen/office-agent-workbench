from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from office_agent.agent_loop import run_agent
from office_agent.app import ProcessState, create_app
from office_agent.cancel import CancelToken, CancelledError
from office_agent.config import AppConfig
from office_agent.session_store import SessionStore
from office_agent.skills import SkillRegistry
from office_agent.tools import ToolExecutor
from office_agent.workspace import Workspace


def _completion(*, content: str | None = None, tool_calls: list[Any] | None = None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _tool_call(call_id: str, name: str, arguments: dict[str, Any]):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments, ensure_ascii=False)),
    )


def test_cancel_token_check_raises_after_cancel():
    token = CancelToken()
    token.check()  # no-op
    token.cancel()
    with pytest.raises(CancelledError):
        token.check()


def test_run_agent_stops_on_cancel_before_max_steps(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()

    @dataclass
    class CountingGateway:
        calls: int = 0
        token: CancelToken | None = None

        def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
            self.calls += 1
            # Cancel after the first model call so the next loop/tool check stops the turn.
            if self.token is not None:
                self.token.cancel()
            return _completion(
                tool_calls=[_tool_call(f"c{self.calls}", "workspace_list", {"path": "."})]
            )

    token = CancelToken()
    gateway = CountingGateway(token=token)
    executor = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust_workspace")
    result = run_agent(
        user_message="列出很多遍",
        attached_paths=[],
        gateway=gateway,
        tools=executor,
        catalog=[],
        max_steps=20,
        cancel=token,
    )

    assert gateway.calls < 20
    assert gateway.calls == 1
    assert "取消" in result.final_text


@pytest.fixture
def app_state(tmp_path: Path, monkeypatch) -> ProcessState:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    cfg = AppConfig(
        api_base="http://127.0.0.1:8000/v1",
        api_key="test-key",
        model="deepseek-v4-flash",
        allowed_hosts=["127.0.0.1", "localhost"],
        max_tool_steps=20,
    )
    return ProcessState(
        config=cfg,
        registry=SkillRegistry(),
        sessions=SessionStore(),
        gateway_factory=lambda _cfg: FakeBlockingGateway(),
    )


@pytest.fixture
def client(app_state: ProcessState) -> TestClient:
    return TestClient(create_app(app_state))


@dataclass
class FakeBlockingGateway:
    """Blocks in chat until released; always returns another tool call."""

    calls: int = 0
    entered: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
        self.calls += 1
        self.entered.set()
        self.release.wait(timeout=10)
        return _completion(
            tool_calls=[_tool_call(f"c{self.calls}", "workspace_list", {"path": "."})]
        )


def test_chat_cancel_stops_stream_worker(client: TestClient, tmp_path: Path, app_state: ProcessState):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})
    sid = client.post("/sessions", json={"workspace_path": str(ws)}).json()["session"]["id"]

    gateway = FakeBlockingGateway()
    app_state.gateway_factory = lambda _cfg: gateway

    events: list[str] = []
    errors: list[BaseException] = []

    def stream_worker() -> None:
        try:
            with client.stream(
                "POST",
                "/chat/stream",
                json={"message": "跑很久", "session_id": sid},
            ) as r:
                assert r.status_code == 200
                for chunk in r.iter_text():
                    events.append(chunk)
        except BaseException as e:
            errors.append(e)

    t = threading.Thread(target=stream_worker, daemon=True)
    t.start()

    assert gateway.entered.wait(timeout=5)
    # Wait until cancel token is registered
    deadline = time.time() + 5
    while time.time() < deadline and sid not in app_state.active_cancel:
        time.sleep(0.01)
    assert sid in app_state.active_cancel

    cancel_r = client.post("/chat/cancel", json={"session_id": sid})
    assert cancel_r.status_code == 200
    assert cancel_r.json()["ok"] is True

    gateway.release.set()
    t.join(timeout=10)
    assert not errors, errors

    text = "".join(events)
    assert gateway.calls < 20
    assert "event: final" in text or "event: error" in text
    assert "取消" in text or "cancel" in text.lower()


def test_chat_cancel_no_active_run(client: TestClient, tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    client.post("/workspace/open", json={"path": str(ws)})
    sid = client.post("/sessions", json={"workspace_path": str(ws)}).json()["session"]["id"]

    r = client.post("/chat/cancel", json={"session_id": sid})
    assert r.status_code in (404, 200)
    if r.status_code == 200:
        assert r.json().get("ok") is False
