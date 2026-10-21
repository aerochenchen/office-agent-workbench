#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""规范制度发布前审查报告（附件1）生成器。

用法:
    python build_report.py review_data.json -o 工作成果/报告.xlsx --draft 工作成果/底稿.md

输入 JSON 结构见 references/04-form-spec.md。
版式复刻原件：A4 纵向、浅青表头、四列（维度/说明/审查要点/审查结论及修改意见）。
不缩放宽度；行高按文字量自动计算；分页尽量落在维度组边界，避免合并单元格被拆开。
stdout 只打 JSON 摘要。需要 PDF 时由人工用 Excel 或 WPS 另存，脚本不调用本机 Excel。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.pagebreak import Break

# ---------- 版式常量 ----------
FONT_NAME = "微软雅黑"
TITLE_PT = 16
SECTION_PT = 10
BODY_PT = 8.5
NOTE_PT = 8
LABEL_PT = 8

FILL = PatternFill("solid", start_color="FFCCFFFF", end_color="FFCCFFFF")
THIN = Side(style="thin", color="FF000000")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

COL_CM = [2.6, 2.6, 6.8, 6.2]          # A B C D，合计 18.2cm
PAGE_H = 842 - 0.6 * 72 - 0.5 * 72     # A4 纵向可用高度（pt）
REPEAT_H = 44                          # 第 2 页起重复表头（第7-8行）占位

HERE = os.path.dirname(os.path.abspath(__file__))
POINTS_PATH = os.path.join(HERE, "..", "assets", "review_points.json")

VERDICTS = ("符合", "基本符合", "不符合", "不适用", "待补")


def load_points() -> list[dict]:
    with open(POINTS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------- 度量 ----------
def cm_to_width(cm: float) -> float:
    px = cm / 2.54 * 96
    return round((px - 5) / 7, 2)


def col_px(cm: float) -> float:
    return cm / 2.54 * 96


def visual_len(text: str) -> float:
    return sum(0.55 if ord(ch) < 128 else 1.0 for ch in str(text))


def est_lines(text: str, cm: float, pt: float) -> int:
    if text is None or str(text) == "":
        return 1
    px_per_char = pt * 96 / 72
    cap = max(1.0, (col_px(cm) - 10) / px_per_char * 0.94)
    total = 0
    for seg in str(text).split("\n"):
        total += max(1, math.ceil(visual_len(seg) / cap))
    return total


def row_height(texts, cms, pts, pad=3.2) -> float:
    lines = 1
    for text, cm, pt in zip(texts, cms, pts):
        lines = max(lines, est_lines(text, cm, pt))
    return round(lines * max(pts) * 1.30 + pad, 1)


# ---------- 写入辅助 ----------
def set_cell(ws, ref, value, *, pt=BODY_PT, bold=False, halign="left", valign="center",
             fill=None, wrap=True):
    c = ws[ref]
    c.value = value
    c.font = Font(name=FONT_NAME, size=pt, bold=bold)
    c.alignment = Alignment(horizontal=halign, vertical=valign, wrap_text=wrap)
    c.border = BOX
    if fill is not None:
        c.fill = fill
    return c


def merge_write(ws, rng, value, **kw):
    ws.merge_cells(rng)
    set_cell(ws, rng.split(":")[0], value, **kw)
    for row in ws[rng]:
        for c in row:
            c.border = BOX
            if kw.get("fill") is not None:
                c.fill = kw["fill"]


# ---------- 主流程 ----------
def build(data: dict, out_path: str) -> str:
    meta = data.get("meta", {})
    items = data.get("items", [])
    points = load_points()
    if len(items) != len(points):
        raise SystemExit(f"items 必须为 {len(points)} 条，当前 {len(items)} 条")

    wb = Workbook()
    ws = wb.active
    ws.title = "规范制度发布前审查报告"
    ws.sheet_view.showGridLines = False
    for i, cm in enumerate(COL_CM, start=1):
        ws.column_dimensions[get_column_letter(i)].width = cm_to_width(cm)

    heights: dict[int, float] = {}

    def h(r: int, v: float):
        heights[r] = v
        ws.row_dimensions[r].height = v

    # 1 附件1
    merge_write(ws, "A1:D1", "附件1", pt=NOTE_PT, halign="left")
    h(1, 16)

    # 2 标题
    merge_write(ws, "A2:D2", "规范制度发布前审查报告", pt=TITLE_PT, halign="center")
    h(2, 30)

    # 3 规范制度名称
    set_cell(ws, "A3", "规范制度名称", halign="center", pt=LABEL_PT)
    name = meta.get("regulation_name", "")
    merge_write(ws, "B3:D3", name)
    h(3, max(20, row_height([name], [COL_CM[1] + COL_CM[2] + COL_CM[3]], [BODY_PT])))

    # 4-6 审查方式
    merge_write(ws, "A4:D4", "一、审查方式", pt=SECTION_PT, bold=True, fill=FILL)
    h(4, 20)
    method = (meta.get("review_method") or "self").lower()
    opt1 = "■  以审查会形式开展集中审查" if method == "meeting" else "□  以审查会形式开展集中审查"
    opt2 = "■  以自查形式开展审查" if method == "self" else "□  以自查形式开展审查"
    merge_write(ws, "A5:D5", opt1)
    merge_write(ws, "A6:D6", opt2)
    h(5, 18)
    h(6, 18)

    # 7 二、审查要素
    merge_write(ws, "A7:D7", "二、审查要素", pt=SECTION_PT, bold=True, fill=FILL)
    h(7, 20)

    # 8 表头
    for col, head in zip("ABCD", ["维度", "说明", "审查要点", "审查结论及修改意见"]):
        set_cell(ws, f"{col}8", head, halign="center")
    h(8, 22)

    # 9-30 22 条要点
    for idx, item in enumerate(items):
        r = 9 + idx
        dim, note, point = points[idx]["dimension"], points[idx]["note"], points[idx]["point"]
        set_cell(ws, f"A{r}", dim, halign="center")
        set_cell(ws, f"B{r}", note, halign="center")
        set_cell(ws, f"C{r}", point)
        verdict = (item.get("conclusion") or "待补").strip()
        opinion = (item.get("opinion") or "").strip()
        if verdict in ("符合", "不适用"):
            body = f"{verdict}。{opinion}" if opinion else verdict
        else:
            body = f"{verdict}：{opinion}" if opinion else verdict
        set_cell(ws, f"D{r}", body)
        h(r, row_height([dim, note, point, body], COL_CM, [BODY_PT] * 4))

    # 合并同值的维度/说明单元格
    def merge_group(col: str, key: str):
        start = None
        prev_key = None
        for idx in range(len(items)):
            key_val = points[idx][key]
            if key_val != prev_key:
                if start is not None and idx - 1 > start:
                    ws.merge_cells(f"{col}{start + 9}:{col}{idx + 8}")
                start, prev_key = idx, key_val
        if start is not None and len(items) - 1 > start:
            ws.merge_cells(f"{col}{start + 9}:{col}{len(items) + 8}")

    merge_group("A", "dimension")
    merge_group("B", "note")

    # 31-34 三、其他修改意见和建议
    merge_write(ws, "A31:D31", "三、其他修改意见和建议", pt=SECTION_PT, bold=True, fill=FILL)
    h(31, 20)
    others = [str(o) for o in (data.get("other_opinions") or [])]
    text = "\n".join(others)
    need = row_height([text], [sum(COL_CM)], [BODY_PT], pad=6)
    for i in range(3):
        rr = 32 + i
        merge_write(ws, f"A{rr}:D{rr}", text if i == 0 else None, valign="top")
        h(rr, max(30, need) if i == 0 else 28)

    # 35-42 四、结论与签字确认
    merge_write(ws, "A35:D35", "四、结论与签字确认", pt=SECTION_PT, bold=True, fill=FILL)
    h(35, 20)

    result = (data.get("result") or "fail").lower()
    pass_mark = "■" if result == "pass" else "□"
    fail_mark = "■" if result == "fail" else "□"
    merge_write(ws, "A36:D36",
                f"        {pass_mark}  审查通过                                        {fail_mark}  审查不通过")
    h(36, 22)

    set_cell(ws, "A37", "规范制度编制部门\n负责人（签字）", halign="center", pt=LABEL_PT)
    merge_write(ws, "B37:D37", data.get("signoff", {}).get("dept_head", ""))
    h(37, 34)

    for col, head in zip("ABCD", ["审查组成员", "单位和部门", "签字", "日期"]):
        set_cell(ws, f"{col}38", head, halign="center")
    h(38, 22)

    members = (data.get("signoff", {}).get("members") or [])[:4]
    for i in range(4):
        rr = 39 + i
        m = members[i] if i < len(members) else {}
        set_cell(ws, f"A{rr}", m.get("name", ""), halign="center")
        set_cell(ws, f"B{rr}", m.get("unit", ""), halign="center")
        set_cell(ws, f"C{rr}", m.get("sign", ""), halign="center")
        set_cell(ws, f"D{rr}", m.get("date", ""), halign="center")
        h(rr, 26)

    # 分页：按区块（表头 / 每个维度组 / 三 / 四）贪心填充，避免拆开合并单元格
    blocks = [[1, 2, 3, 4, 5, 6, 7, 8]]
    cur: list[int] = []
    for idx in range(len(items)):
        key = points[idx]["dimension"]
        if cur and points[cur[0] - 9]["dimension"] != key:
            blocks.append(cur)
            cur = []
        cur.append(9 + idx)
    if cur:
        blocks.append(cur)
    blocks.append([31, 32, 33, 34])
    blocks.append([35, 36, 37, 38, 39, 40, 41, 42])

    page, used = 0, 0.0
    for blk in blocks:
        bh = sum(heights[r] for r in blk)
        cap = PAGE_H if page == 0 else PAGE_H - REPEAT_H
        if used + bh > cap and used > 0:
            ws.row_breaks.append(Break(id=blk[0] - 1))
            page += 1
            used = bh
        else:
            used += bh

    last_row = 42
    ws.print_area = f"A1:D{last_row}"
    ws.print_title_rows = "7:8"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = 9
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = 0.55
    ws.page_margins.right = 0.55
    ws.page_margins.top = 0.6
    ws.page_margins.bottom = 0.5
    ws.page_margins.header = 0.2
    ws.page_margins.footer = 0.2

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    wb.save(out_path)
    return out_path


def build_draft(data: dict, path: str) -> str:
    meta = data.get("meta", {})
    points = load_points()
    lines = [
        f"# {meta.get('regulation_name', '')} 发布前审查底稿",
        "",
        f"- 审查方式：{'审查会集中审查' if (meta.get('review_method') or 'self') == 'meeting' else '自查'}",
        f"- 审查日期：{meta.get('review_date', '')}",
        f"- 审查结论：{'审查通过' if (data.get('result') or 'fail') == 'pass' else '审查不通过'}",
        "",
        "## 一、逐条判定",
        "",
        "| 序号 | 维度 | 审查要点 | 审查结论 | 修改意见 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for idx, item in enumerate(data.get("items", [])):
        p = points[idx]
        lines.append(
            f"| {p['no']} | {p['dimension']} | {p['point']} | "
            f"{item.get('conclusion', '')} | {(item.get('opinion') or '').replace('|', '／')} |"
        )
    lines += ["", "## 二、其他修改意见和建议", ""]
    lines += [f"- {o}" for o in (data.get("other_opinions") or [])] or ["- 无"]
    lines += ["", "## 三、待补材料", ""]
    todos = data.get("pending_inputs") or []
    lines += [f"- {t}" for t in todos] or ["- 无"]
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data", help="审查数据 JSON")
    ap.add_argument("-o", "--out", required=True, help="输出 xlsx 路径")
    ap.add_argument("--draft", help="输出审查底稿 Markdown 路径")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.data):
        print(f"ERROR: 找不到审查数据 {args.data}", file=sys.stderr)
        return 1
    try:
        with open(args.data, encoding="utf-8") as f:
            data = json.load(f)
        out = build(data, args.out)
    except (OSError, json.JSONDecodeError, SystemExit, ValueError) as e:
        message = e.code if isinstance(e, SystemExit) else e
        print(f"ERROR: {message}", file=sys.stderr)
        return 1

    summary: dict = {
        "ok": True,
        "xlsx": out,
        "items": len(data.get("items") or []),
    }
    if args.draft:
        summary["draft"] = build_draft(data, args.draft)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
