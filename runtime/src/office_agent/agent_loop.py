from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from office_agent.tools import ToolExecutor

EventCallback = Callable[[dict[str, Any]], None]

TOOL_LABELS: dict[str, str] = {
    "workspace_list": "查看工作区",
    "workspace_read": "读取文件",
    "workspace_write": "写入文件",
    "run_workspace_script": "运行工作区脚本",
    "run_skill_script": "运行 Skill 脚本",
    "run_shared_script": "运行共享脚本",
    "ask_user": "需要你确认",
    "finish": "完成任务",
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "workspace_list",
            "description": (
                "列出【当前工作区】内某相对路径下的文件与目录。"
                "Skill 的 scripts 不在工作区，请改用 run_skill_script / run_shared_script。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "工作区内相对路径，默认为 . ；必须是已存在的目录",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_read",
            "description": "读取工作区内文本文件内容",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "相对文件路径"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_write",
            "description": (
                "在工作区内写入或覆盖文本文件。"
                "脚本与中间产物 → .office-agent/work/；"
                "最终交付（docx/pdf 等）→ output/；"
                "不要往工作区根目录堆 Agent 产出（根目录留给用户源材料）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相对路径，如 .office-agent/work/merge_docs.py 或 output/AI.docx",
                    },
                    "content": {"type": "string", "description": "文件内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_workspace_script",
            "description": (
                "在工作区沙箱内直接运行已有的 .py 脚本（cwd=工作区根目录）。"
                "脚本应位于 .office-agent/work/；脚本内最终产出请写到 output/（如 output/AI.docx）。"
                "写完后必须用本工具执行，禁止让用户去终端手动 python。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "工作区内相对路径，如 .office-agent/work/merge_docs.py",
                    },
                    "args": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_skill_script",
            "description": (
                "运行已安装 Skill 的 scripts/*.py（位于应用数据目录，不在工作区）。"
                "排版可用 government-document-format/format_gongwen.py；"
                "写作可用 gongwen-rag-writing 下 build_index.py 等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_id": {"type": "string"},
                    "script": {"type": "string", "description": "脚本文件名，如 format_gongwen.py"},
                    "args": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["skill_id", "script"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shared_script",
            "description": (
                "运行共享脚本。公文排版优先：name=format_gongwen，args=[工作区内docx路径]。"
                "排版结果若为新文件，应落到 output/。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "共享脚本逻辑名（不含 .py），如 format_gongwen"},
                    "args": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "仅当缺少关键文件路径导致无法执行时，向用户提一个问题。"
                "整轮最多一次；用户回答后必须执行工具，禁止继续追问同一事项。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "结束当前任务并给出面向用户的总结（提及成果在 output/ 下的路径）",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        },
    },
]


@dataclass
class AgentResult:
    messages: list[dict[str, Any]]
    final_text: str
    tool_events: list[dict[str, Any]]


def _build_system_prompt(catalog: list[dict[str, Any]]) -> str:
    catalog_json = json.dumps(catalog, ensure_ascii=False, indent=2)
    return (
        "你是内网办公智能助手，帮助用户在当前工作区内处理文书与文件任务。"
        "请优先使用已启用的 Skill 与内置工具；不得尝试访问工作区外路径或执行 shell。\n"
        "目录约定（必须遵守）：\n"
        "- 工作区根目录：只保留用户自己的源材料（纪要、模板、附件等），不要往根目录堆 Agent 产出；\n"
        "- `output/`：最终交付成果（如 `output/AI.docx`、排版后的公文）；\n"
        "- `.office-agent/work/`：过程文件（自写 .py、草稿、临时 json/中间文件）；\n"
        "- 运行脚本时 cwd 已是工作区根，脚本内请用 `output/文件名` 写出最终成果，"
        "脚本自身放在 `.office-agent/work/xxx.py`。\n"
        "重要区分：\n"
        "- workspace_* 只能访问用户打开的工作区文件夹；\n"
        "- 工作区内的 .py 用 run_workspace_script 执行（写完脚本后立刻执行）；\n"
        "- Skill 的 scripts/ 不在工作区内，必须用 run_skill_script 或 run_shared_script；\n"
        "- 公文排版优先 run_shared_script(name=format_gongwen, args=[docx路径])；\n"
        "- 不要对「scripts」调用 workspace_list，除非工作区里真有该目录。\n"
        "执行纪律：\n"
        "- 禁止让用户去终端/命令行自行运行 python、bash 或其它命令；你必须用工具代为执行；\n"
        "- 用户已给出足够信息时，立即调用工具执行，不要反复确认；\n"
        "- 若历史里用户已回答过你的问题，直接执行，禁止再次用 ask_user 问同一问题；\n"
        "- ask_user 整轮最多使用一次，且仅当缺少关键路径/文件名导致无法动手时才用；\n"
        "- 可用 workspace_list 自行查找 .docx，而不是不停问用户。\n"
        f"\n已启用的 Skill 目录（JSON）：\n{catalog_json}"
    )


def _build_user_content(user_message: str, attached_paths: list[str]) -> str:
    if not attached_paths:
        return user_message
    paths_text = "\n".join(f"- {p}" for p in attached_paths)
    return f"{user_message}\n\n用户附带的文件路径：\n{paths_text}"


def _history_without_system(history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not history:
        return []
    return [m for m in history if m.get("role") != "system"]


def _ask_user_text(args: dict[str, Any], result: dict[str, Any]) -> str:
    for key in ("prompt", "question"):
        if args.get(key):
            return str(args[key]).strip()
        if result.get(key):
            return str(result[key]).strip()
    return "请补充必要信息后继续。"


def _parse_tool_args(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _assistant_message_from_response(message: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]
    return out


def tool_label(name: str) -> str:
    return TOOL_LABELS.get(name, name)


def args_summary(name: str, args: dict[str, Any]) -> str:
    if name == "workspace_list":
        return str(args.get("path") or ".")
    if name in {"workspace_read", "workspace_write", "run_workspace_script"}:
        return str(args.get("path") or "")
    if name == "run_skill_script":
        return f"{args.get('skill_id', '')}/{args.get('script', '')}".strip("/")
    if name == "run_shared_script":
        script = str(args.get("name") or "")
        extra = args.get("args") or []
        if extra:
            return f"{script} {' '.join(str(a) for a in extra[:2])}".strip()
        return script
    if name == "ask_user":
        q = str(args.get("question") or args.get("prompt") or "")
        return q[:80]
    if name == "finish":
        return str(args.get("summary") or "")[:80]
    raw = json.dumps(args, ensure_ascii=False)
    return raw if len(raw) <= 80 else raw[:77] + "…"


def result_summary(name: str, result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return str(result)[:120]
    if result.get("ok") is False:
        err = str(result.get("error") or result.get("stderr") or "失败")
        return err[:120]
    if name == "workspace_list":
        entries = result.get("entries") or []
        return f"{len(entries)} 项"
    if name == "workspace_write":
        return str(result.get("path") or "已写入")
    if name in {"run_workspace_script", "run_skill_script", "run_shared_script"}:
        code = result.get("returncode", result.get("exit_code"))
        out = str(result.get("stdout") or "").strip().splitlines()
        head = out[0][:80] if out else ""
        if code is not None and head:
            return f"退出码 {code} · {head}"
        if code is not None:
            return f"退出码 {code}"
        return head or "已完成"
    if name == "finish":
        return str(result.get("summary") or "完成")[:80]
    return "完成"


def run_agent(
    user_message: str,
    attached_paths: list[str],
    gateway: Any,
    tools: ToolExecutor,
    catalog: list[dict[str, Any]],
    max_steps: int,
    history: list[dict[str, Any]] | None = None,
    on_event: EventCallback | None = None,
) -> AgentResult:
    """Run one user turn. ``history`` is prior session turns (no system message)."""

    def emit(payload: dict[str, Any]) -> None:
        if on_event is not None:
            on_event(payload)

    prior = _history_without_system(history)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _build_system_prompt(catalog)},
        *prior,
        {"role": "user", "content": _build_user_content(user_message, attached_paths)},
    ]
    # Messages newly produced this turn (exclude revived history + system)
    new_from = 1 + len(prior)
    tool_events: list[dict[str, Any]] = []
    final_text = ""

    for _ in range(max_steps):
        emit({"type": "status", "phase": "planning"})
        response = gateway.chat(messages, tools=TOOL_SCHEMAS)
        message = response.choices[0].message
        messages.append(_assistant_message_from_response(message))

        if message.tool_calls:
            emit({"type": "status", "phase": "tools"})
            stop_for_user = False
            for tc in message.tool_calls:
                name = tc.function.name
                args = _parse_tool_args(tc.function.arguments)
                label = tool_label(name)
                emit(
                    {
                        "type": "tool_start",
                        "id": tc.id,
                        "name": name,
                        "label": label,
                        "args_summary": args_summary(name, args),
                    }
                )
                result = tools.execute(name, args)
                ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
                summary = result_summary(name, result if isinstance(result, dict) else {"ok": False, "error": str(result)})
                emit(
                    {
                        "type": "tool_done",
                        "id": tc.id,
                        "name": name,
                        "label": label,
                        "ok": ok,
                        "summary": summary,
                    }
                )
                tool_events.append({"name": name, "args": args, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
                if name == "ask_user":
                    final_text = _ask_user_text(args, result)
                    stop_for_user = True
                    break
                if name == "finish" and result.get("ok"):
                    final_text = str(result.get("summary") or "")
                    emit({"type": "status", "phase": "finishing"})
                    return AgentResult(
                        messages=messages[new_from:],
                        final_text=final_text,
                        tool_events=tool_events,
                    )
            if stop_for_user:
                emit({"type": "status", "phase": "finishing"})
                return AgentResult(
                    messages=messages[new_from:],
                    final_text=final_text,
                    tool_events=tool_events,
                )
            continue

        if message.content:
            final_text = message.content.strip()
            emit({"type": "status", "phase": "finishing"})
            return AgentResult(
                messages=messages[new_from:],
                final_text=final_text,
                tool_events=tool_events,
            )

    if not final_text and tool_events:
        final_text = "已达到最大工具步数限制，请根据已完成步骤继续或重新发起任务。"
    emit({"type": "status", "phase": "finishing"})
    return AgentResult(
        messages=messages[new_from:],
        final_text=final_text,
        tool_events=tool_events,
    )
