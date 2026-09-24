#!/usr/bin/env python3
"""Scan .docx materials, semantic-chunk, write manifest/chunks/packs.

Usage:
    python ingest.py <folder> [--work-dir <path>] [--max-chars 2000] [--pack-chars 6000]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from docx import Document
from office_agent.script_policy import confine_to_workspace

WORK_REL = Path(".office-agent") / "work" / "multidoc-digest"

_CN_LEVEL1 = re.compile(r"^[一二三四五六七八九十]+、")
_CN_LEVEL2 = re.compile(r"^（[一二三四五六七八九十]+）")
_CN_LEVEL3 = re.compile(r"^\d+[\.\、]\s*")
_CN_LEVEL4 = re.compile(r"^[（\(]\d+[）\)]")
_CN_HEADER_PREFIX = re.compile(
    r"^(第[一二三四五六七八九十\d]+[章节条]|附件[一二三四五六七八九十\d]*|抄送[：:]|主送[：:])"
)
_HAS_DATA = re.compile(
    r"[增长降低达到实现完成增减]+.*?[％%\d]|\d+[\.\d]*[万亿千百]|同比|环比|占比[：:是为]|人均"
)
_HAS_CASE = re.compile(r"如[：:。、，]|例如|比如|案例|典型|示范|试点|某[省市县区部门企业]")
_HAS_PROBLEM = re.compile(r"不足|挑战|问题|困难|短板|薄弱|差距|滞后|制约|瓶颈")
_HAS_MEASURE = re.compile(
    r"(一是|二是|三是|一要|二要|三要|着力|大力|持续|深入|加强|推进|完善|健全)"
)


def detect_heading_level(text: str, style_name: str) -> int:
    text = text.strip()
    if style_name.startswith("Heading"):
        try:
            return int(style_name.replace("Heading", "").strip())
        except ValueError:
            return 1
    if _CN_LEVEL1.match(text):
        return 1
    if _CN_LEVEL2.match(text):
        return 2
    if _CN_LEVEL3.match(text):
        return 3
    if _CN_LEVEL4.match(text):
        return 4
    if _CN_HEADER_PREFIX.match(text):
        return 1
    if text.startswith(("附件", "抄送", "主送")):
        return 3
    return 0


def _tags_for(text: str) -> list[str]:
    tags: list[str] = []
    if _HAS_DATA.search(text):
        tags.append("has_data")
    if _HAS_CASE.search(text):
        tags.append("has_case")
    if _HAS_PROBLEM.search(text):
        tags.append("has_problem")
    if _HAS_MEASURE.search(text):
        tags.append("has_measure")
    return tags


def extract_structure(filepath: Path) -> list[dict]:
    doc = Document(str(filepath))
    structure: list[dict] = []
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue
        style_name = para.style.name if para.style else "Normal"
        level = detect_heading_level(text, style_name)
        tags = _tags_for(text)
        structure.append(
            {
                "text": text,
                "level": level,
                "style": style_name,
                "para_idx": i,
                "is_heading": level > 0,
                "tags": tags,
                "char_count": len(text),
            }
        )
    return structure


def _finalize_unit(unit: dict) -> None:
    unit["has_data"] = "has_data" in unit["all_tags"]
    unit["has_case"] = "has_case" in unit["all_tags"]
    unit["has_problem"] = "has_problem" in unit["all_tags"]
    unit["has_measure"] = "has_measure" in unit["all_tags"]
    unit["all_tags"] = sorted(unit["all_tags"])


def build_semantic_units(structure: list[dict]) -> list[dict]:
    units: list[dict] = []
    current: dict | None = None

    for para in structure:
        if para["is_heading"]:
            if current and current["paragraphs"]:
                _finalize_unit(current)
                units.append(current)
            current = {
                "section_title": para["text"],
                "section_level": para["level"],
                "paragraphs": [],
                "start_idx": para["para_idx"],
                "end_idx": para["para_idx"],
                "all_tags": set(para["tags"]),
                "total_chars": 0,
            }
            # keep heading text as part of unit body for citation context
            current["paragraphs"].append(para["text"])
            current["total_chars"] += para["char_count"]
        else:
            if current is None:
                current = {
                    "section_title": "(前言)",
                    "section_level": 0,
                    "paragraphs": [],
                    "start_idx": para["para_idx"],
                    "end_idx": para["para_idx"],
                    "all_tags": set(),
                    "total_chars": 0,
                }
            current["paragraphs"].append(para["text"])
            current["end_idx"] = para["para_idx"]
            current["all_tags"].update(para["tags"])
            current["total_chars"] += para["char_count"]

    if current and current["paragraphs"]:
        _finalize_unit(current)
        units.append(current)
    return units


def chunk_units(units: list[dict], max_chars: int) -> list[dict]:
    chunks: list[dict] = []
    for unit in units:
        paras = unit["paragraphs"]
        if unit["total_chars"] <= max_chars:
            text = "\n\n".join(paras)
            chunks.append(
                {
                    "text": text,
                    "section_title": unit["section_title"],
                    "section_level": unit["section_level"],
                    "paragraph_range": [unit["start_idx"], unit["end_idx"]],
                    "has_data": unit["has_data"],
                    "has_case": unit["has_case"],
                    "has_problem": unit["has_problem"],
                    "has_measure": unit["has_measure"],
                    "tags": unit["all_tags"],
                    "char_count": unit["total_chars"],
                    "is_split": False,
                }
            )
            continue

        buffer: list[str] = []
        buffer_chars = 0
        sub_texts: list[str] = []
        for p in paras:
            if buffer_chars + len(p) > max_chars and buffer:
                sub_texts.append("\n\n".join(buffer))
                buffer = [p]
                buffer_chars = len(p)
            else:
                buffer.append(p)
                buffer_chars += len(p)
        if buffer:
            sub_texts.append("\n\n".join(buffer))
        for sub in sub_texts:
            tags = _tags_for(sub)
            chunks.append(
                {
                    "text": sub,
                    "section_title": unit["section_title"],
                    "section_level": unit["section_level"],
                    "paragraph_range": [unit["start_idx"], unit["end_idx"]],
                    "has_data": "has_data" in tags,
                    "has_case": "has_case" in tags,
                    "has_problem": "has_problem" in tags,
                    "has_measure": "has_measure" in tags,
                    "tags": tags,
                    "char_count": len(sub),
                    "is_split": True,
                }
            )
    return chunks


def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def find_docx(folder: Path) -> list[Path]:
    files = sorted(
        p
        for p in folder.rglob("*.docx")
        if p.is_file() and not p.name.startswith("~$")
    )
    return files


def build_pack(doc_id: str, filename: str, chunks: list[dict], pack_chars: int) -> str:
    lines = [
        f"# {filename}",
        f"doc_id: {doc_id}",
        "",
        "## 大纲",
    ]
    for ch in chunks:
        flag = []
        if ch["has_data"]:
            flag.append("data")
        if ch["has_case"]:
            flag.append("case")
        if ch["has_problem"]:
            flag.append("problem")
        if ch["has_measure"]:
            flag.append("measure")
        flag_s = ",".join(flag) if flag else "-"
        lines.append(f"- `{ch['chunk_id']}` {ch['section_title']} [{flag_s}]")

    lines.append("")
    lines.append("## 显著片段（含数据/结论优先）")
    budget = pack_chars
    # Prefer tagged chunks first, then the rest
    ordered = sorted(
        chunks,
        key=lambda c: (
            0 if (c["has_data"] or c["has_problem"] or c["has_measure"]) else 1,
            c["chunk_id"],
        ),
    )
    for ch in ordered:
        block = f"### {ch['chunk_id']} {ch['section_title']}\n{ch['text']}\n"
        if len(block) > budget and budget < pack_chars:
            break
        if len(block) > budget:
            block = block[: max(0, budget - 20)] + "\n…(截断)\n"
        lines.append(block.rstrip())
        budget -= len(block)
        if budget <= 0:
            lines.append("\n…(pack 达到字符上限，其余见 chunks.jsonl)\n")
            break
    return "\n".join(lines) + "\n"


def default_work_dir(cwd: Path) -> Path:
    return cwd / WORK_REL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest .docx into multidoc-digest work dir")
    parser.add_argument("folder", help="Folder of .docx materials (workspace-relative or absolute)")
    parser.add_argument("--work-dir", default=None, help="Override work directory")
    parser.add_argument("--max-chars", type=int, default=2000)
    parser.add_argument("--pack-chars", type=int, default=6000)
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    folder = Path(args.folder)
    if not folder.is_absolute():
        folder = cwd / folder
    folder = confine_to_workspace(folder, cwd)
    if not folder.is_dir():
        print(f"ERROR: folder not found: {folder}", file=sys.stderr)
        return 1

    work = Path(args.work_dir) if args.work_dir else default_work_dir(cwd)
    if not work.is_absolute():
        work = cwd / work
    work = confine_to_workspace(work, cwd)
    packs_dir = work / "packs"
    cards_dir = work / "cards"
    packs_dir.mkdir(parents=True, exist_ok=True)
    cards_dir.mkdir(parents=True, exist_ok=True)

    files = find_docx(folder)
    if not files:
        print(f"ERROR: no .docx under {folder}", file=sys.stderr)
        return 1

    manifest_path = work / "manifest.jsonl"
    chunks_path = work / "chunks.jsonl"

    ok_n = 0
    err_n = 0
    total_chunks = 0

    with manifest_path.open("w", encoding="utf-8") as mf, chunks_path.open(
        "w", encoding="utf-8"
    ) as cf:
        for idx, path in enumerate(files, start=1):
            doc_id = f"d{idx:03d}"
            rel_name = path.name
            try:
                sha = file_sha1(path)
                structure = extract_structure(path)
                if not structure:
                    raise ValueError("empty document (no paragraphs)")
                units = build_semantic_units(structure)
                raw_chunks = chunk_units(units, args.max_chars)
                chunks_out: list[dict] = []
                for sec_i, ch in enumerate(raw_chunks, start=1):
                    chunk_id = f"{doc_id}#s{sec_i:02d}"
                    rec = {
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "source": rel_name,
                        "path": str(path),
                        "section_title": ch["section_title"],
                        "section_level": ch["section_level"],
                        "paragraph_range": ch["paragraph_range"],
                        "text": ch["text"],
                        "has_data": ch["has_data"],
                        "has_case": ch["has_case"],
                        "has_problem": ch["has_problem"],
                        "has_measure": ch["has_measure"],
                        "tags": ch["tags"],
                        "char_count": ch["char_count"],
                    }
                    chunks_out.append(rec)
                    cf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total_chunks += len(chunks_out)
                para_count = len(structure)
                char_count = sum(p["char_count"] for p in structure)
                pack = build_pack(doc_id, rel_name, chunks_out, args.pack_chars)
                (packs_dir / f"{doc_id}.md").write_text(pack, encoding="utf-8")
                mf.write(
                    json.dumps(
                        {
                            "doc_id": doc_id,
                            "filename": rel_name,
                            "path": str(path),
                            "paragraphs": para_count,
                            "chars": char_count,
                            "chunks": len(chunks_out),
                            "sha1": sha,
                            "status": "ok",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                ok_n += 1
            except Exception as exc:  # noqa: BLE001 — per-file isolation
                err_n += 1
                mf.write(
                    json.dumps(
                        {
                            "doc_id": doc_id,
                            "filename": rel_name,
                            "path": str(path),
                            "paragraphs": 0,
                            "chars": 0,
                            "chunks": 0,
                            "sha1": "",
                            "status": "error",
                            "error": str(exc),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                print(f"WARN: {rel_name}: {exc}", file=sys.stderr)

    summary = {
        "ok": True,
        "folder": str(folder),
        "work_dir": str(work),
        "files_total": len(files),
        "files_ok": ok_n,
        "files_error": err_n,
        "chunks": total_chunks,
        "manifest": str(manifest_path),
        "chunks_file": str(chunks_path),
        "packs_dir": str(packs_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if ok_n else 1


if __name__ == "__main__":
    raise SystemExit(main())
