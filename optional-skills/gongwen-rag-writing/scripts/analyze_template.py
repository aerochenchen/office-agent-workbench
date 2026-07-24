#!/usr/bin/env python3
"""分析模板报告结构 — 深度版 v2.0

核心改进：
  ③ 跨章节叙事线索检测：识别章节间的过渡、呼应、铺垫关系
  ⑤ 文体特征分析：句长分布、修辞密度、语气标记、信息密度节奏

用法:
    python3 analyze_template.py <模板文件.docx> [--json] [--narrative]
"""

import argparse
import json
import sys
import re
from collections import Counter, defaultdict

from docx import Document


# -------------------- 段落分类 --------------------

# 中文编号模式
_CN_LEVEL1 = re.compile(r'^[一二三四五六七八九十]+、')
_CN_LEVEL2 = re.compile(r'^（[一二三四五六七八九十]+）')
_CN_LEVEL3 = re.compile(r'^\d+[\.\、]\s*')
_CN_LEVEL4 = re.compile(r'^[（\(]\d+[）\)]')

# 句式模式（扩展版）
_PATTERNS = {
    "总结开头": re.compile(r'^(总体来看|总的看|综上所述|一年来|过去一年|回顾)'),
    "数据表述": re.compile(r'[增长降低达到实现完成增减]+.*?[％%\d]|\d+[\.\d]*[万亿千百]|同比|环比|占比[：:是为]'),
    "措施表述": re.compile(r'^(一是|二是|三是|一要|二要|三要|着力|大力|持续|深入|进一步|切实)'),
    "问题表述": re.compile(r'(不足|挑战|问题|困难|短板|薄弱|差距|滞后|制约|瓶颈)'),
    "展望开头": re.compile(r'^(下一步|今后|明年|未来|接下来|下阶段|新的一年)'),
    "排比结构": re.compile(r'(坚持|着力|推进|加强|完善|健全|深化).+?[，,].+?[，,].+?[。；;]'),
    "转折过渡": re.compile(r'(但|然而|虽然|尽管|不过|与此同|另一方)'),
    "因果推理": re.compile(r'(因此|所以|由于|因为|从而|进而|为此)'),
}

# 跨章节关系检测
_CROSS_SECTION = {
    "递进": re.compile(r'(进一步|更加|更深|更高|更强|持续|不断)'),
    "呼应上文": re.compile(r'(如上所述|前述|上述|前面提到|前文)'),
    "补充说明": re.compile(r'(此外|另外|同时|与此同|值得注意|需要说明)'),
    "对比转折": re.compile(r'(与此(相反|对应)|反观|而|相比于|较之)'),
}

# 语气强度标记
_TONE_MARKERS = {
    "强义务": re.compile(r'(必须|务必|坚决|严格|一律|不得|禁止|严禁)'),
    "弱义务": re.compile(r'(应当|应该|要|需要|须|可)'),
    "建议性": re.compile(r'(建议|提倡|鼓励|引导|推动|促进)'),
    "陈述性": re.compile(r'(是|为|已|共|均|分别|累计)'),
}


def classify_paragraph(para) -> dict:
    """分类段落并提取多层次特征"""
    text = para.text.strip()
    if not text:
        return None

    style_name = para.style.name if para.style else "Normal"
    alignment = str(para.alignment) if para.alignment else "LEFT"

    # 字体信息
    font_info = {}
    if para.runs:
        run = para.runs[0]
        font_info = {
            "font_name": run.font.name,
            "font_size": str(run.font.size) if run.font.size else None,
            "bold": run.font.bold,
        }

    result = {
        "text": text,
        "style": style_name,
        "alignment": alignment,
        "font": font_info,
        "char_count": len(text),
        "sentence_count": len(re.split(r'[。！？；]', text)),
    }

    # 层级判断
    if _CN_LEVEL1.match(text):
        result["level"] = "一级标题"
    elif _CN_LEVEL2.match(text):
        result["level"] = "二级标题"
    elif _CN_LEVEL3.match(text):
        result["level"] = "三级标题"
    elif _CN_LEVEL4.match(text):
        result["level"] = "四级标题"
    elif "Heading" in style_name:
        result["level"] = "标题"
    elif re.match(r'^(附件|抄送|主送)', text):
        result["level"] = "版记/附件"
    else:
        result["level"] = "正文"

    # 句式模式
    patterns_found = []
    for name, pat in _PATTERNS.items():
        if pat.search(text):
            patterns_found.append(name)
    result["patterns"] = patterns_found

    # 跨章节信号
    cross_signals = []
    for name, pat in _CROSS_SECTION.items():
        if pat.search(text):
            cross_signals.append(name)
    result["cross_section_signals"] = cross_signals

    # 语气标记
    tone_tags = []
    for name, pat in _TONE_MARKERS.items():
        if pat.search(text):
            tone_tags.append(name)
    result["tone_tags"] = tone_tags

    return result


# -------------------- 深层分析函数 --------------------

def analyze_sentence_length(all_paras: list) -> dict:
    """句长分布分析"""
    all_lengths = []
    for p in all_paras:
        if p["level"] == "正文":
            # 按句号分句
            sentences = re.split(r'[。！？]', p["text"])
            for s in sentences:
                s = s.strip()
                if s:
                    all_lengths.append(len(s))

    if not all_lengths:
        return {"avg": 0, "median": 0, "distribution": {}}

    all_lengths.sort()
    n = len(all_lengths)

    # 分桶
    buckets = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0, "100+": 0}
    for l in all_lengths:
        if l <= 20: buckets["0-20"] += 1
        elif l <= 40: buckets["21-40"] += 1
        elif l <= 60: buckets["41-60"] += 1
        elif l <= 80: buckets["61-80"] += 1
        elif l <= 100: buckets["81-100"] += 1
        else: buckets["100+"] += 1

    return {
        "avg": round(sum(all_lengths) / n, 1),
        "median": all_lengths[n // 2],
        "min": all_lengths[0],
        "max": all_lengths[-1],
        "style_hint": "短句为主，节奏快、有力" if sum(all_lengths) / n < 35
                      else "中长句为主，严谨、信息密度高" if sum(all_lengths) / n > 50
                      else "长短句混合，节奏灵活",
        "distribution": buckets,
        "total_sentences": n,
    }


def analyze_rhetoric_density(all_paras: list) -> dict:
    """修辞手法密度分析"""
    total_body_paras = [p for p in all_paras if p["level"] == "正文"]
    if not total_body_paras:
        return {}

    total = len(total_body_paras)

    counts = defaultdict(int)
    for p in total_body_paras:
        for pat in p["patterns"]:
            counts[pat] += 1

    return {
        "总正文段数": total,
        "排比密度": f"{counts['排比结构']}/{total} ({counts['排比结构']/total*100:.1f}%)",
        "转折密度": f"{counts['转折过渡']}/{total} ({counts['转折过渡']/total*100:.1f}%)",
        "数据密度": f"{counts['数据表述']}/{total} ({counts['数据表述']/total*100:.1f}%)",
        "格式化数据": {
            "每段平均数据出现次数": round(counts["数据表述"] / total, 2),
            "数据段落占比": f"{counts['数据表述']/total*100:.1f}%",
        }
    }


def analyze_tone(all_paras: list) -> dict:
    """语气/态度分析"""
    body = [p for p in all_paras if p["level"] == "正文"]
    if not body:
        return {}

    marker_counts = Counter()
    for p in body:
        for tag in p.get("tone_tags", []):
            marker_counts[tag] += 1

    total = len(body)
    return {
        "总正文段": total,
        "语气分布": {k: f"{v}/{total} ({v/total*100:.1f}%)" for k, v in marker_counts.most_common()},
        "主导语气": marker_counts.most_common(1)[0][0] if marker_counts else "未检出",
        "语气解读": _interpret_tone(marker_counts),
    }


def _interpret_tone(counts: Counter) -> str:
    """解读语气组合"""
    strong = counts.get("强义务", 0)
    weak = counts.get("弱义务", 0)
    suggestion = counts.get("建议性", 0)
    statement = counts.get("陈述性", 0)

    if strong > weak + suggestion:
        return "偏强制执行风格（多用「必须」「严禁」）"
    elif suggestion > strong:
        return "偏引导鼓励风格（多用「建议」「推动」）"
    elif statement > weak + suggestion:
        return "偏客观陈述风格（多用「是」「已」）"
    else:
        return "混合风格，态度灵活"


def analyze_narrative_arc(all_paras: list) -> dict:
    """跨章节叙事弧线分析
    
    识别模板的叙事结构：
    - 章节间的递进/呼应/转折关系
    - 叙事阶段划分（回顾→成绩→问题→展望 等）
    - 每个章节的论证角色
    """
    # 提取章节序列
    sections = []
    current_section = None

    for p in all_paras:
        if p["level"] in ("一级标题", "二级标题", "标题"):
            if current_section:
                sections.append(current_section)
            current_section = {
                "title": p["text"][:80],
                "level": p["level"],
                "body_paras": [],
                "cross_signals": Counter(),
                "patterns": Counter(),
                "tone": Counter(),
                "total_chars": 0,
            }
        elif current_section is not None and p["level"] == "正文":
            current_section["body_paras"].append(p)
            current_section["total_chars"] += p["char_count"]
            for sig in p.get("cross_section_signals", []):
                current_section["cross_signals"][sig] += 1
            for pat in p.get("patterns", []):
                current_section["patterns"][pat] += 1
            for tag in p.get("tone_tags", []):
                current_section["tone"][tag] += 1

    if current_section:
        sections.append(current_section)

    if not sections:
        return {"error": "未检测到章节结构"}

    # 推断每个章节的论证角色
    for sec in sections:
        sec["inferred_role"] = _infer_section_role(sec)

    # 分析章节间关系
    relationships = []
    for i in range(len(sections) - 1):
        rel = _detect_relationship(sections[i], sections[i + 1])
        relationships.append({
            "from": sections[i]["title"],
            "to": sections[i + 1]["title"],
            "relationship": rel,
        })

    # 推断叙事弧线类型
    arc_type = _infer_arc_type(sections)
    arc_description = _describe_arc(arc_type)

    return {
        "总章节数": len(sections),
        "章节序列": [s["title"] for s in sections],
        "叙事弧线类型": arc_type,
        "叙事弧线描述": arc_description,
        "章节论证角色": {s["title"]: s["inferred_role"] for s in sections},
        "章节间关系": relationships,
        "写作建议": _generate_writing_advice(sections, relationships),
    }


def _infer_section_role(section: dict) -> str:
    """根据内容特征推断章节的论证角色"""
    title = section["title"]
    patterns = section["patterns"]
    cross = section["cross_signals"]
    body_text = " ".join(p["text"] for p in section.get("body_paras", []))[:500]

    # 关键词推断
    if any(kw in title for kw in ["回顾", "总结", "概况", "总体", "过去"]):
        return "定调回顾 — 建立全文基调"
    if any(kw in title for kw in ["成效", "成绩", "进展", "成果", "亮点"]):
        return "成果展示 — 正面成绩展开"
    if any(kw in title for kw in ["问题", "不足", "挑战", "困难", "短板"]):
        return "问题剖析 — 转折与反思"
    if any(kw in title for kw in ["形势", "背景", "机遇", "环境"]):
        return "形势分析 — 拔高视野"
    if any(kw in title for kw in ["任务", "工作", "安排", "计划", "部署", "重点", "目标"]):
        return "行动部署 — 落地执行"
    if any(kw in title for kw in ["保障", "措施", "要求", "建议"]):
        return "保障措施 — 支撑条件"

    # 数据密集 → 可能是成果展示
    if patterns.get("数据表述", 0) > 5:
        return "成果展示 — 数据密集型"
    # 措施密集 → 行动部署
    if patterns.get("措施表述", 0) > 3:
        return "行动部署 — 措施密集型"
    # 问题密集 → 问题剖析
    if patterns.get("问题表述", 0) > 2:
        return "问题剖析 — 反思型"

    return "未确定 — 需人工判断"


def _detect_relationship(prev: dict, curr: dict) -> str:
    """检测两个相邻章节的关系"""
    signals = curr.get("cross_signals", {})

    if signals.get("递进", 0) >= 2:
        return "递进深化"
    if signals.get("呼应上文", 0) >= 1:
        return "呼应承上"
    if signals.get("对比转折", 0) >= 2:
        return "对比转折"
    if signals.get("补充说明", 0) >= 1:
        return "补充扩展"

    # 根据角色推断
    roles = (prev.get("inferred_role", ""), curr.get("inferred_role", ""))
    if "回顾" in roles[0] and "成果" in roles[1]:
        return "总结→展开"
    if "成果" in roles[0] and "问题" in roles[1]:
        return "转折（先扬后抑）"
    if "问题" in roles[0] and "部署" in roles[1]:
        return "问题导向→对策"
    if "分析" in roles[0] and "部署" in roles[1]:
        return "理论铺垫→实践落地"
    if "部署" in roles[0] and "保障" in roles[1]:
        return "主体→支撑"

    return "并列（无明显逻辑关系）"


def _infer_arc_type(sections: list) -> str:
    """推断叙事弧线类型"""
    roles = [s.get("inferred_role", "") for s in sections]

    if not roles:
        return "未检测到"

    # 经典工作报告弧线: 回顾→成绩→问题→部署
    has_review = any("回顾" in r for r in roles)
    has_achievement = any("成果" in r for r in roles)
    has_problem = any("问题" in r for r in roles)
    has_deployment = any("部署" in r for r in roles)
    has_analysis = any("分析" in r for r in roles)

    if has_review and has_achievement and has_problem and has_deployment:
        return "经典四段式（回顾→成绩→问题→部署）"
    if has_review and has_achievement and has_deployment:
        return "三段式（回顾→成绩→部署，无独立问题篇）"
    if has_analysis and has_deployment:
        return "分析驱动型（形势分析→行动部署）"

    return "自定义结构"


def _describe_arc(arc_type: str) -> str:
    """叙事弧线的写作含义"""
    descriptions = {
        "经典四段式（回顾→成绩→问题→部署）": (
            "最完整的公文叙事结构。第一节建立基调（「在XX领导下，取得显著成效」），"
            "第二节全面展开成绩（数据+案例），第三节适度转折（指出不足，体现客观理性），"
            "第四节提出对策（承上启下，问题导向）。写作时应确保第二节的每一项成绩"
            "在第四节有对应的延续措施，第三节的问题在第四节得到回应。"
        ),
        "三段式（回顾→成绩→部署，无独立问题篇）": (
            "简洁高效的结构。问题融入成绩段的末尾（「但也要看到……」），"
            "或分散到各部署段中（「针对……问题，下一步将……」）。"
            "写作时注意不要让报告显得报喜不报忧。"
        ),
        "分析驱动型（形势分析→行动部署）": (
            "偏战略性的结构。先分析外部环境和内部条件，再导出行动方案。"
            "写作时需要确保行动方案与分析中识别的机遇/挑战有明确对应关系。"
        ),
    }
    return descriptions.get(arc_type, "自定义结构，需根据具体章节关系灵活处理。")


def _generate_writing_advice(sections: list, relationships: list) -> list:
    """根据模板分析生成具体写作建议"""
    advice = []

    # 检查章节篇幅是否均衡
    char_counts = [s["total_chars"] for s in sections]
    if char_counts:
        avg = sum(char_counts) / len(char_counts)
        for i, s in enumerate(sections):
            ratio = s["total_chars"] / avg if avg > 0 else 1
            if ratio > 2.0:
                advice.append(f"⚠️ 「{s['title']}」篇幅偏长（{ratio:.1f}x 均值），"
                              f"写作时注意控制，避免失衡")
            elif ratio < 0.3:
                advice.append(f"⚠️ 「{s['title']}」篇幅偏短（{ratio:.1f}x 均值），"
                              f"可能需要充实内容")

    # 检查过渡
    for rel in relationships:
        if rel["relationship"] == "并列（无明显逻辑关系）":
            advice.append(f"💡 「{rel['from']}」→「{rel['to']}」之间缺少明显过渡，"
                          f"写作时建议加入承上启下句")
        if rel["relationship"] == "转折（先扬后抑）":
            advice.append(f"💡 「{rel['from']}」→「{rel['to']}」为扬→抑转折，"
                          f"注意过渡要自然，可用「在肯定成绩的同时，也要清醒看到……」")

    return advice


# -------------------- 主流程 --------------------

def analyze_template(filepath: str) -> dict:
    """深度分析模板文件"""
    doc = Document(filepath)

    outline = []
    all_paras = []
    level_counter = Counter()

    for para in doc.paragraphs:
        info = classify_paragraph(para)
        if info is None:
            continue
        all_paras.append(info)
        level_counter[info["level"]] += 1

        if info["level"] not in ("正文",):
            outline.append({
                "level": info["level"],
                "text": info["text"][:80] + ("..." if len(info["text"]) > 80 else ""),
                "style": info["style"],
                "font": info["font"],
                "cross_signals": info.get("cross_section_signals", []),
            })

    # 基础统计
    font_names = Counter()
    pattern_counter = Counter()
    for p in all_paras:
        if p.get("font", {}).get("font_name"):
            font_names[p["font"]["font_name"]] += 1
        for pat in p.get("patterns", []):
            pattern_counter[pat] += 1

    result = {
        "file": filepath,
        "total_paragraphs": len(all_paras),
        "total_chars": sum(p["char_count"] for p in all_paras),
        "level_distribution": dict(level_counter),
        "outline": outline,
        "top_fonts": font_names.most_common(5),
        "sentence_patterns": dict(pattern_counter),

        # 🔥 新增：文体特征
        "sentence_analysis": analyze_sentence_length(all_paras),
        "rhetoric_analysis": analyze_rhetoric_density(all_paras),
        "tone_analysis": analyze_tone(all_paras),

        # 🔥 新增：叙事弧线（v2.0 关键）
        "narrative_arc": analyze_narrative_arc(all_paras),
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="深度分析公文模板结构 v2.0")
    parser.add_argument("template", help="模板 .docx 文件路径")
    parser.add_argument("--json", "-j", action="store_true", help="JSON 输出")
    parser.add_argument("--narrative", "-n", action="store_true",
                        help="仅输出叙事弧线分析（简洁模式）")

    args = parser.parse_args()

    analysis = analyze_template(args.template)

    if args.narrative:
        # 简洁叙事分析模式
        na = analysis["narrative_arc"]
        print(f"\n📖 叙事弧线分析: {args.template}")
        print("=" * 60)
        print(f"弧线类型: {na.get('叙事弧线类型', 'N/A')}")
        print(f"\n{na.get('叙事弧线描述', '')}")
        print(f"\n📑 章节论证角色:")
        for title, role in na.get("章节论证角色", {}).items():
            print(f"  {title}")
            print(f"    → {role}")
        print(f"\n🔗 章节间关系:")
        for rel in na.get("章节间关系", []):
            print(f"  {rel['from']}  →  {rel['to']}")
            print(f"    关系: {rel['relationship']}")
        if na.get("写作建议"):
            print(f"\n💡 写作建议:")
            for adv in na["写作建议"]:
                print(f"  {adv}")
        print("=" * 60)
    elif args.json:
        print(json.dumps(analysis, ensure_ascii=False, indent=2))
    else:
        # 完整终端输出
        print(f"\n📋 模板深度分析: {args.template}")
        print("=" * 60)
        print(f"总段落: {analysis['total_paragraphs']} | 总字符: {analysis['total_chars']}")

        # 句长
        sa = analysis.get("sentence_analysis", {})
        if sa:
            print(f"\n✏️ 句长分析: 平均 {sa.get('avg', '?')} 字/句 | {sa.get('style_hint', '')}")

        # 语气
        ta = analysis.get("tone_analysis", {})
        if ta:
            print(f"🗣️ 语气: {ta.get('语气解读', '')}")

        # 叙事
        na = analysis.get("narrative_arc", {})
        if na:
            print(f"\n📖 叙事弧线: {na.get('叙事弧线类型', 'N/A')}")
            for rel in na.get("章节间关系", []):
                sign = {"递进深化": "↗", "转折": "↩", "呼应承上": "↩", "补充扩展": "→"}.get(
                    rel["relationship"], "→")
                print(f"  {rel['from'][:30]} {sign} {rel['to'][:30]}  ({rel['relationship']})")

        print(f"\n📑 大纲 ({len(analysis['outline'])} 个标题):")
        for item in analysis["outline"]:
            sigs = item.get("cross_signals", [])
            sig_str = f" [{', '.join(sigs)}]" if sigs else ""
            print(f"  [{item['level']}] {item['text']}{sig_str}")

        if na.get("写作建议"):
            print(f"\n💡 写作建议:")
            for adv in na["写作建议"]:
                print(f"  {adv}")

        print("=" * 60)


if __name__ == "__main__":
    main()
