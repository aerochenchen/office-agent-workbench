from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from office_agent.app import ProcessState, create_app
from office_agent.config import AppConfig
from office_agent.session_store import SessionStore
from office_agent.skills import SkillRegistry


@pytest.fixture
def app_state(tmp_path: Path, monkeypatch) -> ProcessState:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    return ProcessState(
        config=AppConfig(
            api_base="http://127.0.0.1:8000/v1",
            api_key="test-key",
            model="deepseek-v4-flash",
            allowed_hosts=["127.0.0.1", "localhost"],
        ),
        registry=SkillRegistry(),
        sessions=SessionStore(),
    )


def test_no_token_env_allows_without_header(app_state: ProcessState):
    client = TestClient(create_app(app_state))
    assert client.get("/config").status_code == 200


def test_token_env_requires_bearer(app_state: ProcessState, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_API_TOKEN", "secret-token")
    client = TestClient(create_app(app_state))

    denied = client.get("/config")
    assert denied.status_code == 401
    assert denied.json()["detail"] == "Invalid or missing API token"

    ok = client.get("/config", headers={"Authorization": "Bearer secret-token"})
    assert ok.status_code == 200


def test_health_exempt_when_token_configured(app_state: ProcessState, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_API_TOKEN", "secret-token")
    client = TestClient(create_app(app_state))
    assert client.get("/health").status_code == 200
    assert client.get("/health").json() == {"ok": True}


def test_shutdown_exempt_when_token_configured(app_state: ProcessState, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_API_TOKEN", "secret-token")
    client = TestClient(create_app(app_state))
    assert client.post("/shutdown").status_code == 200


def test_wrong_bearer_returns_401(app_state: ProcessState, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_API_TOKEN", "secret-token")
    client = TestClient(create_app(app_state))
    r = client.get("/skills", headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 401
