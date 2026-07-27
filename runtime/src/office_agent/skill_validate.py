"""Lightweight Skill package validation for Runtime install gating.

Ported from skill-builder's core error rules; does not import or require that Skill.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import yaml

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

ALLOWED_TIERS = frozenset({"light", "heavy"})
ALLOWED_PERMISSIONS = frozenset({"workspace_read", "workspace_write", "run_python"})
REQUIRED_FIELDS = ("name", "description", "version", "tier")
MAX_DESCRIPTION_CHARS = 60
FORBIDDEN_IMPORT_ROOTS = frozenset({"requests", "httpx", "socket"})
EXPECTED_SECTION_KEYWORDS = ("何时", "步数预算")


def _empty_result() -> dict[str, Any]:
    return {"ok": False, "errors": [], "warnings": []}


def _is_safe_id(value: str) -> bool:
    if not value or ".." in value or "/" in value or "\\" in value:
        return False
    return bool(SAFE_ID_RE.match(value))


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("SKILL.md missing YAML frontmatter")
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        raise ValueError(f"SKILL.md YAML frontmatter unparseable: {e}") from e
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("SKILL.md frontmatter must be a mapping")
    return data, m.group(2)


def _check_frontmatter(
    data: dict[str, Any], skill_id: str
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for field in REQUIRED_FIELDS:
        if not str(data.get(field) or "").strip():
            errors.append(f"frontmatter missing required field: {field}")

    if not str(data.get("display_name") or "").strip():
        warnings.append("frontmatter missing display_name")

    if not _is_safe_id(skill_id):
        errors.append(
            f"skill id {skill_id!r} is unsafe (no path separators / '..'; "
            "use letters, digits, '_' or '-')"
        )

    name = str(data.get("name") or "").strip()
    if name and not _is_safe_id(name):
        errors.append(
            f"name={name!r} is unsafe (no path separators / '..'; "
            "use letters, digits, '_' or '-')"
        )

    tier = str(data.get("tier") or "").strip()
    if tier and tier not in ALLOWED_TIERS:
        errors.append(f"tier={tier!r} invalid; must be light or heavy")

    perms = data.get("permissions") or []
    if perms is None:
        perms = []
    if not isinstance(perms, list):
        errors.append("permissions must be a list")
    else:
        for p in perms:
            if str(p) not in ALLOWED_PERMISSIONS:
                errors.append(
                    f"permissions contains unknown entry {p!r}; "
                    f"allowed: {sorted(ALLOWED_PERMISSIONS)}"
                )

    description = str(data.get("description") or "").strip()
    if len(description) > MAX_DESCRIPTION_CHARS:
        warnings.append(
            f"description is {len(description)} chars "
            f"(>{MAX_DESCRIPTION_CHARS}); keep it short for context injection"
        )

    return errors, warnings


def _check_body(body: str) -> list[str]:
    warnings: list[str] = []
    for keyword in EXPECTED_SECTION_KEYWORDS:
        if keyword not in body:
            warnings.append(f"body missing optional section keyword: {keyword}")
    return warnings


def _scan_forbidden_imports(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    found.append(f"forbidden network import: {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in FORBIDDEN_IMPORT_ROOTS:
                found.append(f"forbidden network import: {node.module}")
    return sorted(set(found))


def _check_scripts(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        return errors
    for script in sorted(scripts_dir.glob("*.py")):
        rel = script.relative_to(skill_dir).as_posix()
        source = script.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=str(script))
        except SyntaxError as e:
            errors.append(f"{rel} syntax error: line {e.lineno} {e.msg}")
            continue
        errors.extend(f"{rel}: {msg}" for msg in _scan_forbidden_imports(tree))
    return errors


def validate_skill_dir(skill_dir: Path) -> dict[str, Any]:
    """Validate a Skill directory. Returns {ok, errors, warnings}."""
    result = _empty_result()
    skill_dir = Path(skill_dir)
    if not skill_dir.is_dir():
        result["errors"].append(f"not a directory: {skill_dir}")
        return result

    md = skill_dir / "SKILL.md"
    if not md.is_file():
        result["errors"].append("SKILL.md not found")
        return result

    try:
        data, body = _parse_frontmatter(md.read_text(encoding="utf-8"))
    except ValueError as e:
        result["errors"].append(str(e))
        return result

    # Prefer frontmatter name so temp extract dirs (e.g. _tmp_extract) are not
    # treated as the skill id. Directory name is only a fallback.
    frontmatter_name = str(data.get("name") or "").strip()
    skill_id = frontmatter_name or skill_dir.name
    fm_errors, fm_warnings = _check_frontmatter(data, skill_id)
    result["errors"] = fm_errors + _check_scripts(skill_dir)
    result["warnings"] = fm_warnings + _check_body(body)
    result["ok"] = not result["errors"]
    return result


def validate_skill_text(text: str, skill_id: str) -> dict[str, Any]:
    """Validate a standalone SKILL.md body (no scripts tree)."""
    result = _empty_result()
    try:
        data, body = _parse_frontmatter(text)
    except ValueError as e:
        result["errors"].append(str(e))
        return result
    fm_errors, fm_warnings = _check_frontmatter(data, skill_id)
    result["errors"] = fm_errors
    result["warnings"] = fm_warnings + _check_body(body)
    result["ok"] = not result["errors"]
    return result


def propose_auto_fixes(text: str, skill_id: str) -> tuple[str, list[str]]:
    """Fill a few missing frontmatter fields. Returns (new_text, human-readable fixes).

    Only patches safe, inferable gaps: version, tier, display_name.
    Does not touch name/description/permissions/scripts.
    """
    try:
        data, body = _parse_frontmatter(text)
    except ValueError:
        return text, []

    fixes: list[str] = []
    if not str(data.get("version") or "").strip():
        data["version"] = "0.1.0"
        fixes.append("补全 version=0.1.0")
    if not str(data.get("tier") or "").strip():
        data["tier"] = "light"
        fixes.append("补全 tier=light")
    if not str(data.get("display_name") or "").strip():
        name = str(data.get("name") or skill_id).strip() or skill_id
        data["display_name"] = name
        fixes.append(f"补全 display_name={name}")

    if not fixes:
        return text, []

    dumped = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    return f"---\n{dumped}---\n{body}", fixes


def _validation_after_frontmatter_fix(
    skill_id: str,
    fixed_text: str,
    *,
    skill_dir: Path | None = None,
) -> dict[str, Any]:
    result = _empty_result()
    try:
        data, body = _parse_frontmatter(fixed_text)
    except ValueError as e:
        result["errors"].append(str(e))
        return result
    fm_errors, fm_warnings = _check_frontmatter(data, skill_id)
    script_errors = _check_scripts(skill_dir) if skill_dir is not None else []
    result["errors"] = fm_errors + script_errors
    result["warnings"] = fm_warnings + _check_body(body)
    result["ok"] = not result["errors"]
    return result


def enrich_validation_with_autofix(
    validation: dict[str, Any],
    *,
    text: str,
    skill_id: str,
    skill_dir: Path | None = None,
) -> dict[str, Any]:
    """Attach auto_fixes / can_install_with_fixes to a validation payload."""
    fixed_text, fixes = propose_auto_fixes(text, skill_id)
    if not fixes:
        return {
            **validation,
            "auto_fixes": [],
            "can_install_with_fixes": bool(validation.get("ok")),
        }
    after = _validation_after_frontmatter_fix(
        skill_id, fixed_text, skill_dir=skill_dir
    )
    return {
        **validation,
        "auto_fixes": fixes,
        "can_install_with_fixes": bool(after.get("ok")),
        "validation_after_fixes": {
            "ok": bool(after.get("ok")),
            "errors": list(after.get("errors") or []),
            "warnings": list(after.get("warnings") or []),
        },
    }
