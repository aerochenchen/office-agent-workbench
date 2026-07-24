from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from office_agent.agent_loop import TOOL_SCHEMAS, run_agent
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
        "run_workspace_script",
        "run_skill_script",
        "run_shared_script",
        "ask_user",
        "finish",
    }
    assert names == expected


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
