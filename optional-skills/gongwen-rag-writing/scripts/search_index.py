#!/usr/bin/env python3
"""语义检索 RAG 索引

从已构建的向量索引中，用 BGE-small-zh-v1.5 检索与查询最相关的文本块。

用法:
    python3 search_index.py <索引文件> <查询文本> [--top-k 5] [--min-score 0.3]
    
示例:
    python3 search_index.py ~/Desktop/素材/rag_index.json "技术创新进展" --top-k 10
"""

import argparse
import json
import sys

import numpy as np
from sentence_transformers import SentenceTransformer
from model_path import resolve_embedding_model


def load_index(index_path: str) -> dict:
    """加载索引文件"""
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def search(index: dict, query: str, model: SentenceTransformer, 
           top_k: int = 5, min_score: float = 0.0) -> list:
    """在索引中搜索最相关的文本块
    
    Returns:
        list of dicts: [{text, source, score, chunk_idx, char_count}, ...]
    """
    embeddings = np.array(index["embeddings"])
    
    # 向量化查询（BGE 需要加 query prefix 以获得更好效果）
    query_vec = model.encode(
        query, 
        normalize_embeddings=True,
        prompt="为这个句子生成表示以用于检索相关文章："  # BGE 推荐格式
    )
    
    # 计算余弦相似度（因为已归一化，直接点积即可）
    scores = np.dot(embeddings, query_vec)
    
    # 取 top-k
    top_indices = np.argsort(scores)[::-1][:top_k]
    
    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score < min_score:
            continue
        chunk = index["chunks"][idx]
        results.append({
            "text": chunk["text"],
            "source": chunk["source"],
            "path": chunk["path"],
            "chunk_idx": chunk["chunk_idx"],
            "char_count": chunk["char_count"],
            "score": round(score, 4),
        })
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="语义检索公文素材 RAG 索引"
    )
    parser.add_argument("index", help="索引 JSON 文件路径")
    parser.add_argument("query", help="检索查询文本")
    parser.add_argument("--top-k", "-k", type=int, default=5, help="返回结果数（默认: 5）")
    parser.add_argument("--min-score", "-s", type=float, default=0.3, 
                        help="最低相似度阈值（默认: 0.3）")
    parser.add_argument("--json", "-j", action="store_true", 
                        help="以 JSON 格式输出（供脚本/agent 解析）")
    
    args = parser.parse_args()
    
    # 加载索引
    index = load_index(args.index)
    
    # 加载模型
    model_name = resolve_embedding_model(index.get("model", "BAAI/bge-small-zh-v1.5"))
    model = SentenceTransformer(model_name)
    
    # 搜索
    results = search(index, args.query, model, args.top_k, args.min_score)
    
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"\n🔍 查询: {args.query}")
        print(f"📊 结果: {len(results)}/{args.top_k} (min_score={args.min_score})")
        print("=" * 60)
        
        for i, r in enumerate(results, 1):
            print(f"\n【结果 {i}】 相似度: {r['score']:.4f}  |  来源: {r['source']}")
            print(f"  ─────────────────────────────────────────────")
            # 截断过长文本
            text = r['text']
            if len(text) > 500:
                text = text[:500] + " ... [截断]"
            print(f"  {text}")
            print()
        
        print("=" * 60)
        print(f"索引信息: {index['total_docs']} 个文档, {index['total_chunks']} 个文本块")


if __name__ == "__main__":
    main()
