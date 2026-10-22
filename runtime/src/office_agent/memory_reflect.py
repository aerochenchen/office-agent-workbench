"""Post-turn reflection: update memory and optionally crystallize prompt-only skills."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from office_agent.memory_store import MemoryStore
from office_agent.skill_validate import validate_skill_text
from office_agent.skills import SkillError, SkillRegistry

logger = logging.getLogger(__name__)

_UNTRUSTED_TOOLS = frozenset(
    {
        "workspace_read",
        "workspace_extract",
        "workspace_list",
        "workspace_look",
    }
)
_TRACE_TOOLS = frozenset(
    {
        "read_skill",
        "run_skill_script",
        "run_shared_script",
        "plan_create",
        "plan_update_step",
        "plan_set_status",
        "plan_set_approval",
        "plan_get",
        "finish",
    }
)
_OVERLAP_MIN = 12

# User must say something durable about themselves / standing prefs — Hermes-style.
# Task chatter alone must not trigger a memory write.
_MEMORY_SIGNAL_RE = re.compile(
    r"(记住|请记|记一下|别忘|以后都|以后不要|以后别|不要再|别再|少问|少确认|"
    r"我习惯|我喜欢|我偏好|固定用|每次都|一律|默认就|"
    r"remember|prefer|always|never\s+ask|don'?t\s+ask)",
    re.IGNORECASE,
)

_SKILLISH_RE = re.compile(
    r"(read_skill|run_skill|run_shared|SKILL\.md|技能正文|硬规则|步数预算|"
    r"必须先|禁止把|按其中的步骤|granularity=|workspace_extract|"
    r"format_gongwen|deliverables)",
    re.IGNORECASE,
)

_REFLECT_SYSTEM = (
    "你是文书通的记忆整理器。记忆只记「跨任务仍成立」的人与偏好，不记办事方法。"
    "只输出一个 JSON 对象，不要 markdown，不要解释。"
    '格式：{"habits":[{"topic":"短主题","text":"一句关于这个人的事实"}],"recent":[]}。'
    "habits 最多 2 条；写成陈述事实（如「用户偏好少确认」），不要写成对助手的命令。"
    "recent 必须始终为空数组 []，不要写近况或本轮事项。"
    "只根据「使用者原话」提炼。工具名、技能名、助手总结一律忽略。"
    "禁止写入：技能/说明书里的步骤与纪律、排版校对规则、工具用法、"
    "本轮做完了什么、材料正文、可从技能再次读到的内容。"
    "使用者只是下了办事任务、没有表达偏好或纠正时，返回 {\"habits\":[],\"recent\":[]}。"
)


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def strip_attachment_footer(text: str) -> str:
    marker = "\n\n用户附带的文件路径："
    if marker in text:
        return text.split(marker, 1)[0].strip()
    return (text or "").strip()


def user_has_durable_signal(user_message: str) -> bool:
    """True when the user stated a standing preference / correction / remember-me."""
    text = strip_attachment_footer(user_message)
    if not text:
        return False
    return bool(_MEMORY_SIGNAL_RE.search(text))


def should_reflect(
    *,
    onboarding: bool,
    tool_events: list[dict[str, Any]] | None,
    cancelled: bool = False,
    error: bool = False,
) -> bool:
    """Whether this turn is eligible for post-turn side effects (memory / crystallize)."""
    if onboarding or cancelled or error:
        return False
    events = tool_events or []
    if not events:
        return False
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name = str(ev.get("name") or "")
        result = ev.get("result") if isinstance(ev.get("result"), dict) else {}
        if name == "ask_user" and result.get("ok"):
            return False
        if name == "finish" and result.get("ok") and result.get("finished"):
            return True
    return any(
        isinstance(ev, dict) and str(ev.get("name") or "") not in {"ask_user"}
        for ev in events
    )


def should_write_memory(
    *,
    onboarding: bool,
    user_message: str,
    tool_events: list[dict[str, Any]] | None,
    cancelled: bool = False,
    error: bool = False,
) -> bool:
    """Memory writes need a durable user signal — not every finished task."""
    if not should_reflect(
        onboarding=onboarding,
        tool_events=tool_events,
        cancelled=cancelled,
        error=error,
    ):
        return False
    return user_has_durable_signal(user_message)


def collect_untrusted_blobs(tool_events: list[dict[str, Any]] | None) -> list[str]:
    blobs: list[str] = []
    for ev in tool_events or []:
        if not isinstance(ev, dict):
            continue
        if str(ev.get("name") or "") not in _UNTRUSTED_TOOLS:
            continue
        result = ev.get("result")
        try:
            blobs.append(json.dumps(result, ensure_ascii=False))
        except (TypeError, ValueError):
            blobs.append(str(result))
    return blobs


def overlaps_untrusted(text: str, blobs: list[str]) -> bool:
    sample = (text or "").strip()
    if len(sample) < _OVERLAP_MIN:
        return False
    windows = [sample]
    if len(sample) > 40:
        windows.extend(
            sample[i : i + 40]
            for i in range(0, min(len(sample) - 39, 200), 20)
        )
    for blob in blobs:
        if not blob:
            continue
        for win in windows:
            if len(win) >= _OVERLAP_MIN and win in blob:
                return True
    return False


def _tool_trace_lines(tool_events: list[dict[str, Any]] | None) -> list[str]:
    lines: list[str] = []
    for ev in tool_events or []:
        if not isinstance(ev, dict):
            continue
        name = str(ev.get("name") or "")
        args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
        if name == "read_skill":
            lines.append(f"read_skill:{args.get('skill_id', '')}")
        elif name == "run_skill_script":
            lines.append(
                f"run_skill_script:{args.get('skill_id', '')}/{args.get('script', '')}"
            )
        elif name == "run_shared_script":
            lines.append(f"run_shared_script:{args.get('name', '')}")
        elif name in _TRACE_TOOLS:
            lines.append(name)
        elif name == "run_workspace_script":
            lines.append("run_workspace_script")
        else:
            lines.append(name)
    return lines


def build_reflect_user_payload(
    *,
    user_message: str,
    final_text: str = "",
    tool_events: list[dict[str, Any]] | None = None,
) -> str:
    """Payload for the memory LLM — user speech only (Hermes: facts about the person)."""
    del final_text, tool_events  # kept for call-site compatibility; must not feed skill echo
    user = strip_attachment_footer(user_message)
    return (
        "使用者原话（只从此提炼跨任务仍成立的偏好/纠正；无则返回空）：\n"
        + user[:800]
    )


def _parse_reflect_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {"habits": [], "recent": []}
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {"habits": [], "recent": []}
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {"habits": [], "recent": []}
    if not isinstance(data, dict):
        return {"habits": [], "recent": []}
    return data


def _looks_skillish(text: str) -> bool:
    sample = (text or "").strip()
    if not sample:
        return False
    if _SKILLISH_RE.search(sample):
        return True
    # Imperatives aimed at the agent, not facts about the user.
    if re.match(r"^(必须|禁止|务必|应当|应该|先|不要让助手)", sample):
        return True
    return False


def _filter_reflection(
    data: dict[str, Any], blobs: list[str]
) -> tuple[list[dict[str, str]], list[str]]:
    habits_out: list[dict[str, str]] = []
    for item in data.get("habits") or []:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic") or "").strip()
        text = str(item.get("text") or "").strip()
        if not topic or not text:
            continue
        if overlaps_untrusted(topic, blobs) or overlaps_untrusted(text, blobs):
            continue
        if _looks_skillish(topic) or _looks_skillish(text):
            continue
        habits_out.append({"topic": topic, "text": text})
        if len(habits_out) >= 2:
            break

    recent_out: list[str] = []
    for item in data.get("recent") or []:
        text = str(item).strip() if not isinstance(item, dict) else str(
            item.get("text") or ""
        ).strip()
        if not text or overlaps_untrusted(text, blobs) or _looks_skillish(text):
            continue
        # Skip completed-work diary lines ("做完了…") — Hermes skips these too.
        if re.search(r"(做完|已完成|刚做了|本轮|这次任务)", text):
            continue
        recent_out.append(text)
        if len(recent_out) >= 1:
            break
    return habits_out, recent_out


def flow_signature(
    *,
    user_message: str,
    tool_events: list[dict[str, Any]] | None,
) -> str | None:
    """Stable signature for crystallizing repeated flows. None if not eligible."""
    events = tool_events or []
    if any(
        isinstance(ev, dict) and str(ev.get("name") or "") == "run_workspace_script"
        for ev in events
    ):
        return None
    steps: list[str] = []
    deliverable_suffixes: list[str] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name = str(ev.get("name") or "")
        args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
        result = ev.get("result") if isinstance(ev.get("result"), dict) else {}
        if name not in _TRACE_TOOLS:
            continue
        if name == "read_skill":
            steps.append(f"read_skill:{args.get('skill_id', '')}")
        elif name == "run_skill_script":
            steps.append(
                f"run_skill_script:{args.get('skill_id', '')}/{args.get('script', '')}"
            )
        elif name == "run_shared_script":
            steps.append(f"run_shared_script:{args.get('name', '')}")
        elif name == "finish":
            steps.append("finish")
            dels = args.get("deliverables") or result.get("deliverables") or []
            if isinstance(dels, list):
                for d in dels:
                    suf = Path(str(d)).suffix.lower()
                    if suf:
                        deliverable_suffixes.append(suf)
        else:
            steps.append(name)
    if "finish" not in steps:
        return None
    skill_ops = [s for s in steps if s.startswith(("read_skill:", "run_skill_script:"))]
    shared_ops = [s for s in steps if s.startswith("run_shared_script:")]
    if not skill_ops and not shared_ops:
        return None
    # Only replaying one existing skill's own script — no new flow to crystallize.
    if skill_ops and not shared_ops and all(
        s.startswith(("read_skill:", "run_skill_script:"))
        or s
        in {
            "finish",
            "plan_get",
            "plan_create",
            "plan_update_step",
            "plan_set_status",
            "plan_set_approval",
        }
        for s in steps
    ):
        skill_ids: set[str] = set()
        for s in skill_ops:
            if s.startswith("read_skill:"):
                skill_ids.add(s.split(":", 1)[1])
            elif s.startswith("run_skill_script:"):
                skill_ids.add(s.split(":", 1)[1].split("/", 1)[0])
        if len(skill_ids) <= 1:
            return None

    head = strip_attachment_footer(user_message)[:40]
    payload = "|".join(steps) + "#" + ",".join(sorted(set(deliverable_suffixes))) + "#" + head
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _bump_version(version: str) -> str:
    parts = (version or "1.0.0").split(".")
    nums: list[int] = []
    for p in parts[:3]:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    nums[2] += 1
    return f"{nums[0]}.{nums[1]}.{nums[2]}"


def _slug_from_user(user_message: str) -> str:
    head = strip_attachment_footer(user_message)
    digest = hashlib.sha256(head.encode("utf-8")).hexdigest()[:8]
    return f"learned-flow-{digest}"


def build_skill_md(
    *,
    skill_id: str,
    display_name: str,
    version: str,
    user_message: str,
    tool_events: list[dict[str, Any]] | None,
) -> str:
    steps = _tool_trace_lines(tool_events)
    body_steps = "\n".join(f"{i}. `{s}`" for i, s in enumerate(steps, 1) if s != "finish")
    if not body_steps:
        body_steps = "1. 按使用者说明办事，优先复用已启用技能与共享脚本。"
    desc = strip_attachment_footer(user_message).replace("\n", " ").replace('"', "")
    if len(desc) > 58:
        desc = desc[:57] + "…"
    if not desc:
        desc = "按已固化的本机办事步骤完成同类任务"
    safe_display = display_name.replace('"', "").replace("\n", " ") or "习惯流程"
    return (
        "---\n"
        f"name: {skill_id}\n"
        f'display_name: "{safe_display}"\n'
        f'description: "{desc}"\n'
        f"version: {version}\n"
        "tier: light\n"
        "permissions:\n"
        "  - workspace_read\n"
        "  - workspace_write\n"
        "---\n\n"
        f"# {safe_display}\n\n"
        "本技能由记忆根据重复流程自动固化，仅含说明，不含新脚本。\n\n"
        "## 触发\n\n"
        f"使用者意图接近：「{strip_attachment_footer(user_message)[:80]}」\n\n"
        "## 步骤\n\n"
        f"{body_steps}\n\n"
        "## 硬规则\n\n"
        "- 必须先 `read_skill` 读取将要调用的已有技能正文，再按其步骤执行。\n"
        "- 只使用已安装技能脚本与共享脚本，禁止新建工作区补丁脚本。\n"
        "- 交付物写入 `工作成果/`。\n"
    )


def try_crystallize(
    store: MemoryStore,
    registry: SkillRegistry,
    *,
    signature: str,
    user_message: str,
    tool_events: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    count = store.record_trace(signature)
    if count < 2:
        return None

    existing = store.get_crystallized(signature)
    if existing:
        skill_id = str(existing.get("skill_id") or "")
        old_version = str(existing.get("version") or "1.0.0")
        version = _bump_version(old_version)
        display_name = str(existing.get("display_name") or skill_id)
    else:
        skill_id = _slug_from_user(user_message)
        old_version = ""
        version = "1.0.0"
        display_name = "习惯流程"
        short = strip_attachment_footer(user_message)
        if short:
            display_name = short[:10]

    if registry.is_bundled_id(skill_id):
        return None

    # Avoid colliding with an unrelated installed skill id.
    for meta in registry.scan():
        if meta.id == skill_id and store.get_crystallized(signature) is None:
            skill_id = f"{skill_id}-{signature[:6]}"
            break

    text = build_skill_md(
        skill_id=skill_id,
        display_name=display_name,
        version=version,
        user_message=user_message,
        tool_events=tool_events,
    )
    validation = validate_skill_text(text, skill_id)
    if not validation.get("ok"):
        logger.info("crystallize validation failed: %s", validation.get("errors"))
        return None

    dest = registry.skills_dir / skill_id
    if dest.is_dir():
        label = old_version or version
        backup = store.backup_root / f"{skill_id}-{label}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(dest, backup)

    try:
        with tempfile.TemporaryDirectory(prefix="oa-mem-skill-") as tmp:
            md_path = Path(tmp) / "SKILL.md"
            md_path.write_text(text, encoding="utf-8")
            meta = registry.install_md(md_path, force_overwrite=True)
            registry.set_enabled(meta.id, True)
            meta.enabled = True
    except SkillError as e:
        logger.info("crystallize install failed: %s", e)
        return None

    store.set_crystallized(
        signature,
        skill_id=meta.id,
        display_name=meta.ui_name,
        version=meta.version,
    )
    return {
        "skill_id": meta.id,
        "display_name": meta.ui_name,
        "version": meta.version,
    }


def run_reflection(
    *,
    gateway: Any,
    store: MemoryStore,
    registry: SkillRegistry | None,
    user_message: str,
    final_text: str,
    tool_events: list[dict[str, Any]] | None,
    onboarding: bool,
    cancelled: bool = False,
    error: bool = False,
) -> dict[str, Any] | None:
    """Best-effort post-turn reflection. Never raises to callers."""
    try:
        if not should_reflect(
            onboarding=onboarding,
            tool_events=tool_events,
            cancelled=cancelled,
            error=error,
        ):
            return None

        applied: dict[str, Any] = {
            "changed": False,
            "topics": [],
            "recent_line": "",
            "snapshot": store.snapshot(),
        }
        if should_write_memory(
            onboarding=onboarding,
            user_message=user_message,
            tool_events=tool_events,
            cancelled=cancelled,
            error=error,
        ):
            blobs = collect_untrusted_blobs(tool_events)
            payload = build_reflect_user_payload(user_message=user_message)
            response = gateway.chat(
                [
                    {"role": "system", "content": _REFLECT_SYSTEM},
                    {"role": "user", "content": payload},
                ],
                tools=None,
            )
            content = ""
            try:
                content = str(response.choices[0].message.content or "")
            except (AttributeError, IndexError, TypeError):
                content = ""
            habits, _recent = _filter_reflection(_parse_reflect_json(content), blobs)
            applied = store.apply_reflection(habits, [])

        crystallized = None
        sig = flow_signature(user_message=user_message, tool_events=tool_events)
        if sig and registry is not None:
            crystallized = try_crystallize(
                store,
                registry,
                signature=sig,
                user_message=user_message,
                tool_events=tool_events,
            )

        if not applied.get("changed") and not crystallized:
            return None

        out: dict[str, Any] = {
            "topics": list(applied.get("topics") or []),
            "recent_line": str(applied.get("recent_line") or ""),
            "can_undo": store.can_undo(),
            "changed": bool(applied.get("changed")),
        }
        if crystallized:
            out["skill_id"] = crystallized["skill_id"]
            out["display_name"] = crystallized["display_name"]
        return out
    except Exception:
        logger.warning("memory reflection failed", exc_info=True)
        return None
