#!/usr/bin/env python3
"""Pull an installed Skill back into the workspace, or pack it for sharing.

Usage:
    python export.py <skill_id> --to-draft            # 拉回草稿区改（迭代用）
    python export.py <skill_id> --zip                 # 打成 工作成果/<中文名>-<id>.zip（分享用）
    python export.py <skill_id> --zip --with-fixtures # 连自测样例一起打包

同事拿到 zip 后，在技能面板点「导入技能」选该文件即可。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

# The frozen sidecar runs scripts through runpy.run_path, which leaves sys.path
# untouched, so sibling modules are not importable without this.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_common import (  # noqa: E402
    COPY_IGNORE,
    DRAFT_ROOT,
    read_skill_md,
    skills_dir,
    text_files,
)

OUTPUT_REL = Path("工作成果")
SKIP_PARTS = {"__pycache__", ".git"}
SKIP_NAMES = {".DS_Store"}


def _check_skill_id(skill_id: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", skill_id):
        raise ValueError(f"不安全的技能 id：{skill_id}")


def to_draft(skill_id: str) -> dict[str, Any]:
    _check_skill_id(skill_id)
    src = skills_dir() / skill_id
    dest = DRAFT_ROOT / skill_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, ignore=COPY_IGNORE)
    data, _ = read_skill_md(dest)
    return {
        "ok": True,
        "skill_id": skill_id,
        "draft_dir": dest.as_posix(),
        "version": str(data.get("version") or ""),
        "files": text_files(dest),
        "next": "改完记得升 version、补「变更记录」，再跑 validate.py 与 install.py",
    }


def to_zip(skill_id: str, *, with_fixtures: bool) -> dict[str, Any]:
    _check_skill_id(skill_id)
    src = skills_dir() / skill_id
    data, _ = read_skill_md(src)
    display = str(data.get("display_name") or skill_id).strip()
    OUTPUT_REL.mkdir(parents=True, exist_ok=True)
    zip_path = OUTPUT_REL / f"{display}-{skill_id}.zip"

    packed: list[str] = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src.rglob("*")):
            if not p.is_file() or p.name in SKIP_NAMES:
                continue
            rel = p.relative_to(src)
            if SKIP_PARTS & set(rel.parts) or p.suffix == ".pyc":
                continue
            if not with_fixtures and rel.parts and rel.parts[0] == "fixtures":
                continue
            # Nest under the skill id so install_zip resolves a single skill root.
            zf.write(p, arcname=(Path(skill_id) / rel).as_posix())
            packed.append(rel.as_posix())

    return {
        "ok": True,
        "skill_id": skill_id,
        "zip": zip_path.as_posix(),
        "size_kb": round(zip_path.stat().st_size / 1024, 1),
        "entries": len(packed),
        "files": packed,
        "next": "同事在技能面板点「导入技能」→「zip / md 文件」选这个包即可",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出已安装技能：拉回草稿区或打成分享包")
    parser.add_argument("skill_id", help="技能 id（技能目录名）")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--to-draft", action="store_true", help="复制到工作区草稿区以便修改")
    mode.add_argument("--zip", action="store_true", help="打包到 工作成果/ 供分享")
    parser.add_argument("--with-fixtures", action="store_true", help="打包时带上 fixtures/")
    args = parser.parse_args(argv)

    src = skills_dir() / args.skill_id
    if not (src / "SKILL.md").is_file():
        print(f"ERROR: 技能未安装或缺少 SKILL.md：{args.skill_id}", file=sys.stderr)
        return 2

    try:
        result = to_draft(args.skill_id) if args.to_draft else to_zip(
            args.skill_id, with_fixtures=args.with_fixtures
        )
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
