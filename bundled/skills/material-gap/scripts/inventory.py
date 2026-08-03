#!/usr/bin/env python3
"""Inventory workspace files by extension for material-gap.

Usage:
  python inventory.py [relative_dir]
  python inventory.py . --out .office-agent/work/material-gap/inventory.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

SKIP_DIR_NAMES = {
    ".git",
    ".office-agent",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
}

TYPE_LABELS = {
    ".docx": "Word",
    ".doc": "Word",
    ".xlsx": "Excel",
    ".xls": "Excel",
    ".pptx": "PPT",
    ".ppt": "PPT",
    ".pdf": "PDF",
    ".md": "Markdown",
    ".txt": "文本",
    ".png": "图片",
    ".jpg": "图片",
    ".jpeg": "图片",
    ".gif": "图片",
    ".webp": "图片",
}


def classify(suffix: str) -> str:
    return TYPE_LABELS.get(suffix.lower(), "其他")


def walk(root: Path, base: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        # skip nested skip dirs
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            rel = path.relative_to(base).as_posix()
        except ValueError:
            continue
        suf = path.suffix.lower()
        rows.append(
            {
                "path": rel,
                "name": path.name,
                "ext": suf or "(无扩展名)",
                "type": classify(suf),
                "size": path.stat().st_size,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List workspace materials by type")
    parser.add_argument("dir", nargs="?", default=".", help="relative directory")
    parser.add_argument(
        "--out",
        default=".office-agent/work/material-gap/inventory.json",
        help="output JSON path relative to cwd (workspace root)",
    )
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    target = (cwd / args.dir).resolve()
    try:
        target.relative_to(cwd.resolve())
    except ValueError:
        print(f"ERROR: path escapes workspace: {args.dir}", file=sys.stderr)
        return 1
    if not target.is_dir():
        print(f"ERROR: not a directory: {args.dir}", file=sys.stderr)
        return 1

    files = walk(target, cwd.resolve())
    by_ext = Counter(f["ext"] for f in files)
    by_type = Counter(f["type"] for f in files)
    report = {
        "ok": True,
        "root": args.dir,
        "total": len(files),
        "by_ext": dict(sorted(by_ext.items())),
        "by_type": dict(sorted(by_type.items())),
        "files": files,
    }
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = cwd / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "ok": True,
        "total": len(files),
        "by_type": report["by_type"],
        "inventory": str(out_path.relative_to(cwd)) if out_path.is_relative_to(cwd) else str(out_path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
