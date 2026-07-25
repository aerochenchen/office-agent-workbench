#!/usr/bin/env python3
"""Merge map cards into a thematic outline via lexical clustering.

Usage:
    python merge_outline.py
    python merge_outline.py --work-dir .office-agent/work/multidoc-digest
    python merge_outline.py --cards <dir> --chunks <file> --manifest <file> --output <file>
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

WORK_REL = Path(".office-agent") / "work" / "multidoc-digest"

# Simple CJK + alnum tokenizer
_TOKEN = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}")
_STOP = {
    "以及",
    "进行",
    "工作",
    "有关",
    "相关",
    "情况",
    "问题",
    "方面",
    "通过",
    "进一步",
    "不断",
    "加强",
    "推进",
    "完善",
    "落实",
    "我们",
    "他们",
    "这个",
    "那个",
    "一个",
    "可以",
    "已经",
    "对于",
    "由于",
    "如果",
    "但是",
    "因此",
    "同时",
}


def tokenize(text: str) -> list[str]:
    toks = [t.lower() for t in _TOKEN.findall(text or "")]
    return [t for t in toks if t not in _STOP]


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_cards(cards_dir: Path) -> list[dict]:
    cards: list[dict] = []
    if not cards_dir.is_dir():
        return cards
    for p in sorted(cards_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"WARN: bad card {p.name}: {exc}", file=sys.stderr)
            continue
        data.setdefault("doc_id", p.stem)
        cards.append(data)
    return cards


def extract_points(cards: list[dict]) -> list[dict]:
    points: list[dict] = []
    for card in cards:
        doc_id = str(card.get("doc_id", ""))
        for i, pt in enumerate(card.get("points") or []):
            claim = str(pt.get("claim") or "").strip()
            if not claim:
                continue
            citations = [str(c) for c in (pt.get("citations") or [])]
            points.append(
                {
                    "id": f"{doc_id}-p{i:02d}",
                    "doc_id": doc_id,
                    "claim": claim,
                    "citations": citations,
                    "kind": str(pt.get("kind") or "other"),
                    "has_data": bool(pt.get("has_data")),
                    "tokens": tokenize(claim),
                }
            )
    return points


def build_idf(points: list[dict]) -> dict[str, float]:
    df: Counter[str] = Counter()
    for p in points:
        for t in set(p["tokens"]):
            df[t] += 1
    n = max(len(points), 1)
    return {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}


def tfidf_vec(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    if not tokens:
        return {}
    tf = Counter(tokens)
    total = sum(tf.values())
    return {t: (c / total) * idf.get(t, 1.0) for t, c in tf.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def cluster_points(points: list[dict], threshold: float = 0.28) -> list[list[dict]]:
    """Greedy single-linkage style clustering by TF-IDF cosine."""
    if not points:
        return []
    idf = build_idf(points)
    vectors = [tfidf_vec(p["tokens"], idf) for p in points]
    clusters: list[list[int]] = []
    centroids: list[dict[str, float]] = []

    for i, vec in enumerate(vectors):
        best_j = -1
        best_sim = threshold
        for j, cen in enumerate(centroids):
            sim = cosine(vec, cen)
            if sim >= best_sim:
                best_sim = sim
                best_j = j
        if best_j < 0:
            clusters.append([i])
            centroids.append(dict(vec))
        else:
            clusters[best_j].append(i)
            # update centroid as mean of member vectors
            members = clusters[best_j]
            acc: dict[str, float] = defaultdict(float)
            for mi in members:
                for k, v in vectors[mi].items():
                    acc[k] += v
            n = len(members)
            centroids[best_j] = {k: v / n for k, v in acc.items()}

    return [[points[i] for i in idxs] for idxs in clusters]


def theme_title(cluster: list[dict]) -> str:
    # Prefer most common non-stop bigrams / longest claim snippet
    bag: Counter[str] = Counter()
    for p in cluster:
        toks = p["tokens"]
        for i in range(len(toks) - 1):
            bag[toks[i] + toks[i + 1]] += 1
        for t in toks:
            bag[t] += 1
    if bag:
        top = bag.most_common(1)[0][0]
        if len(top) >= 4:
            return top[:24]
    claim = cluster[0]["claim"]
    return (claim[:20] + "…") if len(claim) > 20 else claim


def build_outline(
    points: list[dict],
    cards: list[dict],
    manifest: list[dict],
    threshold: float,
) -> dict:
    clusters = cluster_points(points, threshold=threshold)
    # Sort themes by size desc
    clusters.sort(key=len, reverse=True)

    themes: list[dict] = []
    used_docs: set[str] = set()
    for ti, cluster in enumerate(clusters, start=1):
        support: list[str] = []
        seen_c: set[str] = set()
        docs: set[str] = set()
        for p in cluster:
            docs.add(p["doc_id"])
            used_docs.add(p["doc_id"])
            for c in p["citations"]:
                if c not in seen_c:
                    seen_c.add(c)
                    support.append(c)
        themes.append(
            {
                "theme_id": f"t{ti:02d}",
                "title": theme_title(cluster),
                "point_count": len(cluster),
                "doc_ids": sorted(docs),
                "support_citations": support[:40],
                "points": [
                    {
                        "id": p["id"],
                        "claim": p["claim"],
                        "doc_id": p["doc_id"],
                        "citations": p["citations"],
                        "kind": p["kind"],
                        "has_data": p["has_data"],
                    }
                    for p in cluster
                ],
            }
        )

    ok_docs = {m["doc_id"] for m in manifest if m.get("status") == "ok"}
    card_docs = {c.get("doc_id") for c in cards if c.get("doc_id")}
    coverage_docs = used_docs & ok_docs
    missing_cards = sorted(ok_docs - card_docs)
    unused_in_outline = sorted(ok_docs - used_docs)

    return {
        "theme_count": len(themes),
        "themes": themes,
        "coverage_preview": {
            "docs_ok": len(ok_docs),
            "docs_with_cards": len(card_docs & ok_docs),
            "docs_in_outline": len(coverage_docs),
            "coverage_ratio": round(len(coverage_docs) / len(ok_docs), 4) if ok_docs else 0.0,
            "missing_cards": missing_cards,
            "unused_in_outline": unused_in_outline,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge cards into thematic outline")
    parser.add_argument("--work-dir", default=None)
    parser.add_argument("--cards", default=None)
    parser.add_argument("--chunks", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--threshold", type=float, default=0.28)
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    work = Path(args.work_dir) if args.work_dir else cwd / WORK_REL
    if not work.is_absolute():
        work = (cwd / work).resolve()

    cards_dir = Path(args.cards) if args.cards else work / "cards"
    if not cards_dir.is_absolute():
        cards_dir = (cwd / cards_dir).resolve()
    chunks_path = Path(args.chunks) if args.chunks else work / "chunks.jsonl"
    if not chunks_path.is_absolute():
        chunks_path = (cwd / chunks_path).resolve()
    manifest_path = Path(args.manifest) if args.manifest else work / "manifest.jsonl"
    if not manifest_path.is_absolute():
        manifest_path = (cwd / manifest_path).resolve()
    out_path = Path(args.output) if args.output else work / "outline.json"
    if not out_path.is_absolute():
        out_path = (cwd / out_path).resolve()

    cards = load_cards(cards_dir)
    if not cards:
        print(f"ERROR: no cards in {cards_dir}", file=sys.stderr)
        return 1

    points = extract_points(cards)
    if not points:
        print("ERROR: cards contain no points", file=sys.stderr)
        return 1

    manifest = load_jsonl(manifest_path)
    # chunks loaded for future validation; presence checked
    _ = load_jsonl(chunks_path)

    outline = build_outline(points, cards, manifest, threshold=args.threshold)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")

    preview = outline["coverage_preview"]
    summary = {
        "ok": True,
        "output": str(out_path),
        "theme_count": outline["theme_count"],
        "point_count": len(points),
        "card_count": len(cards),
        "coverage_ratio": preview["coverage_ratio"],
        "missing_cards": preview["missing_cards"],
        "unused_in_outline": preview["unused_in_outline"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
