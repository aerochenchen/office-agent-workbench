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
    tool_schemas_for,
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
        "plan_get",
        "plan_create",
        "plan_update_step",
        "plan_set_status",
        "plan_set_approval",
        "ask_user",
        "finish",
    }
    assert names == expected


def test_workspace_script_tool_omitted_when_disabled():
    names = {s["function"]["name"] for s in tool_schemas_for(allow_workspace_scripts=False)}
    assert "run_workspace_script" not in names
    names_on = {s["function"]["name"] for s in tool_schemas_for(allow_workspace_scripts=True)}
    assert "run_workspace_script" in names_on


def test_system_prompt_disables_workspace_scripts_by_default():
    text = _build_system_prompt([])
    assert "工作区自定义脚本已关闭" in text
    enabled = _build_system_prompt([], allow_workspace_scripts=True)
    assert "用 run_workspace_script 执行" in enabled


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
    assert "在文件夹里办公" in text
    assert "不会触及文件夹以外" in text or "不会动文件夹以外" in text
    assert "精炼" in text or "相关" in text
    assert "等价" in text  # paste-vs-folder must not be framed as equal paths
    assert "贴进对话框" in text or "贴到对话" in text


def test_onboarding_prompt_folder_first_for_office_tasks():
    text = _build_onboarding_system_prompt()
    assert "办事类" in text or "排版" in text
    assert "必须先请用户「打开文件夹」" in text
    # Pure chat remains allowed; do not require folder for every utterance.
    assert "闲聊" in text or "纯对话" in text or "改措辞" in text


def test_work_prompt_includes_local_use_and_colleague_tone():
    text = _build_system_prompt([])
    assert "本地使用" in text
    assert "不联网" in text
    assert "内网使用" not in text


def test_system_prompt_includes_plan_discipline():
    text = _build_system_prompt([])
    assert "plan_create" in text
    assert "工作计划" in text
    assert "剩余步骤数或标题列表" in text
    assert "可按工作计划继续" in text


def test_system_prompt_enforces_plan_confirmation_and_dialog_only_edits():
    text = _build_system_prompt([])
    assert "plan_set_approval" in text
    assert "工作成果/工作计划.html" in text
    assert "对话框" in text
    assert "needs_user" in text
    assert "ask_user" in text
    assert "仅供查阅" in text
    assert "不用确认" in text
    assert "禁止解析或同步" in text
    assert "`工作成果/工作计划.html`" in text or "反引号" in text


def test_system_prompt_ask_user_priority():
    text = _build_system_prompt([])
    assert "缺路径" in text
    assert "plan_create 前问清" in text
    assert "工作计划确认（占本轮 ask_user）" in text
    assert "needs_user 澄清（若本轮 ask_user 已用则留待下一轮）" in text


def test_system_prompt_doc_to_sheet_not_sheet_to_brief():
    """从文稿摘字段做成表 ≠ 表格成文；禁止误路由到 sheet-to-brief + cells。"""
    text = _build_system_prompt([])
    assert "sheet-to-brief" in text
    assert "做成表" in text or "摘成表" in text or "汇总成" in text
    assert "不是 sheet-to-brief" in text or "≠ sheet-to-brief" in text or "不要用 sheet-to-brief" in text
    assert "workspace_list" in text
    assert "任意" in text or "这个文件夹" in text


def test_system_prompt_forbid_ask_path_when_folder_suffices():
    text = _build_system_prompt([])
    assert "禁止" in text
    assert "workspace_list" in text
    # 用户已指文件夹/任意格式时不要 ask_user 要文件名
    assert "文件名" in text
    assert ("这个文件夹" in text) or ("任意格式" in text) or ("任选" in text)


def test_ask_user_schema_description_allows_plan_confirmation():
    ask_schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "ask_user")
    desc = ask_schema["function"]["description"]
    assert "工作计划" in desc or "确认" in desc
    assert "整轮最多" in desc
    assert "执行工具" in desc
    assert "workspace_list" in desc
    assert "禁止" in desc or "不要" in desc


def test_finish_schema_accepts_deliverables():
    finish_schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "finish")
    props = finish_schema["function"]["parameters"]["properties"]
    assert "summary" in props
    assert "deliverables" in props
    desc = finish_schema["function"]["description"]
    assert "工作成果" in desc
    assert "deliverables" in desc or "交付" in desc


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
    assert "untrusted_workspace_data" in tool_msg["content"]


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


def test_finish_with_missing_deliverables_does_not_end_turn(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()
    executor = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    gateway = FakeGateway(
        responses=[
            _completion(
                tool_calls=[
                    _tool_call(
                        "c1",
                        "finish",
                        {
                            "summary": "已汇总",
                            "deliverables": ["工作成果/产品汇总.xlsx"],
                        },
                    )
                ],
            ),
            _completion(content="继续写出表格后再结束"),
        ]
    )
    result = run_agent(
        user_message="汇总成表",
        attached_paths=[],
        gateway=gateway,
        tools=executor,
        catalog=[],
        max_steps=5,
    )
    assert result.tool_events[0]["name"] == "finish"
    assert result.tool_events[0]["result"]["ok"] is False
    assert len(gateway.chat_calls) == 2
    assert "继续写出" in result.final_text


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


def test_ask_user_after_plan_create_injects_html_link(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()
    executor = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    gateway = FakeGateway(
        responses=[
            _completion(
                tool_calls=[
                    _tool_call(
                        "c1",
                        "plan_create",
                        {
                            "goal": "办两件事",
                            "steps": [
                                {"id": "s1", "title": "摸底"},
                                {"id": "s2", "title": "成文"},
                            ],
                        },
                    ),
                    _tool_call(
                        "c2",
                        "ask_user",
                        {"question": "请确认是否按此工作计划执行？"},
                    ),
                ],
            ),
            _completion(content="不应再继续"),
        ]
    )
    result = run_agent(
        user_message="帮我分步处理材料",
        attached_paths=[],
        gateway=gateway,
        tools=executor,
        catalog=[],
        max_steps=5,
    )
    assert "`工作成果/工作计划.html`" in result.final_text
    assert "请确认是否按此工作计划执行" in result.final_text
    assert (tmp_path / "ws" / "工作成果" / "工作计划.html").is_file()


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
