#!/usr/bin/env python3
"""段落级对比两份 .docx，输出结构化改动 JSON。

Usage:
  python docx_diff.py <old.docx> <new.docx> [--out report.json]

Wave 1：仅正文段落（strip 后非空）；表格/文本框改动记入 warnings。
"""
from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from office_agent.script_policy import confine_to_workspace


def _paragraphs(path: Path) -> tuple[list[str], list[str]]:
    from docx import Document

    doc = Document(str(path))
    paras: list[str] = []
    for p in doc.paragraphs:
        text = (p.text or "").strip()
        if text:
            paras.append(text)
    warnings: list[str] = []
    if doc.tables:
        warnings.append(f"含 {len(doc.tables)} 个表格，Wave1 未做单元格级对比")
    return paras, warnings


def diff_paragraphs(old_paras: list[str], new_paras: list[str]) -> list[dict[str, Any]]:
    sm = SequenceMatcher(a=old_paras, b=new_paras, autojunk=False)
    changes: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            # Pair by index within the block; extras become add/delete
            old_block = old_paras[i1:i2]
            new_block = new_paras[j1:j2]
            n = max(len(old_block), len(new_block))
            for k in range(n):
                if k < len(old_block) and k < len(new_block):
                    if old_block[k] == new_block[k]:
                        continue
                    changes.append(
                        {
                            "op": "replace",
                            "old_para": i1 + k,
                            "new_para": j1 + k,
                            "old_text": old_block[k],
                            "new_text": new_block[k],
                        }
                    )
                elif k < len(old_block):
                    changes.append(
                        {
                            "op": "delete",
                            "old_para": i1 + k,
                            "new_para": None,
                            "old_text": old_block[k],
                            "new_text": "",
                        }
                    )
                else:
                    changes.append(
                        {
                            "op": "add",
                            "old_para": None,
                            "new_para": j1 + k,
                            "old_text": "",
                            "new_text": new_block[k],
                        }
                    )
        elif tag == "delete":
            for k, text in enumerate(old_paras[i1:i2]):
                changes.append(
                    {
                        "op": "delete",
                        "old_para": i1 + k,
                        "new_para": None,
                        "old_text": text,
                        "new_text": "",
                    }
                )
        elif tag == "insert":
            for k, text in enumerate(new_paras[j1:j2]):
                changes.append(
                    {
                        "op": "add",
                        "old_para": None,
                        "new_para": j1 + k,
                        "old_text": "",
                        "new_text": text,
                    }
                )
    return changes


def build_report(old_path: Path, new_path: Path) -> dict[str, Any]:
    old_paras, w1 = _paragraphs(old_path)
    new_paras, w2 = _paragraphs(new_path)
    warnings = list(w1) + list(w2)
    changes = diff_paragraphs(old_paras, new_paras)
    summary = {"add": 0, "delete": 0, "replace": 0}
    for c in changes:
        op = c["op"]
        if op in summary:
            summary[op] += 1
    return {
        "ok": True,
        "old": str(old_path),
        "new": str(new_path),
        "old_para_count": len(old_paras),
        "new_para_count": len(new_paras),
        "changes": changes,
        "warnings": warnings,
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="段落级对比两份 docx")
    parser.add_argument("old", type=Path, help="旧版 .docx")
    parser.add_argument("new", type=Path, help="新版 .docx")
    parser.add_argument("--out", type=Path, default=None, help="写出 JSON 报告路径")
    args = parser.parse_args(argv)

    try:
        cwd = Path.cwd()
        args.old = confine_to_workspace(args.old, cwd)
        args.new = confine_to_workspace(args.new, cwd)
        if args.out is not None:
            args.out = confine_to_workspace(args.out, cwd)
        if not args.old.is_file():
            raise FileNotFoundError(f"文件不存在: {args.old}")
        if not args.new.is_file():
            raise FileNotFoundError(f"文件不存在: {args.new}")
        if args.old.suffix.lower() != ".docx" or args.new.suffix.lower() != ".docx":
            raise ValueError("仅支持 .docx")
        report = build_report(args.old, args.new)
        out_path = args.out
        if out_path is None:
            out_path = args.new.with_name(args.new.stem + "_diff.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report["output"] = str(out_path)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001 — CLI 边界统一报错
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
