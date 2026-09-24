#!/usr/bin/env python3
"""Install a validated Skill draft into the app data directory.

Usage:
    python install.py <草稿目录> [--no-enable] [--force]

先跑 validate；有 error 一律拒装。--force 只用于覆盖已安装的同名技能。
已存在同名技能会先备份到 ~/.office-agent/skill-backups/。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

# The frozen sidecar runs scripts through runpy.run_path, which leaves sys.path
# untouched, so sibling modules are not importable without this.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_common import COPY_IGNORE, app_data_dir, read_skill_md, skills_dir  # noqa: E402
from validate import validate  # noqa: E402

# Kept outside skills/ so SkillRegistry.scan() never picks backups up as skills.
BACKUP_REL = "skill-backups"


def _set_enabled(skill_id: str, enabled: bool) -> None:
    state_path = app_data_dir() / "skills_state.json"
    state: dict[str, Any] = {"enabled": {}}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {"enabled": {}}
    state.setdefault("enabled", {})[skill_id] = enabled
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _backup(dest: Path, version: str) -> str | None:
    if not dest.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = app_data_dir() / BACKUP_REL / f"{dest.name}-{version or 'unknown'}-{stamp}"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(dest, backup, ignore=COPY_IGNORE)
    return str(backup)


def install(draft: Path, *, enabled: bool = True, force: bool = False) -> dict[str, Any]:
    report = validate(draft)
    if not report["ok"]:
        return {
            "ok": False,
            "error": "校验未通过，拒绝安装",
            "errors": report["errors"],
            "warnings": report["warnings"],
        }

    skill_id = draft.name
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", skill_id):
        return {"ok": False, "error": f"不安全的技能 id：{skill_id}", "errors": ["unsafe skill id"]}
    dest = skills_dir() / skill_id
    if dest.exists() and not force:
        return {
            "ok": False,
            "error": "同名技能已存在。--force 只覆盖已安装版本，不能跳过校验",
            "errors": ["skill already installed"],
            "warnings": report["warnings"],
        }
    previous = None
    if dest.exists():
        try:
            prev_version = str(read_skill_md(dest)[0].get("version") or "")
        except ValueError:
            prev_version = ""
        previous = {"version": prev_version, "backup": _backup(dest, prev_version)}
        shutil.rmtree(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(draft, dest, ignore=COPY_IGNORE)
    _set_enabled(skill_id, enabled)

    return {
        "ok": True,
        "skill_id": skill_id,
        "display_name": report["skill"].get("display_name") or skill_id,
        "version": report["skill"].get("version"),
        "installed_to": str(dest),
        "enabled": enabled,
        "replaced": previous,
        "warnings": report["warnings"],
        "next": "已生效，无需重启。请在右侧技能面板点「刷新」即可看到它。",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把技能草稿安装到应用数据目录")
    parser.add_argument("draft", help="草稿目录（相对工作区根）")
    parser.add_argument("--no-enable", action="store_true", help="安装但不启用")
    parser.add_argument("--force", action="store_true", help="覆盖已安装的同名技能，不跳过校验")
    args = parser.parse_args(argv)

    draft = Path(args.draft).resolve()
    if not draft.is_dir():
        print(f"ERROR: 草稿目录不存在：{args.draft}", file=sys.stderr)
        return 2

    result = install(draft, enabled=not args.no_enable, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        print("ERROR: 安装失败，请按 errors 修改草稿后重试", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
