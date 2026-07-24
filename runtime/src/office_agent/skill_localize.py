# Translate Skill UI fields (display_name / description) via ModelGateway
# and write them back into the installed SKILL.md frontmatter.
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from office_agent.skills import FRONTMATTER_RE, SkillError, SkillMeta, parse_skill_md

logger = logging.getLogger(__name__)

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(text or ""))


def needs_zh_display(meta: SkillMeta) -> bool:
    """True when UI name or description still lacks Chinese characters."""
    if not has_cjk(meta.display_name):
        return True
    if meta.description.strip() and not has_cjk(meta.description):
        return True
    return False


def apply_zh_frontmatter(
    skill_md: Path,
    *,
    display_name: str,
    description: str | None = None,
) -> None:
    """Update display_name (and optionally description) in SKILL.md; keep body."""
    text = skill_md.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise SkillError("SKILL.md missing YAML frontmatter")
    data = yaml.safe_load(m.group(1)) or {}
    if not isinstance(data, dict):
        raise SkillError("SKILL.md frontmatter must be a mapping")
    data["display_name"] = display_name.strip()
    if description is not None:
        data["description"] = description.strip()
    body = m.group(2)
    dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False).strip()
    skill_md.write_text(f"---\n{dumped}\n---\n{body}", encoding="utf-8")


def _extract_json_object(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model response has no JSON object")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("model JSON must be an object")
    return data


def _skill_md_path(meta: SkillMeta) -> Path:
    if meta.path is None:
        raise SkillError("skill path missing; cannot localize")
    md = meta.path / "SKILL.md"
    if not md.is_file():
        raise SkillError(f"SKILL.md not found: {md}")
    return md


def localize_installed_skill(meta: SkillMeta, gateway: Any) -> SkillMeta:
    """Call the model, write Chinese UI fields into installed SKILL.md, re-parse."""
    md = _skill_md_path(meta)
    want_desc = bool(meta.description.strip()) and not has_cjk(meta.description)
    want_name = not has_cjk(meta.display_name)

    user_payload = {
        "id": meta.id,
        "name": meta.name,
        "display_name": meta.display_name or None,
        "description": meta.description or None,
        "need_display_name": want_name,
        "need_description": want_desc,
    }
    messages = [
        {
            "role": "system",
            "content": (
                "你是办公软件产品文案助手。将 Skill 的界面展示字段译成简体中文。"
                "只输出一个 JSON 对象，不要 Markdown，不要解释。"
                '格式：{"display_name":"...","description":"..."}。'
                "display_name：2–12 个汉字的产品短名，不要英文 id。"
                "description：一句中文说明，保留原意。"
                "不要修改 id/name；若某字段 need_*=false，仍可原样返回该字段。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False),
        },
    ]
    resp = gateway.chat(messages)
    content = ""
    try:
        content = resp.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError) as e:
        raise ValueError(f"unexpected gateway response: {e}") from e

    data = _extract_json_object(content)
    display_name = str(data.get("display_name") or "").strip()
    description = str(data.get("description") or "").strip()

    if want_name:
        if not display_name or not has_cjk(display_name):
            raise ValueError("model did not return a Chinese display_name")
    else:
        display_name = meta.display_name

    new_description: str | None = None
    if want_desc:
        if not description or not has_cjk(description):
            raise ValueError("model did not return a Chinese description")
        new_description = description

    apply_zh_frontmatter(md, display_name=display_name, description=new_description)
    updated = parse_skill_md(md.read_text(encoding="utf-8"), meta.path)
    updated.enabled = meta.enabled
    return updated


def try_localize_installed_skill(meta: SkillMeta, gateway_factory: Any, config: Any) -> SkillMeta:
    """Soft-fail wrapper: on any error, return the original meta unchanged."""
    if not needs_zh_display(meta):
        return meta
    try:
        gateway = gateway_factory(config)
        return localize_installed_skill(meta, gateway)
    except Exception as e:  # noqa: BLE001 — install/list must not fail on locale
        logger.warning("skill zh localize skipped for %s: %s", meta.id, e)
        return meta
