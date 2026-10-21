#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 docx 正文（含引用域文本）与表格导出为纯文本，供逐条审查。

用法:
    python extract_docx.py 制度.docx -o .office-agent/work/regulation-pre-review/取稿.txt
    python extract_docx.py 制度.docx --no-tables

为什么要逐 w:t 取：docx 里的法律名称常以交叉引用域存放，python-docx 的
paragraph.text 会漏掉域结果，导致依据条款读成“按照、…”，审查时判断失真。
stdout 只打 JSON 摘要。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import docx
from docx.oxml.ns import qn


def para_text(p) -> str:
    return "".join(t.text for t in p._p.iter(qn("w:t")) if t.text).strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("docx_path")
    ap.add_argument("-o", "--out")
    ap.add_argument("--no-tables", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.docx_path):
        print(f"ERROR: 找不到文件 {args.docx_path}", file=sys.stderr)
        return 1

    d = docx.Document(args.docx_path)
    lines: list[str] = []

    for i, p in enumerate(d.paragraphs):
        txt = para_text(p)
        if not txt:
            continue
        style = p.style.name if p.style is not None else ""
        lines.append(f"[P{i}]({style}) {txt}")

    if not args.no_tables:
        for ti, t in enumerate(d.tables):
            lines.append("")
            lines.append(f"=== 表格 T{ti}  {len(t.rows)}行 x {len(t.columns)}列 ===")
            for r in t.rows:
                cells, prev = [], None
                for c in r.cells:
                    v = c.text.replace("\n", " / ").strip()
                    if v != prev:          # 跳过纵向合并的重复单元格
                        cells.append(v)
                        prev = v
                lines.append("| " + " | ".join(cells))

    out = args.out or (args.docx_path + ".txt")
    parent = os.path.dirname(os.path.abspath(out))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps({
        "ok": True,
        "out": out,
        "paragraphs": len(d.paragraphs),
        "tables": len(d.tables),
        "nonempty_paragraphs": sum(1 for line in lines if line.startswith("[P")),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
