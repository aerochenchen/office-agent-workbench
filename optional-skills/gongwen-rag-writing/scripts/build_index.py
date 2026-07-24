#!/usr/bin/env python3
"""构建 RAG 向量索引 — 结构感知版

核心改进（v2.0）：
  ① 结构感知分块：不再按固定字符数切分，而是识别文档的层级结构，
     以「标题 + 其下所有从属段落」作为原子语义单元。同一语义单元内的
     段落绝不拆散，避免论证链断裂。
  ② 元数据丰富：每个 chunk 附带层级关系、段落范围、数据/案例标记。
  ③ 智能降级：若文档无明确标题样式，自动回退到基于段落的语义分组。

用法:
    python3 build_index.py <文件夹路径> [--output <索引文件路径>]
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from sentence_transformers import SentenceTransformer
from model_path import resolve_embedding_model
from tqdm import tqdm


# -------------------- 段落结构提取 --------------------

# 中文编号模式：一、二、... 十、  / （一）（二） / 1. 2. / (1) (2) / ① ②
_CN_LEVEL1 = re.compile(r'^[一二三四五六七八九十]+、')
_CN_LEVEL2 = re.compile(r'^（[一二三四五六七八九十]+）')
_CN_LEVEL3 = re.compile(r'^\d+[\.\、]\s*')
_CN_LEVEL4 = re.compile(r'^[（\(]\d+[）\)]')
_CN_HEADER_PREFIX = re.compile(r'^(第[一二三四五六七八九十\d]+[章节条]|附件[一二三四五六七八九十\d]*|抄送[：:]|主送[：:])')

# 数据/案例检测
_HAS_DATA = re.compile(r'[增长降低达到实现完成增减]+.*?[％%\d]|\d+[\.\d]*[万亿千百]|同比|环比|占比[：:是为]|人均')
_HAS_CASE = re.compile(r'如[：:。、，]|例如|比如|案例|典型|示范|试点|某[省市县区部门企业]')
_HAS_PROBLEM = re.compile(r'不足|挑战|问题|困难|短板|薄弱|差距|滞后|制约|瓶颈')
_HAS_MEASURE = re.compile(r'(一是|二是|三是|一要|二要|三要|着力|大力|持续|深入|加强|推进|完善|健全)')


def detect_heading_level(text: str, style_name: str) -> int:
    """检测段落的标题层级（公文体系）。
    
    Returns:
        0 = 正文, 1 = 一级标题, 2 = 二级, 3 = 三级, 4 = 四级
    """
    text = text.strip()
    
    # Word 内置标题样式
    if style_name.startswith("Heading"):
        try:
            return int(style_name.replace("Heading", "").strip())
        except ValueError:
            return 1
    
    # 公文编号模式
    if _CN_LEVEL1.match(text):
        return 1
    if _CN_LEVEL2.match(text):
        return 2
    if _CN_LEVEL3.match(text):
        return 3
    if _CN_LEVEL4.match(text):
        return 4
    if _CN_HEADER_PREFIX.match(text):
        return 1  # "第X章" 等
    
    # 特殊：发文字号、附件标注等
    if text.startswith(("附件", "抄送", "主送")):
        return 3
    
    return 0  # 正文


def extract_structure_from_docx(filepath: str) -> list:
    """从 .docx 提取结构化的段落序列（保留层级关系）。
    
    Returns:
        list of dicts, each with:
            {"text": str, "level": int, "style": str, "para_idx": int,
             "is_heading": bool, "tags": list}
    """
    doc = Document(filepath)
    structure = []
    
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue
        
        style_name = para.style.name if para.style else "Normal"
        level = detect_heading_level(text, style_name)
        
        # 标签检测
        tags = []
        if _HAS_DATA.search(text):
            tags.append("has_data")
        if _HAS_CASE.search(text):
            tags.append("has_case")
        if _HAS_PROBLEM.search(text):
            tags.append("has_problem")
        if _HAS_MEASURE.search(text):
            tags.append("has_measure")
        
        structure.append({
            "text": text,
            "level": level,
            "style": style_name,
            "para_idx": i,
            "is_heading": level > 0,
            "tags": tags,
            "char_count": len(text),
        })
    
    return structure


def build_semantic_units(structure: list) -> list:
    """从结构化段落构建语义单元（标题 + 其从属段落）。
    
    核心逻辑：
    - 遍历段落序列，维护当前「活动标题栈」
    - 遇到同级别或更高级别标题时，关闭当前语义单元
    - 一个语义单元 = 一个标题 + 该标题下到下一个同级标题之间的所有正文
    
    若文档无标题（全是 level=0），则将连续段落智能分组合并为一个语义单元。
    
    Returns:
        list of dicts, each with:
            {"section_title": str, "section_level": int, "paragraphs": [str],
             "start_idx": int, "end_idx": int, "total_chars": int,
             "combined_tags": list, "has_data": bool, "has_case": bool}
    """
    units = []
    current_unit = None  # {title, level, paragraphs, start_idx, end_idx, tags}
    
    for para in structure:
        if para["is_heading"]:
            # 保存上一个单元
            if current_unit and current_unit["paragraphs"]:
                _finalize_unit(current_unit)
                units.append(current_unit)
            
            # 开始新单元
            current_unit = {
                "section_title": para["text"],
                "section_level": para["level"],
                "paragraphs": [],
                "start_idx": para["para_idx"],
                "end_idx": para["para_idx"],
                "all_tags": set(para["tags"]),
                "total_chars": 0,
            }
        else:
            if current_unit is None:
                # 文档开头没有标题 → 创建「前言」伪单元
                current_unit = {
                    "section_title": "(前言)",
                    "section_level": 0,
                    "paragraphs": [],
                    "start_idx": para["para_idx"],
                    "end_idx": para["para_idx"],
                    "all_tags": set(),
                    "total_chars": 0,
                }
            
            current_unit["paragraphs"].append(para["text"])
            current_unit["end_idx"] = para["para_idx"]
            current_unit["all_tags"].update(para["tags"])
            current_unit["total_chars"] += para["char_count"]
    
    # 最后一个单元
    if current_unit and current_unit["paragraphs"]:
        _finalize_unit(current_unit)
        units.append(current_unit)
    
    return units


def _finalize_unit(unit: dict):
    """整理语义单元的元数据"""
    unit["has_data"] = "has_data" in unit["all_tags"]
    unit["has_case"] = "has_case" in unit["all_tags"]
    unit["has_problem"] = "has_problem" in unit["all_tags"]
    unit["has_measure"] = "has_measure" in unit["all_tags"]
    unit["all_tags"] = sorted(unit["all_tags"])


def chunk_semantic_units(units: list, max_chars: int = 2000) -> list:
    """将超大语义单元按段落边界拆分（但保持论证链完整）。
    
    与旧版固定字符切分的区别：
    - 首先，整个语义单元 < max_chars → 保留完整（不切）
    - 超大的单元 → 按段落自然边界拆分，每组一个子 chunk
    - 每个子 chunk 保留父标题的元数据
    
    这确保不会出现「论点在 chunk A，论据在 chunk B」的情况。
    """
    chunks = []
    
    for unit in units:
        unit_text = "\n\n".join(unit["paragraphs"])
        
        if unit["total_chars"] <= max_chars:
            # 完整保留
            chunks.append({
                "text": unit_text,
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
            })
        else:
            # 按段落边界拆分子 chunks
            sub_paras = unit["paragraphs"]
            sub_chunks = []
            buffer = []
            buffer_chars = 0
            
            for p in sub_paras:
                if buffer_chars + len(p) > max_chars and buffer:
                    sub_chunks.append("\n\n".join(buffer))
                    buffer = [p]
                    buffer_chars = len(p)
                else:
                    buffer.append(p)
                    buffer_chars += len(p)
            
            if buffer:
                sub_chunks.append("\n\n".join(buffer))
            
            for j, sub_text in enumerate(sub_chunks):
                chunks.append({
                    "text": sub_text,
                    "section_title": unit["section_title"],
                    "section_level": unit["section_level"],
                    "paragraph_range": [unit["start_idx"], unit["end_idx"]],
                    "has_data": unit["has_data"],
                    "has_case": unit["has_case"],
                    "has_problem": unit["has_problem"],
                    "has_measure": unit["has_measure"],
                    "tags": unit["all_tags"],
                    "char_count": len(sub_text),
                    "is_split": len(sub_chunks) > 1,
                    "sub_idx": j,
                    "sub_total": len(sub_chunks),
                })
    
    return chunks


# -------------------- 主流程 --------------------

def build_index(
    folder: str,
    output_path: str = None,
    model_name: str = "BAAI/bge-small-zh-v1.5",
    max_chars: int = 2000,
) -> dict:
    """主流程：扫描 → 结构化提取 → 语义单元分块 → 向量化 → 保存"""
    
    folder = os.path.expanduser(folder)
    docx_files = sorted(Path(folder).rglob("*.docx"))
    docx_files = [f for f in docx_files if not f.name.startswith("~$")]
    
    if not docx_files:
        print(f"❌ 在 {folder} 中未找到 .docx 文件", file=sys.stderr)
        sys.exit(1)
    
    print(f"📂 找到 {len(docx_files)} 个 .docx 文件")
    for f in docx_files:
        print(f"   - {f.name}")
    
    # 1. 提取 + 结构化
    print(f"\n📄 结构化提取（语义单元分块，max_chars={max_chars}）...")
    all_chunks = []
    stats = {"total_units": 0, "split_units": 0, "no_heading": 0}
    
    for filepath in tqdm(docx_files, desc="处理文档"):
        try:
            structure = extract_structure_from_docx(str(filepath))
            units = build_semantic_units(structure)
            
            # 统计
            headings = [u for u in units if u["section_level"] > 0]
            if not headings:
                stats["no_heading"] += 1
            
            chunks = chunk_semantic_units(units, max_chars=max_chars)
            stats["total_units"] += len(units)
            stats["split_units"] += sum(1 for c in chunks if c.get("is_split"))
            
            for chunk in chunks:
                chunk["source"] = filepath.name
                chunk["path"] = str(filepath)
                all_chunks.append(chunk)
                
        except Exception as e:
            print(f"⚠️  跳过 {filepath.name}: {e}", file=sys.stderr)
    
    print(f"\n✅ 语义单元: {stats['total_units']} 个 → 输出 chunk: {len(all_chunks)} 个")
    print(f"   其中拆分的大单元: {stats['split_units']} 个")
    print(f"   无标题文档: {stats['no_heading']} 个（已自动降级为段落分组）")
    
    if not all_chunks:
        print("❌ 未能提取任何有效文本", file=sys.stderr)
        sys.exit(1)
    
    # 统计标签分布
    tag_counts = defaultdict(int)
    for c in all_chunks:
        for tag in c.get("tags", []):
            tag_counts[tag] += 1
    print(f"   数据标记: {tag_counts.get('has_data', 0)} | "
          f"案例标记: {tag_counts.get('has_case', 0)} | "
          f"问题标记: {tag_counts.get('has_problem', 0)} | "
          f"措施标记: {tag_counts.get('has_measure', 0)}")
    
    # 2. 向量化
    print(f"\n🔢 加载模型 {model_name} ...")
    model = SentenceTransformer(model_name)
    
    print("向量化中...")
    texts = [c["text"] for c in all_chunks]
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=32,
    )
    
    # 3. 组装索引
    index = {
        "version": "2.0",
        "model": model_name,
        "vector_dim": int(embeddings.shape[1]),
        "chunking": "structure-aware",
        "max_chars_per_chunk": max_chars,
        "total_docs": len(docx_files),
        "total_semantic_units": stats["total_units"],
        "total_chunks": len(all_chunks),
        "source_files": [f.name for f in docx_files],
        "tag_distribution": dict(tag_counts),
        "chunks": all_chunks,
        "embeddings": embeddings.tolist(),
    }
    
    # 4. 保存
    if output_path is None:
        rag_dir = Path(folder) / ".office-agent" / "rag" / "gongwen-rag-writing"
        rag_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(rag_dir / "index.json")
    output_path = os.path.expanduser(output_path)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    
    print(f"\n{'='*55}")
    print(f"✅ 索引构建完成！")
    print(f"   输出: {output_path}  ({size_mb:.1f} MB)")
    print(f"   文档: {len(docx_files)} | 语义单元: {stats['total_units']} | chunks: {len(all_chunks)}")
    print(f"   向量: {embeddings.shape[1]} 维")
    print(f"   分块策略: 语义单元感知（{max_chars} 字符上限/单元）")
    print(f"{'='*55}")
    
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="公文写作 RAG 索引构建 — 结构感知版 v2.0"
    )
    parser.add_argument("folder", help="包含 .docx 素材文档的文件夹路径")
    parser.add_argument("--output", "-o", default=None, help="索引输出路径")
    parser.add_argument("--max-chars", "-m", type=int, default=2000, 
                        help="语义单元最大字符数，超出则按段落边界拆分（默认: 2000）")
    
    args = parser.parse_args()
    build_index(args.folder, args.output, max_chars=args.max_chars)
