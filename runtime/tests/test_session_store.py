import json
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
    assert [m["role"] for m in ui] == ["user", "assistant"]
    assert ui[0]["content"] == "你好"
    assert ui[1]["content"] == "完成了"


def _tool_call_payload(call_id: str, name: str, arguments: dict) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


def test_history_to_ui_messages_hides_tool_call_thinking():
    """Reload must match live UI: one user + one final assistant per turn."""
    history = [
        {"role": "user", "content": "分析现在有什么资料"},
        {
            "role": "assistant",
            "content": "I'll start by looking at what's in the workspace.",
            "tool_calls": [_tool_call_payload("c1", "workspace_list", {"path": "."})],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": json.dumps({"ok": True, "entries": []}),
        },
        {"role": "assistant", "content": "已摸完底，下面把清单和发现写成文件。"},
        {
            "role": "user",
            "content": "现在要到华东空管局通信网络中心进行技术交流,介绍文书通产品.",
        },
        {
            "role": "assistant",
            "content": "这个任务要出 PPT 和讲解稿，我先读一下对应技能的做法。",
            "tool_calls": [_tool_call_payload("c2", "read_skill", {"skill_id": "slides"})],
        },
        {
            "role": "tool",
            "tool_call_id": "c2",
            "content": json.dumps({"ok": True, "content": "skill"}),
        },
        {
            "role": "assistant",
            "content": "材料口径我已经摸清了。这个任务要出「提纲 + PPT + 讲解稿」，按规矩先立工作计划，请你过一眼。",
        },
    ]
    ui = history_to_ui_messages(history)
    assert [m["role"] for m in ui] == ["user", "assistant", "user", "assistant"]
    assert ui[0]["content"] == "分析现在有什么资料"
    assert ui[1]["content"] == "已摸完底，下面把清单和发现写成文件。"
    assert "I'll start" not in ui[1]["content"]
    assert "我先读一下" not in ui[3]["content"]
    assert "先立工作计划" in ui[3]["content"]
    steps = ui[1].get("live_steps") or []
    assert steps
    assert steps[0]["name"] == "workspace_list"
    assert steps[0]["label"] == "查看工作区"
    assert steps[0]["status"] == "ok"


def test_history_to_ui_messages_ask_user_shows_question_not_thinking():
    history = [
        {"role": "user", "content": "制作交流ppt"},
        {
            "role": "assistant",
            "content": "材料口径我已经摸清了。",
            "tool_calls": [
                _tool_call_payload(
                    "c1",
                    "plan_create",
                    {"goal": "做交流材料", "steps": [{"id": "s1", "title": "写PPT"}]},
                ),
                _tool_call_payload(
                    "c2",
                    "ask_user",
                    {"question": "请确认是否按此工作计划执行？"},
                ),
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": json.dumps({"ok": True, "plan": {"goal": "做交流材料"}}),
        },
        {
            "role": "tool",
            "tool_call_id": "c2",
            "content": json.dumps(
                {"ok": True, "question": "请确认是否按此工作计划执行？"},
                ensure_ascii=False,
            ),
        },
    ]
    ui = history_to_ui_messages(history)
    assert [m["role"] for m in ui] == ["user", "assistant"]
    assert ui[1]["content"].startswith("请确认是否按此工作计划执行？")
    assert "材料口径我已经摸清了" not in ui[1]["content"]
    assert "`工作成果/工作计划.html`" in ui[1]["content"]


def test_history_to_ui_messages_finish_uses_summary():
    history = [
        {"role": "user", "content": "继续"},
        {
            "role": "assistant",
            "content": "PPT 写好了，收个尾。",
            "tool_calls": [
                _tool_call_payload(
                    "c1",
                    "finish",
                    {"summary": "PPT 已生成（19 页）。接着写逐页讲解稿。"},
                )
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": json.dumps(
                {
                    "ok": True,
                    "finished": True,
                    "summary": "PPT 已生成（19 页）。接着写逐页讲解稿。",
                },
                ensure_ascii=False,
            ),
        },
    ]
    ui = history_to_ui_messages(history)
    assert ui[1]["content"] == "PPT 已生成（19 页）。接着写逐页讲解稿。"
    assert "收个尾" not in ui[1]["content"]
