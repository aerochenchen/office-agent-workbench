from pathlib import Path

from office_agent.session_store import (
    DEFAULT_TITLE,
    SessionStore,
    history_to_ui_messages,
    title_from_user_text,
)


def test_create_list_delete_sessions(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    store = SessionStore()
    ws = "/tmp/project-a"
    a = store.create_session(ws)
    b = store.create_session(ws)
    store.append_messages(a, [{"role": "user", "content": "合并课件"}])
    listed = store.list_sessions(ws)
    assert len(listed) == 2
    assert listed[0]["id"] == a  # most recently updated first
    assert listed[0]["title"] == "合并课件"
    assert listed[1]["title"] == DEFAULT_TITLE
    assert store.delete_session(b) is True
    assert len(store.list_sessions(ws)) == 1
    assert store.delete_session(b) is False


def test_title_from_user_text_truncates():
    assert title_from_user_text("短") == "短"
    long = "这是一段非常非常长的用户指令用来测试标题截断行为是否正确"
    t = title_from_user_text(long)
    assert t.endswith("…")
    assert len(t) <= 24


def test_history_to_ui_messages_skips_tools():
    history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
        {"role": "tool", "content": "{}"},
        {"role": "assistant", "content": "完成了"},
    ]
    ui = history_to_ui_messages(history)
    assert ui == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "完成了"},
    ]
