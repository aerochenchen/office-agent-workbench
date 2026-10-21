"""Reject xlsx packages Excel will not open.

openpyxl can read worksheets whose child tags are out of schema order.
Excel validates that order and refuses the file, so delivery checks the
package itself.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

# CT_Worksheet sequence in ECMA-376. Later tags must not precede earlier ones.
_SHEET_CHILD_ORDER = (
    "sheetPr",
    "dimension",
    "sheetViews",
    "sheetFormatPr",
    "cols",
    "sheetData",
    "sheetCalcPr",
    "sheetProtection",
    "protectedRanges",
    "scenarios",
    "autoFilter",
    "sortState",
    "dataConsolidate",
    "customSheetViews",
    "mergeCells",
    "phoneticPr",
    "conditionalFormatting",
    "dataValidations",
    "hyperlinks",
    "printOptions",
    "pageMargins",
    "pageSetup",
    "headerFooter",
    "rowBreaks",
    "colBreaks",
    "customProperties",
    "cellWatches",
    "ignoredErrors",
    "smartTags",
    "drawing",
    "legacyDrawing",
    "legacyDrawingHF",
    "picture",
    "oleObjects",
    "controls",
    "webPublishItems",
    "tableParts",
    "extLst",
)
_ORDER_RANK = {name: index for index, name in enumerate(_SHEET_CHILD_ORDER)}
_MERGE_REF = re.compile(r"^[A-Z]{1,3}[1-9][0-9]*:[A-Z]{1,3}[1-9][0-9]*$")
_TAG_RE_CACHE: dict[str, re.Pattern[str]] = {}


def xlsx_package_errors(path: Path, label: str) -> list[str]:
    """Return human-readable defects. Empty means the package can be delivered."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return [f"{label} 不是有效的 Excel 压缩包"]
    with archive:
        names = set(archive.namelist())
        errors: list[str] = []
        if "xl/workbook.xml" not in names:
            errors.append(f"{label} 不是完整的 Excel 文件：缺少 xl/workbook.xml")
        sheets = [name for name in sorted(names) if _is_worksheet(name)]
        if not sheets:
            errors.append(f"{label} 不是完整的 Excel 文件：缺少工作表")
            return errors
        for sheet_name in sheets:
            try:
                xml = archive.read(sheet_name).decode("utf-8")
            except UnicodeError:
                errors.append(f"{label} 的 {sheet_name} 不是 UTF-8 文本")
                continue
            errors.extend(_worksheet_errors(xml, label, sheet_name))
        return errors


def _is_worksheet(name: str) -> bool:
    parts = name.split("/")
    return (
        len(parts) == 3
        and parts[0] == "xl"
        and parts[1] == "worksheets"
        and parts[2].endswith(".xml")
    )


def _worksheet_errors(xml: str, label: str, sheet_name: str) -> list[str]:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        return [f"{label} 的 {sheet_name} 无法解析：{exc}"]
    where = f"{label} 的 {sheet_name}"
    errors: list[str] = []
    previous_rank = -1
    previous_name = ""
    for child in list(root):
        name = _local_name(child.tag)
        rank = _ORDER_RANK.get(name)
        if rank is None:
            loc = _tag_location(xml, name)
            errors.append(f"{where} {loc}：无法识别的标签 {name}")
            continue
        if rank < previous_rank:
            loc = _tag_location(xml, name)
            hint = f"{name} 出现在 {previous_name} 之后"
            if name == "printOptions":
                hint += "，应位于 pageMargins 之前"
            errors.append(f"{where} {loc}：{hint}")
        previous_rank = rank
        previous_name = name
        if name == "mergeCells":
            errors.extend(_merge_errors(child, xml, where))
    return errors


def _merge_errors(merge_cells: ElementTree.Element, xml: str, where: str) -> list[str]:
    errors: list[str] = []
    for cell in list(merge_cells):
        if _local_name(cell.tag) != "mergeCell":
            continue
        ref = cell.get("ref") or ""
        if _MERGE_REF.fullmatch(ref):
            continue
        loc = _attr_location(xml, ref) if ref else _tag_location(xml, "mergeCell")
        shown = ref or "（空）"
        errors.append(f"{where} {loc}：合并区域「{shown}」不是单元格地址")
    return errors


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _tag_location(xml: str, tag: str) -> str:
    pattern = _TAG_RE_CACHE.get(tag)
    if pattern is None:
        pattern = re.compile(rf"<(?:[\w.]+:)?{re.escape(tag)}(?=[\s>/])")
        _TAG_RE_CACHE[tag] = pattern
    match = pattern.search(xml)
    if match is None:
        return tag
    return _position(xml, match.start())


def _attr_location(xml: str, value: str) -> str:
    idx = xml.find(value)
    if idx < 0:
        return value
    return _position(xml, idx)


def _position(xml: str, idx: int) -> str:
    line = xml.count("\n", 0, idx) + 1
    column = idx - xml.rfind("\n", 0, idx)
    return f"第 {line} 行第 {column} 列"
