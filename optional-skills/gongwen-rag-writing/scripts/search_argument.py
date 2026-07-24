#!/usr/bin/env python3
"""论证驱动多角度检索

核心改进（v2.0）：
  不再用单个「章节标题」做检索，而是根据该章节的「论证需求」，
  从多个角度并行检索，然后将结果按论证角色组织。

典型用法：
  # 方式1：命令行多查询
  python3 search_argument.py <索引> \
    "成绩:技术创新 突破 成果" \
    "数据:研发投入 专利 增长率" \
    "案例:典型企业 示范项目" \
    "问题:短板 不足 差距" \
    --top-k 5 --json

  # 方式2：从 JSON 文件读取论证计划
  python3 search_argument.py <索引> --plan <论证计划.json> --json

论证计划 JSON 格式:
  {
    "chapter": "三、技术创新进展",
    "queries": [
      {"role": "成绩", "query": "技术创新 突破 成果 进展", "weight": 1.5},
      {"role": "数据", "query": "研发投入 专利 增长率 占比", "weight": 1.2},
      {"role": "案例", "query": "典型企业 示范项目 成功经验", "weight": 1.0},
      {"role": "问题", "query": "短板 不足 差距 瓶颈", "weight": 0.8}
    ]
  }
"""

import argparse
import json
import sys
from collections import defaultdict

import numpy as np
from sentence_transformers import SentenceTransformer
from model_path import resolve_embedding_model


def load_index(index_path: str) -> dict:
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def search_single(index: dict, query: str, model: SentenceTransformer,
                  top_k: int = 5) -> list:
    """单次语义检索，返回带分数的结果列表"""
    embeddings = np.array(index["embeddings"])
    
    query_vec = model.encode(
        query,
        normalize_embeddings=True,
        prompt="为这个句子生成表示以用于检索相关文章："
    )
    
    scores = np.dot(embeddings, query_vec)
    top_indices = np.argsort(scores)[::-1][:top_k]
    
    results = []
    for idx in top_indices:
        score = float(scores[idx])
        chunk = index["chunks"][idx]
        results.append({
            "text": chunk["text"],
            "source": chunk.get("source", ""),
            "path": chunk.get("path", ""),
            "section_title": chunk.get("section_title", ""),
            "section_level": chunk.get("section_level", 0),
            "has_data": chunk.get("has_data", False),
            "has_case": chunk.get("has_case", False),
            "has_problem": chunk.get("has_problem", False),
            "has_measure": chunk.get("has_measure", False),
            "tags": chunk.get("tags", []),
            "score": round(score, 4),
            "char_count": chunk.get("char_count", len(chunk["text"])),
            "chunk_idx": int(idx),
        })
    
    return results


def argument_search(
    index: dict,
    queries: list,
    model: SentenceTransformer,
    top_k: int = 5,
    min_score: float = 0.2,
) -> dict:
    """多角度论证驱动检索。
    
    Args:
        index: 已加载的索引
        queries: [{"role": "成绩", "query": "...", "weight": 1.5}, ...]
        model: BGE 模型
        top_k: 每个角度的返回数
        min_score: 最低分数阈值
    
    Returns:
        {"results_by_role": {...}, "merged": [...], "stats": {...}}
    """
    results_by_role = {}
    all_by_chunk_idx = {}  # chunk_idx -> {score, roles, ...} 用于去重
    
    for q in queries:
        role = q.get("role", "未命名")
        query_text = q.get("query", "")
        weight = q.get("weight", 1.0)
        
        if not query_text:
            continue
        
        raw_results = search_single(index, query_text, model, top_k=top_k)
        
        # 过滤低分
        filtered = [r for r in raw_results if r["score"] >= min_score]
        
        # 标签奖励：如果查询角色与 chunk 标签匹配，加分
        for r in filtered:
            tag_bonus = 0.0
            if role == "数据" and r.get("has_data"):
                tag_bonus = 0.05
            elif role == "案例" and r.get("has_case"):
                tag_bonus = 0.05
            elif role == "问题" and r.get("has_problem"):
                tag_bonus = 0.05
            elif role == "措施" and r.get("has_measure"):
                tag_bonus = 0.05
            
            r["adjusted_score"] = round(r["score"] * weight + tag_bonus, 4)
        
        # 按调整后分数排序
        filtered.sort(key=lambda x: x["adjusted_score"], reverse=True)
        
        results_by_role[role] = filtered
        
        # 合并到全局去重表
        for r in filtered:
            cid = r["chunk_idx"]
            if cid not in all_by_chunk_idx:
                all_by_chunk_idx[cid] = {
                    **r,
                    "roles": [role],
                    "best_score": r["adjusted_score"],
                }
            else:
                existing = all_by_chunk_idx[cid]
                if role not in existing["roles"]:
                    existing["roles"].append(role)
                existing["best_score"] = max(existing["best_score"], r["adjusted_score"])
    
    # 合并结果：去重 + 按 best_score 排序
    merged = sorted(all_by_chunk_idx.values(), 
                    key=lambda x: x["best_score"], reverse=True)
    
    # 统计
    stats = {
        "total_roles": len(results_by_role),
        "total_raw": sum(len(v) for v in results_by_role.values()),
        "total_unique": len(merged),
        "roles_distribution": {role: len(items) for role, items in results_by_role.items()},
    }
    
    return {
        "results_by_role": results_by_role,
        "merged": merged,
        "stats": stats,
    }


def parse_cli_queries(args_queries: list) -> list:
    """解析命令行传入的 '角色:查询文本' 格式"""
    queries = []
    for q in args_queries:
        if ":" in q:
            role, query = q.split(":", 1)
            queries.append({"role": role.strip(), "query": query.strip(), "weight": 1.0})
        else:
            queries.append({"role": "默认", "query": q.strip(), "weight": 1.0})
    return queries


def main():
    parser = argparse.ArgumentParser(
        description="论证驱动多角度检索 — 公文写作 RAG v2.0"
    )
    parser.add_argument("index", help="索引 JSON 文件路径")
    parser.add_argument("queries", nargs="*", 
                        help="'角色:查询文本' 对，如 '成绩:技术创新 突破'")
    parser.add_argument("--plan", "-p", default=None, 
                        help="论证计划 JSON 文件（与命令行 queries 互斥）")
    parser.add_argument("--top-k", "-k", type=int, default=5, 
                        help="每个角度返回数（默认: 5）")
    parser.add_argument("--min-score", "-s", type=float, default=0.2,
                        help="最低相似度阈值（默认: 0.2）")
    parser.add_argument("--json", "-j", action="store_true",
                        help="JSON 输出（供 Agent 解析）")
    parser.add_argument("--max-chars", "-c", type=int, default=600,
                        help="终端显示时每块截断字符数（默认: 600）")
    
    args = parser.parse_args()
    
    # 解析查询
    if args.plan:
        with open(args.plan, "r", encoding="utf-8") as f:
            plan = json.load(f)
        chapter = plan.get("chapter", "未命名章节")
        queries = plan.get("queries", [])
    elif args.queries:
        chapter = "命令行查询"
        queries = parse_cli_queries(args.queries)
    else:
        print("❌ 请提供查询参数或 --plan 文件", file=sys.stderr)
        sys.exit(1)
    
    if not queries:
        print("❌ 无有效查询", file=sys.stderr)
        sys.exit(1)
    
    # 加载
    index = load_index(args.index)
    model = SentenceTransformer(resolve_embedding_model(index.get("model", "BAAI/bge-small-zh-v1.5")))
    
    # 检索
    result = argument_search(index, queries, model, args.top_k, args.min_score)
    
    if args.json:
        # JSON 输出（完整结果，不截断）
        print(json.dumps({
            "chapter": chapter,
            "results_by_role": _simplify_for_json(result["results_by_role"]),
            "merged": _simplify_for_json(result["merged"]),
            "stats": result["stats"],
        }, ensure_ascii=False, indent=2))
    else:
        # 终端可读输出
        print(f"\n{'='*65}")
        print(f"📋 章节: {chapter}")
        print(f"📊 按论证角度检索: {', '.join(q['role'] for q in queries)}")
        print(f"{'='*65}")
        
        for role, items in result["results_by_role"].items():
            print(f"\n## 【{role}】({len(items)} 条)")
            print("-" * 50)
            for i, r in enumerate(items[:args.top_k], 1):
                text = r["text"]
                if len(text) > args.max_chars:
                    text = text[:args.max_chars] + " …"
                print(f"  [{i}] score={r['adjusted_score']:.4f} | {r['source']}")
                print(f"      {text[:200]}…" if len(r["text"]) > 200 else f"      {text}")
                if r.get("section_title"):
                    print(f"      📍 所属章节: {r['section_title']}")
                print()
        
        print(f"\n{'='*65}")
        print(f"📈 统计: 总计 {result['stats']['total_raw']} 条 → "
              f"去重后 {result['stats']['total_unique']} 个独立 chunk")
        print(f"   角色分布: {result['stats']['roles_distribution']}")
        print(f"{'='*65}")


def _simplify_for_json(items):
    """简化输出，去掉冗余字段"""
    if isinstance(items, list):
        return [{
            "text": i["text"],
            "source": i.get("source", ""),
            "section_title": i.get("section_title", ""),
            "score": i.get("adjusted_score", i.get("score", 0)),
            "roles": i.get("roles", []),
            "has_data": i.get("has_data", False),
            "has_case": i.get("has_case", False),
            "tags": i.get("tags", []),
        } for i in items]
    elif isinstance(items, dict):
        return {k: _simplify_for_json(v) for k, v in items.items()}
    return items


if __name__ == "__main__":
    main()
