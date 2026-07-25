#!/usr/bin/env python3
"""Check a Skill draft against the packaging rules before installing it.

Usage:
    python validate.py <草稿目录>           # 如 .office-agent/work/skill-draft/weekly-digest
    python validate.py --installed <id>     # 校验已安装的技能

有 error 时退出码 1；只有 warning 时退出码 0。
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path
from typing import Any

# The frozen sidecar runs scripts through runpy.run_path, which leaves sys.path
# untouched, so sibling modules are not importable without this.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_common import (  # noqa: E402
    SEMVER_RE,
    SKILL_ID_RE,
    app_data_dir,
    installed_skills,
    read_skill_md,
    skills_dir,
    text_files,
)

ALLOWED_TIERS = {"light", "heavy"}
ALLOWED_PERMISSIONS = {"workspace_read", "workspace_write", "run_python"}
REQUIRED_FIELDS = ("name", "display_name", "description", "version", "tier")
MAX_DESCRIPTION_CHARS = 60
MAX_BODY_CHARS = 8000
MAX_FILE_BYTES = 2 * 1024 * 1024
SMOKE_SCRIPT_NAME = "smoke_pipeline.py"
EXPECTED_SECTIONS = {
    "何时": "何时用 / 何时不用",
    "步数预算": "步数预算",
    "变更记录": "变更记录",
}
FORBIDDEN_IMPORTS = {"requests", "urllib.request", "urllib3", "httpx", "socket"}
REFERENCE_PATH_RE = re.compile(r"\b((?:scripts|references|templates)/[\w./-]+)")
FENCED_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
PLACEHOLDER_RE = re.compile(r"\{\{.*?\}\}", re.DOTALL)
# Python 3.12+ tokenizes f-string text as FSTRING_MIDDLE rather than STRING.
LITERAL_TOKENS = {tokenize.COMMENT, tokenize.STRING} | {
    t for t in [getattr(tokenize, "FSTRING_MIDDLE", None)] if t is not None
}


def _strip_markdown_code(text: str) -> str:
    """Blank out fenced blocks and inline code spans.

    A leftover template placeholder shows up in prose; prose that merely *talks*
    about placeholders wraps them in code formatting.
    """
    without_fences = FENCED_BLOCK_RE.sub("", text)
    return INLINE_CODE_RE.sub("", without_fences)


def _strip_python_comments_and_strings(source: str) -> str:
    """Blank out comments and string literals, keeping offsets intact."""
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    chars = list(source)

    def blank(start: tuple[int, int], end: tuple[int, int]) -> None:
        a = starts[start[0] - 1] + start[1]
        b = starts[end[0] - 1] + end[1]
        for i in range(a, min(b, len(chars))):
            if chars[i] != "\n":
                chars[i] = " "

    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in LITERAL_TOKENS:
                blank(tok.start, tok.end)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return source
    return "".join(chars)


def _jaccard(a: str, b: str) -> float:
    """Character-bigram overlap; good enough to spot near-duplicate descriptions."""
    grams_a = {a[i : i + 2] for i in range(len(a) - 1)}
    grams_b = {b[i : i + 2] for i in range(len(b) - 1)}
    if not grams_a or not grams_b:
        return 0.0
    return len(grams_a & grams_b) / len(grams_a | grams_b)


def _check_frontmatter(data: dict[str, Any], skill_id: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for field in REQUIRED_FIELDS:
        if not str(data.get(field) or "").strip():
            errors.append(f"frontmatter 缺少必填字段 {field}")

    if not SKILL_ID_RE.match(skill_id):
        errors.append(f"目录名 {skill_id!r} 不合法：需匹配 ^[a-z0-9][a-z0-9-]{{1,39}}$（小写 ASCII + 连字符）")

    name = str(data.get("name") or "").strip()
    if name and name != skill_id:
        errors.append(f"frontmatter name={name!r} 与目录名 {skill_id!r} 不一致；技能 id 取自目录名，两者必须相同")

    version = str(data.get("version") or "").strip()
    if version and not SEMVER_RE.match(version):
        errors.append(f"version={version!r} 不是 semver（如 1.0.0）")

    tier = str(data.get("tier") or "").strip()
    if tier and tier not in ALLOWED_TIERS:
        errors.append(f"tier={tier!r} 非法，只能是 light 或 heavy")
    if tier == "heavy" and data.get("min_ram_gb") is None:
        errors.append("tier=heavy 必须同时声明 min_ram_gb")

    perms = data.get("permissions") or []
    if not isinstance(perms, list):
        errors.append("permissions 必须是列表")
    else:
        for p in perms:
            if str(p) not in ALLOWED_PERMISSIONS:
                errors.append(f"permissions 含未知项 {p!r}，可选：{sorted(ALLOWED_PERMISSIONS)}")

    description = str(data.get("description") or "").strip()
    if len(description) > MAX_DESCRIPTION_CHARS:
        warnings.append(
            f"description {len(description)} 字，超过 {MAX_DESCRIPTION_CHARS} 字；"
            "它每轮对话都会注入上下文，细节应放正文"
        )
    if not data.get("trigger_phrases"):
        warnings.append("建议补 trigger_phrases，便于日后回看该技能应被什么话触发")

    shared = data.get("shared_scripts") or []
    if isinstance(shared, list):
        shared_dir = app_data_dir() / "shared-scripts"
        for s in shared:
            if not (shared_dir / f"{s}.py").is_file():
                warnings.append(f"shared_scripts 声明的 {s} 在 {shared_dir} 下不存在")

    return errors, warnings


def _check_body(body: str, skill_dir: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    leftover = PLACEHOLDER_RE.findall(_strip_markdown_code(body))
    if leftover:
        errors.append(f"正文仍有未填写的占位符，模板没写完：{'、'.join(leftover[:5])}")

    for rel in sorted(set(_referenced_files(body))):
        if not (skill_dir / rel).exists():
            errors.append(f"正文引用了不存在的文件：{rel}")

    if len(body) > MAX_BODY_CHARS:
        warnings.append(
            f"正文 {len(body)} 字符，超过 {MAX_BODY_CHARS}；read_skill 会一次性载入，"
            "建议把细则拆到 references/"
        )
    for keyword, label in EXPECTED_SECTIONS.items():
        if keyword not in body:
            warnings.append(f"正文缺少「{label}」章节")
    if "交付" not in body and "产出" not in body:
        warnings.append("正文没说清交付物是什么")

    return errors, warnings


def _referenced_files(body: str) -> list[str]:
    """Pull scripts/*.py, references/*.md and templates/* paths out of the prose."""
    return [m.group(1).rstrip(".,;:）)") for m in REFERENCE_PATH_RE.finditer(body)]


def _check_scripts(skill_dir: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    scripts = sorted((skill_dir / "scripts").glob("*.py")) if (skill_dir / "scripts").is_dir() else []

    for script in scripts:
        rel = script.relative_to(skill_dir).as_posix()
        source = script.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=str(script))
        except SyntaxError as e:
            errors.append(f"{rel} 语法错误：第 {e.lineno} 行 {e.msg}")
            continue

        errors.extend(f"{rel}: {m}" for m in _scan_forbidden(tree))
        leftover = PLACEHOLDER_RE.findall(_strip_python_comments_and_strings(source))
        if leftover:
            errors.append(f"{rel} 仍有未填写的占位符：{'、'.join(leftover[:5])}")

        # Helper modules and the dev-only smoke test are not Agent entry points,
        # so the CLI-shape rules don't apply to them.
        if script.name == SMOKE_SCRIPT_NAME or not _has_main_guard(tree):
            continue
        if "argparse" not in source:
            warnings.append(f"{rel} 没用 argparse，参数解析不稳")
        if "json.dumps" not in source:
            warnings.append(f"{rel} 没有 stdout 打 JSON 摘要，Agent 难判断结果")
        if not _has_main_function(tree):
            warnings.append(f"{rel} 缺少 main(argv) -> int 入口")

    return errors, warnings


def _scan_forbidden(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {n.split(".")[0] for n in FORBIDDEN_IMPORTS}:
                    found.append(f"禁止联网，不要 import {alias.name}")
                if alias.name == "office_agent" or alias.name.startswith("office_agent."):
                    found.append("不要 import office_agent，脚本是独立进程")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in {n.split(".")[0] for n in FORBIDDEN_IMPORTS}:
                found.append(f"禁止联网，不要 from {node.module} import ...")
            if root == "office_agent":
                found.append("不要 import office_agent，脚本是独立进程")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                found.append("禁止 os.system，Runtime 不允许执行 shell")
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value:
                    found.append("禁止 subprocess(..., shell=True)")
    return sorted(set(found))


def _has_main_function(tree: ast.AST) -> bool:
    return any(isinstance(n, ast.FunctionDef) and n.name == "main" for n in ast.walk(tree))


def _has_main_guard(tree: ast.AST) -> bool:
    return any(
        isinstance(n, ast.If)
        and isinstance(n.test, ast.Compare)
        and isinstance(n.test.left, ast.Name)
        and n.test.left.id == "__name__"
        for n in ast.walk(tree)
    )


def _check_overlap(skill_id: str, description: str) -> list[str]:
    warnings: list[str] = []
    for other_id, other in installed_skills():
        if other_id == skill_id:
            continue
        other_desc = str(other.get("description") or "").strip()
        if other_desc and _jaccard(description, other_desc) >= 0.6:
            warnings.append(
                f"description 与已安装技能 {other_id}（{other.get('display_name') or other_id}）"
                "高度重合，考虑迭代那个技能而不是新建"
            )
    return warnings


def _check_size(skill_dir: Path) -> list[str]:
    warnings: list[str] = []
    for p in skill_dir.rglob("*"):
        if p.is_file() and p.stat().st_size > MAX_FILE_BYTES:
            mb = p.stat().st_size / 1024 / 1024
            warnings.append(f"{p.relative_to(skill_dir).as_posix()} 有 {mb:.1f}MB，分享包会很大")
    return warnings


def validate(skill_dir: Path) -> dict[str, Any]:
    skill_id = skill_dir.name
    result: dict[str, Any] = {
        "ok": False,
        "skill_dir": str(skill_dir),
        "skill": {"id": skill_id},
        "errors": [],
        "warnings": [],
        "files": [],
    }
    if not skill_dir.is_dir():
        result["errors"].append(f"目录不存在：{skill_dir}")
        return result

    result["files"] = text_files(skill_dir)
    try:
        data, body = read_skill_md(skill_dir)
    except ValueError as e:
        result["errors"].append(str(e))
        return result

    result["skill"] = {
        "id": skill_id,
        "name": str(data.get("name") or ""),
        "display_name": str(data.get("display_name") or ""),
        "description": str(data.get("description") or ""),
        "version": str(data.get("version") or ""),
        "tier": str(data.get("tier") or ""),
    }

    errors, warnings = _check_frontmatter(data, skill_id)
    body_errors, body_warnings = _check_body(body, skill_dir)
    script_errors, script_warnings = _check_scripts(skill_dir)

    result["errors"] = errors + body_errors + script_errors
    result["warnings"] = (
        warnings
        + body_warnings
        + script_warnings
        + _check_overlap(skill_id, result["skill"]["description"])
        + _check_size(skill_dir)
    )
    result["ok"] = not result["errors"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 Skill 包是否符合规范")
    parser.add_argument("target", nargs="?", help="草稿目录（相对工作区根）")
    parser.add_argument("--installed", metavar="SKILL_ID", help="改为校验已安装的技能")
    args = parser.parse_args(argv)

    if args.installed:
        skill_dir = skills_dir() / args.installed
    elif args.target:
        skill_dir = Path(args.target)
    else:
        print("ERROR: 需要给出草稿目录，或用 --installed <id>", file=sys.stderr)
        return 2

    result = validate(skill_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        print(f"ERROR: {len(result['errors'])} 项必须修复后才能安装", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
