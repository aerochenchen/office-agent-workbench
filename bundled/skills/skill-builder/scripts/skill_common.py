#!/usr/bin/env python3
"""Shared helpers for the skill-builder scripts (not called directly by the Agent)."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
SKILL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

DRAFT_ROOT = Path(".office-agent") / "work" / "skill-draft"
COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".git")
TEXT_SUFFIXES = frozenset({".md", ".txt", ".json", ".py", ".yaml", ".yml", ".csv", ".tmpl"})


def app_data_dir() -> Path:
    """Mirror office_agent.paths.app_data_dir without importing the Runtime."""
    override = os.environ.get("OFFICE_AGENT_DATA")
    return Path(override).expanduser() if override else Path.home() / ".office-agent"


def skills_dir() -> Path:
    return app_data_dir() / "skills"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter mapping, body). Raises ValueError on malformed input."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("SKILL.md 缺少 YAML frontmatter（文件必须以 --- 开头）")
    try:
        import yaml
    except ImportError as e:  # pragma: no cover - pyyaml ships with the Runtime
        raise ValueError("解析 frontmatter 需要 pyyaml") from e
    data = yaml.safe_load(m.group(1))
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("frontmatter 必须是键值映射")
    return data, m.group(2)


def read_skill_md(skill_dir: Path) -> tuple[dict[str, Any], str]:
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        raise ValueError(f"缺少 SKILL.md: {md}")
    return parse_frontmatter(md.read_text(encoding="utf-8"))


def text_files(skill_dir: Path, *, limit: int = 60) -> list[str]:
    """Text files worth showing the Agent; fixtures are collapsed to a count."""
    out: list[str] = []
    fixtures = 0
    for p in sorted(skill_dir.rglob("*")):
        if "__pycache__" in p.parts or not p.is_file():
            continue
        rel = p.relative_to(skill_dir)
        if rel.parts and rel.parts[0] == "fixtures":
            fixtures += 1
            continue
        if p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        out.append(rel.as_posix())
        if len(out) >= limit:
            out.append("…（已截断）")
            break
    if fixtures:
        out.append(f"fixtures/ 共 {fixtures} 个文件")
    return out


def installed_skills() -> list[tuple[str, dict[str, Any]]]:
    """(skill_id, frontmatter) for every installed skill that parses."""
    root = skills_dir()
    if not root.is_dir():
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not (d / "SKILL.md").is_file():
            continue
        try:
            data, _ = read_skill_md(d)
        except ValueError:
            continue
        out.append((d.name, data))
    return out
