from __future__ import annotations
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
    emitted: list[tuple] = []

    def fake_emit(event: str, **kwargs) -> None:
        emitted.append((event, kwargs))

    monkeypatch.setattr("office_agent.diagnostic.emit", fake_emit)
    log = AuditLog(tmp_path / "a.sqlite")
    log.db_path.write_text("not-a-db", encoding="utf-8")
    log.record_event("chat_started", outcome="ok")  # must not raise
    assert emitted == [("audit_write_failed", {"level": "error", "error_code": "sqlite"})]
