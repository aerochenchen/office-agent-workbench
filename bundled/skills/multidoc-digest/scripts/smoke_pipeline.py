#!/usr/bin/env python3
"""Generate 30 sample .docx + gold facts, run ingest→cards→merge→audit smoke.

Usage (repo root, with python-docx available):
    python bundled/skills/multidoc-digest/scripts/smoke_pipeline.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[4]  # repo root from .../bundled/skills/multidoc-digest/scripts
SKILL_SCRIPTS = Path(__file__).resolve().parent
FIXTURE = ROOT / "bundled" / "skills" / "multidoc-digest" / "fixtures" / "sample-30"
GOLD = FIXTURE / "gold_facts.json"


THEMES = [
    ("数字化转型", "一、数字化转型进展", "建成智能平台，覆盖基层网点 {n} 个，同比提升 {pct}%。"),
    ("安全生产", "一、安全生产工作", "全年排查隐患 {n} 处，整改完成率达到 {pct}%。"),
    ("人才培养", "一、干部人才培养", "完成专题培训 {n} 人次，优秀学员占比 {pct}%。"),
    ("服务提升", "一、窗口服务提升", "群众满意度达到 {pct}%，办结时限压缩 {n} 个工作日。"),
    ("党建引领", "一、党建引领业务", "开展主题党日 {n} 次，党员攻坚项目落地 {pct} 项重点任务。"),
    ("财务合规", "一、财务与内控", "审计发现问题 {n} 项，已整改 {pct}%。"),
]


def make_doc(path: Path, title: str, heading: str, body: str, extra: str) -> None:
    doc = Document()
    doc.add_heading(title, level=1)
    doc.add_paragraph(heading)
    doc.add_paragraph(body)
    doc.add_paragraph("二、下一步打算")
    doc.add_paragraph(extra)
    doc.add_paragraph("（一）持续推进重点工作")
    doc.add_paragraph("例如：在试点单位先行先试，形成可复制经验。")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))


def generate_samples() -> list[dict]:
    """Create 30 docs; return gold facts (must-appear claims)."""
    if FIXTURE.exists():
        for p in FIXTURE.glob("*.docx"):
            p.unlink()
    FIXTURE.mkdir(parents=True, exist_ok=True)

    gold: list[dict] = []
    # 10 gold facts tied to specific docs
    gold_specs = [
        (0, 128, 15, "覆盖基层网点 128 个"),
        (1, 56, 92, "排查隐患 56 处"),
        (2, 320, 18, "专题培训 320 人次"),
        (3, 3, 97, "群众满意度达到 97%"),
        (4, 12, 8, "主题党日 12 次"),
        (5, 7, 100, "审计发现问题 7 项"),
        (6, 210, 22, "覆盖基层网点 210 个"),
        (7, 41, 88, "排查隐患 41 处"),
        (8, 150, 25, "专题培训 150 人次"),
        (9, 2, 95, "群众满意度达到 95%"),
    ]

    for i in range(30):
        theme_i = i % len(THEMES)
        theme_name, heading, tmpl = THEMES[theme_i]
        n = 10 + i * 3
        pct = 50 + (i % 40)
        # Override with gold specs for first 10
        fact_text = None
        for gi, (idx, gn, gpct, label) in enumerate(gold_specs):
            if idx == i:
                n, pct = gn, gpct
                fact_text = label
                break
        body = tmpl.format(n=n, pct=pct)
        title = f"{theme_name}专项材料{i + 1:02d}"
        fname = f"{title}.docx"
        path = FIXTURE / fname
        extra = "着力完善制度机制，推进重点任务落地见效。"
        if i % 5 == 0:
            extra = "仍存在短板：基层力量不足，制约业务协同。"
        make_doc(path, title, heading, body, extra)
        if fact_text:
            gold.append(
                {
                    "doc_index": i + 1,
                    "filename": fname,
                    "must_contain": fact_text,
                    "theme": theme_name,
                }
            )

    GOLD.write_text(json.dumps(gold, ensure_ascii=False, indent=2), encoding="utf-8")
    return gold


def write_synthetic_cards(work: Path) -> None:
    """Simulate Agent map step from packs/chunks (deterministic, not LLM)."""
    chunks_path = work / "chunks.jsonl"
    cards_dir = work / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    by_doc: dict[str, list[dict]] = {}
    with chunks_path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            by_doc.setdefault(rec["doc_id"], []).append(rec)

    for doc_id, chs in by_doc.items():
        points = []
        for ch in chs[:4]:
            # take first sentence-ish as claim
            text = ch["text"].replace("\n", " ")
            claim = text[:80]
            kind = "other"
            has_data = bool(ch.get("has_data"))
            if has_data:
                kind = "data"
            elif ch.get("has_problem"):
                kind = "problem"
            elif ch.get("has_measure"):
                kind = "measure"
            elif ch.get("has_case"):
                kind = "case"
            points.append(
                {
                    "claim": claim,
                    "citations": [ch["chunk_id"]],
                    "kind": kind,
                    "has_data": has_data,
                }
            )
        card = {
            "doc_id": doc_id,
            "title": chs[0].get("source", doc_id),
            "points": points,
            "summary": points[0]["claim"][:120] if points else "",
        }
        (cards_dir / f"{doc_id}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def write_synthetic_report(work: Path, out_report: Path) -> None:
    outline = json.loads((work / "outline.json").read_text(encoding="utf-8"))
    chunks = {}
    with (work / "chunks.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            chunks[rec["chunk_id"]] = rec
    manifest = {}
    with (work / "manifest.jsonl").open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            manifest[rec["doc_id"]] = rec

    lines = ["# 样本汇总报告（冒烟）", ""]
    used: set[str] = set()
    for theme in outline["themes"]:
        lines.append(f"## {theme['title']}")
        lines.append("")
        for pt in theme["points"][:3]:
            cites = pt.get("citations") or []
            mark = "".join(f"〔{c}〕" for c in cites[:2])
            lines.append(f"{pt['claim']}{mark}")
            lines.append("")
            for c in cites:
                m = c.split("#")[0]
                used.add(m)
        lines.append("")

    # Intentionally leave some docs unused to exercise coverage; cite most docs
    # Add one invalid citation to verify audit catches it
    lines.append("## 附记")
    lines.append("")
    lines.append("个别表述待核实〔d999#s01〕。")
    lines.append("")
    lines.append("## 参考文献")
    lines.append("")
    lines.append("| 文档ID | 文件名 |")
    lines.append("|--------|--------|")
    for doc_id in sorted(used):
        fn = manifest.get(doc_id, {}).get("filename", "")
        lines.append(f"| {doc_id} | {fn} |")
    lines.append("")

    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text("\n".join(lines), encoding="utf-8")


def run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)


def check_gold(report_text: str, gold: list[dict]) -> dict:
    hits = []
    misses = []
    for g in gold:
        if g["must_contain"] in report_text:
            hits.append(g)
        else:
            misses.append(g)
    return {
        "gold_total": len(gold),
        "hits": len(hits),
        "misses": [{"must_contain": m["must_contain"], "filename": m["filename"]} for m in misses],
        "hit_rate": round(len(hits) / len(gold), 4) if gold else 0.0,
    }


def main() -> int:
    gold = generate_samples()
    ws = FIXTURE / "_workspace"
    if ws.exists():
        import shutil

        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    # materials live at workspace/materials
    materials = ws / "materials"
    materials.mkdir()
    for p in FIXTURE.glob("*.docx"):
        (materials / p.name).write_bytes(p.read_bytes())

    py = sys.executable
    run([py, str(SKILL_SCRIPTS / "ingest.py"), str(materials)], cwd=ws)
    work = ws / ".office-agent" / "work" / "multidoc-digest"
    write_synthetic_cards(work)
    run([py, str(SKILL_SCRIPTS / "merge_outline.py")], cwd=ws)
    report = ws / "工作成果" / "汇总报告.md"
    write_synthetic_report(work, report)
    run([py, str(SKILL_SCRIPTS / "audit.py"), str(report)], cwd=ws)

    report_text = report.read_text(encoding="utf-8")
    # For smoke, gold may partially miss because synthetic report truncates claims;
    # also copy gold facts into report appendix so pipeline audit still meaningful,
    # and separately score gold against packs (ingest fidelity).
    packs_blob = ""
    for p in sorted((work / "packs").glob("*.md")):
        packs_blob += p.read_text(encoding="utf-8")
    gold_vs_packs = check_gold(packs_blob, gold)
    gold_vs_report = check_gold(report_text, gold)

    audit_summary = json.loads(
        # re-run audit capturing last stdout already printed; read audit file headers
        json.dumps({"note": "see stdout above"})
    )
    result = {
        "fixture_dir": str(FIXTURE),
        "workspace": str(ws),
        "gold_vs_packs": gold_vs_packs,
        "gold_vs_report_smoke": gold_vs_report,
        "audit_md": str(ws / "工作成果" / "审计报告.md"),
        "expect_invalid_citation": "d999#s01",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Assertions for CI-ish smoke
    assert gold_vs_packs["hit_rate"] == 1.0, gold_vs_packs
    audit_md = (ws / "工作成果" / "审计报告.md").read_text(encoding="utf-8")
    assert "d999#s01" in audit_md
    assert "无效引用" in audit_md
    print("SMOKE OK: ingest preserves gold facts; audit flags invalid citation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
