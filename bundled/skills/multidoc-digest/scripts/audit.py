#!/usr/bin/env python3
"""Audit a digest report for coverage and citation integrity.

Usage:
    python audit.py output/汇总报告.md
    python audit.py <report> --work-dir .office-agent/work/multidoc-digest --sample 8
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

WORK_REL = Path(".office-agent") / "work" / "multidoc-digest"
CITATION_RE = re.compile(r"〔(d\d{3}#s\d{2,})〕")
DOC_FROM_CIT = re.compile(r"^(d\d{3})")


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_cards(cards_dir: Path) -> list[dict]:
    cards: list[dict] = []
    if not cards_dir.is_dir():
        return cards
    for p in sorted(cards_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        data.setdefault("doc_id", p.stem)
        cards.append(data)
    return cards


def sentences_with_citations(text: str) -> list[tuple[str, list[str]]]:
    """Split roughly by Chinese/English sentence enders; keep those with citations."""
    parts = re.split(r"(?<=[。！？；\n])", text)
    out: list[tuple[str, list[str]]] = []
    for part in parts:
        s = part.strip()
        if not s:
            continue
        cites = CITATION_RE.findall(s)
        if cites:
            out.append((s, cites))
    return out


def single_source_data_risks(cards: list[dict]) -> list[dict]:
    risks: list[dict] = []
    for card in cards:
        for pt in card.get("points") or []:
            claim = str(pt.get("claim") or "")
            citations = [str(c) for c in (pt.get("citations") or [])]
            kind = str(pt.get("kind") or "")
            has_data = bool(pt.get("has_data")) or kind == "data"
            if not has_data:
                continue
            doc_ids = {m.group(1) for c in citations if (m := DOC_FROM_CIT.match(c))}
            if len(citations) <= 1 or len(doc_ids) <= 1:
                risks.append(
                    {
                        "doc_id": card.get("doc_id"),
                        "claim": claim,
                        "citations": citations,
                        "reason": "数据要点仅单一来源或单一锚点",
                    }
                )
    return risks


def render_report(
    *,
    report_path: Path,
    manifest: list[dict],
    chunks: list[dict],
    cards: list[dict],
    cited_ids: list[str],
    invalid: list[str],
    used_docs: set[str],
    unused_docs: list[dict],
    risks: list[dict],
    samples: list[dict],
    coverage_ratio: float,
) -> str:
    ok_docs = [m for m in manifest if m.get("status") == "ok"]
    err_docs = [m for m in manifest if m.get("status") != "ok"]
    lines = [
        "# 批量文档整理 · 审计报告",
        "",
        f"- 被审计文件：`{report_path}`",
        f"- 入库成功：{len(ok_docs)} 份；失败：{len(err_docs)} 份",
        f"- 正文引用锚点数：{len(cited_ids)}（去重 {len(set(cited_ids))}）",
        f"- **文档覆盖率**：{coverage_ratio:.1%}（{len(used_docs)}/{len(ok_docs)}）",
        f"- **无效引用**：{len(invalid)}",
        f"- **单一来源数据风险**：{len(risks)}",
        "",
        "## 1. 覆盖率",
        "",
        f"已用文档 ID：{', '.join(sorted(used_docs)) or '（无）'}",
        "",
        "### 未用文件清单",
        "",
    ]
    if unused_docs:
        lines.append("| doc_id | 文件名 |")
        lines.append("|--------|--------|")
        for m in unused_docs:
            lines.append(f"| {m.get('doc_id')} | {m.get('filename')} |")
    else:
        lines.append("（无 — 全部成功入库文档均在正文引用中出现）")

    lines.extend(["", "## 2. 引用校验", ""])
    if invalid:
        lines.append("以下锚点出现在报告中，但 **不在** `chunks.jsonl`：")
        lines.append("")
        for c in invalid:
            lines.append(f"- `{c}`")
    else:
        lines.append("全部正文引用锚点均可在 chunks 中命中。")

    lines.extend(["", "## 3. 风险清单（单一来源数据）", ""])
    if risks:
        for r in risks[:50]:
            lines.append(
                f"- [{r.get('doc_id')}] {r.get('claim')} — {r.get('reason')}；citations={r.get('citations')}"
            )
        if len(risks) > 50:
            lines.append(f"- …另有 {len(risks) - 50} 条省略")
    else:
        lines.append("（未发现）")

    lines.extend(["", "## 4. 抽检对照（报告论断 ↔ 源 chunk）", ""])
    if samples:
        for i, s in enumerate(samples, start=1):
            lines.append(f"### 样本 {i}")
            lines.append("")
            lines.append(f"- 报告句：{s['sentence']}")
            lines.append(f"- 引用：`{s['citation']}`")
            lines.append(f"- 源文件：{s.get('source', '')}")
            lines.append(f"- 章节：{s.get('section_title', '')}")
            lines.append("")
            lines.append("```")
            lines.append(s.get("chunk_text", "")[:800])
            lines.append("```")
            lines.append("")
    else:
        lines.append("（报告中无带引用的句子，无法抽检）")

    if err_docs:
        lines.extend(["", "## 5. 入库失败文件", ""])
        for m in err_docs:
            lines.append(f"- {m.get('doc_id')} {m.get('filename')}: {m.get('error', '')}")

    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit multidoc digest report")
    parser.add_argument("report", help="Path to 汇总报告.md")
    parser.add_argument("--work-dir", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--chunks", default=None)
    parser.add_argument("--cards", default=None)
    parser.add_argument("--output", default=None, help="Default: output/审计报告.md")
    parser.add_argument("--sample", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = (cwd / report_path).resolve()
    if not report_path.is_file():
        print(f"ERROR: report not found: {report_path}", file=sys.stderr)
        return 1

    work = Path(args.work_dir) if args.work_dir else cwd / WORK_REL
    if not work.is_absolute():
        work = (cwd / work).resolve()

    manifest_path = Path(args.manifest) if args.manifest else work / "manifest.jsonl"
    chunks_path = Path(args.chunks) if args.chunks else work / "chunks.jsonl"
    cards_dir = Path(args.cards) if args.cards else work / "cards"
    for p in (manifest_path, chunks_path, cards_dir):
        if not p.is_absolute():
            # re-bind locals carefully
            pass
    if not manifest_path.is_absolute():
        manifest_path = (cwd / manifest_path).resolve()
    if not chunks_path.is_absolute():
        chunks_path = (cwd / chunks_path).resolve()
    if not cards_dir.is_absolute():
        cards_dir = (cwd / cards_dir).resolve()

    out_path = Path(args.output) if args.output else cwd / "output" / "审计报告.md"
    if not out_path.is_absolute():
        out_path = (cwd / out_path).resolve()

    report_text = report_path.read_text(encoding="utf-8")
    cited_ids = CITATION_RE.findall(report_text)
    chunk_rows = load_jsonl(chunks_path)
    chunk_by_id = {c["chunk_id"]: c for c in chunk_rows if "chunk_id" in c}
    valid_ids = set(chunk_by_id)

    invalid = sorted({c for c in cited_ids if c not in valid_ids})
    used_docs = {m.group(1) for c in cited_ids if (m := DOC_FROM_CIT.match(c))}

    manifest = load_jsonl(manifest_path)
    ok_docs = [m for m in manifest if m.get("status") == "ok"]
    unused_docs = [m for m in ok_docs if m.get("doc_id") not in used_docs]
    coverage_ratio = (len(used_docs) / len(ok_docs)) if ok_docs else 0.0

    cards = load_cards(cards_dir)
    risks = single_source_data_risks(cards)

    sent_cites = sentences_with_citations(report_text)
    rng = random.Random(args.seed)
    candidates = [(s, c) for s, cites in sent_cites for c in cites if c in valid_ids]
    rng.shuffle(candidates)
    samples: list[dict] = []
    for sentence, citation in candidates[: max(0, args.sample)]:
        ch = chunk_by_id[citation]
        samples.append(
            {
                "sentence": sentence,
                "citation": citation,
                "source": ch.get("source", ""),
                "section_title": ch.get("section_title", ""),
                "chunk_text": ch.get("text", ""),
            }
        )

    md = render_report(
        report_path=report_path,
        manifest=manifest,
        chunks=chunk_rows,
        cards=cards,
        cited_ids=cited_ids,
        invalid=invalid,
        used_docs=used_docs,
        unused_docs=unused_docs,
        risks=risks,
        samples=samples,
        coverage_ratio=coverage_ratio,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    summary = {
        "ok": True,
        "report": str(report_path),
        "audit_output": str(out_path),
        "coverage_ratio": round(coverage_ratio, 4),
        "docs_ok": len(ok_docs),
        "docs_cited": len(used_docs),
        "unused_count": len(unused_docs),
        "citations_total": len(cited_ids),
        "citations_unique": len(set(cited_ids)),
        "invalid_citations": invalid,
        "single_source_risks": len(risks),
        "samples": len(samples),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
