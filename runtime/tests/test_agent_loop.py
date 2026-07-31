from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from office_agent.agent_loop import (
    TOOL_SCHEMAS,
    _build_onboarding_system_prompt,
    _build_system_prompt,
    run_agent,
)
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


@dataclass
class FakeGateway:
    responses: list[Any]

    def __post_init__(self) -> None:
        self.chat_calls: list[dict[str, Any]] = []

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
        # Copy so later mutations in run_agent don't rewrite the recorded request
        self.chat_calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        if not self.responses:
            raise RuntimeError("FakeGateway: no more scripted responses")
        return self.responses.pop(0)


def test_tool_loop_lists_workspace_then_replies(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws" / "note.txt").write_text("x", encoding="utf-8")

    executor = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    catalog = [{"id": "s1", "name": "示例", "description": "测试", "tier": "light"}]

    gateway = FakeGateway(
        responses=[
            _completion(
                tool_calls=[_tool_call("c1", "workspace_list", {"path": "."})],
            ),
            _completion(content="目录已列出"),
        ]
    )

    result = run_agent(
        user_message="列出目录",
        attached_paths=[],
        gateway=gateway,
        tools=executor,
        catalog=catalog,
        max_steps=10,
    )

    assert result.final_text == "目录已列出"
    assert len(result.tool_events) == 1
    assert result.tool_events[0]["name"] == "workspace_list"
    assert result.tool_events[0]["result"]["ok"] is True
    assert any(e["name"] == "note.txt" for e in result.tool_events[0]["result"]["entries"])
    assert len(gateway.chat_calls) == 2

    system = gateway.chat_calls[0]["messages"][0]
    assert system["role"] == "system"
    assert "办公" in system["content"] or "助手" in system["content"]
    assert "示例" in system["content"] or "s1" in system["content"]


def test_tool_schema_names_match_executor():
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    expected = {
        "workspace_list",
        "workspace_read",
        "workspace_write",
        "workspace_extract",
        "run_workspace_script",
        "read_skill",
        "run_skill_script",
        "run_shared_script",
        "ask_user",
        "finish",
    }
    assert names == expected


def test_onboarding_prompt_local_colleague_tone_and_boundaries():
    text = _build_onboarding_system_prompt()
    assert "本地使用" in text
    assert "不联网" in text
    assert "打开文件夹" in text
    assert "机关同事" in text or "当面交代" in text
    assert "内网使用" not in text
    assert "自然口语" not in text
    assert "禁止" in text and "贴肉" in text  # ban-list example, not endorsement
    assert "不是外网搜索" in text


def test_work_prompt_includes_local_use_and_colleague_tone():
    text = _build_system_prompt([])
    assert "本地使用" in text
    assert "不联网" in text
    assert "内网使用" not in text


def test_system_prompt_requires_reading_skill_body(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()
    executor = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    gateway = FakeGateway(responses=[_completion(content="好")])
    run_agent(
        user_message="排版",
        attached_paths=[],
        gateway=gateway,
        tools=executor,
        catalog=[{"id": "s1", "name": "示例", "description": "测试", "tier": "light"}],
        max_steps=3,
    )
    system = gateway.chat_calls[0]["messages"][0]["content"]
    assert "read_skill" in system
    assert "SKILL.md" in system


def test_read_skill_returns_body_to_model(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = tmp_path / "skills" / "s1"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: s1\ndescription: d\n---\n\n# 三步纪律\n\nStep 1 先读素材\n",
        encoding="utf-8",
    )
    (tmp_path / "ws").mkdir()
    executor = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    gateway = FakeGateway(
        responses=[
            _completion(tool_calls=[_tool_call("c1", "read_skill", {"skill_id": "s1"})]),
            _completion(content="已按技能步骤执行"),
        ]
    )
    result = run_agent(
        user_message="用 s1 干活",
        attached_paths=[],
        gateway=gateway,
        tools=executor,
        catalog=[{"id": "s1", "name": "示例", "description": "d", "tier": "light"}],
        max_steps=5,
    )
    assert result.final_text == "已按技能步骤执行"
    assert result.tool_events[0]["result"]["ok"] is True
    # The workflow body must reach the model on the follow-up request.
    tool_msg = next(m for m in gateway.chat_calls[1]["messages"] if m["role"] == "tool")
    assert "三步纪律" in tool_msg["content"]


def test_finish_tool_ends_with_summary(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()
    executor = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    gateway = FakeGateway(
        responses=[
            _completion(
                tool_calls=[_tool_call("c1", "finish", {"summary": "任务完成"})],
            ),
        ]
    )
    result = run_agent(
        user_message="结束",
        attached_paths=[],
        gateway=gateway,
        tools=executor,
        catalog=[],
        max_steps=5,
    )
    assert result.final_text == "任务完成"
    assert len(result.tool_events) == 1
    assert result.tool_events[0]["name"] == "finish"


def test_ask_user_pauses_for_answer(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()
    executor = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    gateway = FakeGateway(
        responses=[
            _completion(
                tool_calls=[_tool_call("c1", "ask_user", {"question": "哪个docx？"})],
            ),
            _completion(content="不应再继续"),
        ]
    )
    result = run_agent(
        user_message="帮我排版",
        attached_paths=[],
        gateway=gateway,
        tools=executor,
        catalog=[],
        max_steps=5,
    )
    assert result.final_text == "哪个docx？"
    assert len(gateway.chat_calls) == 1
    assert result.tool_events[0]["name"] == "ask_user"


def test_history_is_passed_to_model(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()
    executor = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    gateway = FakeGateway(responses=[_completion(content="开始排版")])
    history = [
        {"role": "user", "content": "帮我排版"},
        {"role": "assistant", "content": "哪个docx？"},
        {"role": "user", "content": "报告.docx"},
    ]
    # Only pass prior turns excluding the latest user message (API will append latest)
    prior = history[:-1]
    result = run_agent(
        user_message="报告.docx",
        attached_paths=[],
        gateway=gateway,
        tools=executor,
        catalog=[],
        max_steps=3,
        history=prior,
    )
    assert result.final_text == "开始排版"
    msgs = gateway.chat_calls[0]["messages"]
    roles = [m["role"] for m in msgs]
    assert roles[0] == "system"
    assert any(m.get("content") == "帮我排版" for m in msgs)
    assert any(m.get("content") == "哪个docx？" for m in msgs)
    assert msgs[-1]["role"] == "user" and msgs[-1]["content"] == "报告.docx"


def test_max_steps_stops_loop(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()
    executor = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    gateway = FakeGateway(
        responses=[
            _completion(tool_calls=[_tool_call("c1", "workspace_list", {"path": "."})]),
            _completion(tool_calls=[_tool_call("c2", "workspace_list", {"path": "."})]),
        ]
    )
    result = run_agent(
        user_message="一直列",
        attached_paths=[],
        gateway=gateway,
        tools=executor,
        catalog=[],
        max_steps=1,
    )
    assert len(result.tool_events) == 1
    assert len(gateway.chat_calls) == 1


def test_attached_paths_injected_into_user_content(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "report.docx").write_text("x", encoding="utf-8")

    executor = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    gateway = FakeGateway(responses=[_completion(content="已收到")])
    result = run_agent(
        user_message="请处理这个文件",
        attached_paths=["report.docx"],
        gateway=gateway,
        tools=executor,
        catalog=[],
        max_steps=3,
    )

    user_msg = gateway.chat_calls[0]["messages"][-1]
    assert user_msg["role"] == "user"
    assert "report.docx" in user_msg["content"]
    assert "用户附带的文件路径" in user_msg["content"]
    assert result.messages[0]["content"] == user_msg["content"]


def test_on_event_emits_tool_and_status(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()
    executor = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    gateway = FakeGateway(
        responses=[
            _completion(tool_calls=[_tool_call("c1", "workspace_list", {"path": "."})]),
            _completion(content="好了"),
        ]
    )
    events: list[dict[str, Any]] = []
    result = run_agent(
        user_message="列一下",
        attached_paths=[],
        gateway=gateway,
        tools=executor,
        catalog=[],
        max_steps=5,
        on_event=events.append,
    )
    assert result.final_text == "好了"
    types = [e["type"] for e in events]
    assert "status" in types
    assert "tool_start" in types
    assert "tool_done" in types
    start = next(e for e in events if e["type"] == "tool_start")
    assert start["label"] == "查看工作区"
    assert start["id"] == "c1"
    done = next(e for e in events if e["type"] == "tool_done")
    assert done["ok"] is True


def test_onboarding_passes_tools_none_to_gateway(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    gateway = FakeGateway(responses=[_completion(content="我是入门助手")])
    result = run_agent(
        user_message="你能做什么？",
        attached_paths=[],
        gateway=gateway,
        tools=None,
        catalog=[],
        max_steps=3,
        onboarding=True,
    )
    assert result.final_text == "我是入门助手"
    assert result.tool_events == []
    assert len(gateway.chat_calls) == 1
    assert gateway.chat_calls[0]["tools"] is None


def test_onboarding_ignores_tool_calls_without_orphans_or_side_effects(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    marker = ws / "should-not-exist.txt"

    class SpyExecutor(ToolExecutor):
        def __init__(self) -> None:
            super().__init__(Workspace(ws), SkillRegistry(), permission_mode="trust")
            self.execute_calls: list[tuple[str, dict[str, Any]]] = []

        def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
            self.execute_calls.append((name, args))
            if name == "workspace_write":
                marker.write_text("leaked", encoding="utf-8")
            return super().execute(name, args)

    spy = SpyExecutor()
    gateway = FakeGateway(
        responses=[
            _completion(
                content="先打开文件夹吧",
                tool_calls=[
                    _tool_call(
                        "c1",
                        "workspace_write",
                        {"path": "should-not-exist.txt", "content": "leaked"},
                    )
                ],
            )
        ]
    )
    result = run_agent(
        user_message="写入文件",
        attached_paths=[],
        gateway=gateway,
        tools=spy,
        catalog=[],
        max_steps=5,
        onboarding=True,
    )

    assert gateway.chat_calls[0]["tools"] is None
    assert result.tool_events == []
    assert spy.execute_calls == []
    assert not marker.exists()
    assert "打开文件夹" in result.final_text or result.final_text == "先打开文件夹吧"

    # No orphan tool_calls: every assistant tool_call id has a tool result.
    pending: set[str] = set()
    answered: set[str] = set()
    for msg in result.messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict) and tc.get("id"):
                    pending.add(str(tc["id"]))
        elif msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id")
            if tc_id:
                answered.add(str(tc_id))
    assert pending <= answered
    tool_msgs = [m for m in result.messages if m.get("role") == "tool"]
    assert any("onboarding" in str(m.get("content", "")) for m in tool_msgs)
