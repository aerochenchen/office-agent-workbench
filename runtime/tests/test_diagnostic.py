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


def test_emit_swallows_oserror_when_log_path_fails(monkeypatch):
    def _raise_oserror(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("office_agent.diagnostic.current_log_path", _raise_oserror)
    emit("chat_started", level="info", turn_id="t1")


def test_configure_prunes_old_files(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    logs = tmp_path / "logs"
    logs.mkdir()
    old = logs / "runtime-2000-01-01.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    configure()
    assert not old.exists()
