#!/usr/bin/env python3
"""Document I/O: normalize legacy Office formats and extract text units.

- .doc  → .docx (soffice / textutil / Word COM on Windows)
- .xls  → .xlsx (xlrd → openpyxl)
- extract: .docx / .xlsx / .pdf → list of units with stable unit_id anchors
- PDF pages with no text layer: printed-text OCR via pypdfium2 render + RapidOCR
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NORMALIZED_REL = ".office-agent/work/normalized"
PDF_OCR_MAX_PAGES_DEFAULT = 30
# pypdfium2 scale=1 is 72 dpi. 150 dpi is enough for printed scans without huge bitmaps.
# Source: https://github.com/pypdfium2-team/pypdfium2#render-a-page
PDF_OCR_RENDER_DPI = 150
PDF_OCR_QUALITY_HINT = (
    "处理得好的材料：能打开、能改字的 Word/WPS；"
    "或者 PDF 打开后用鼠标能把字拖选出来（Word 里点「另存为 PDF」一般就是这种）。"
    "表格用 Excel。"
    "当前这份是扫描件或图片版，靠印刷体识别，不能保证准确。"
    "现在处理可能：错字、错数、文号和金额对不上、表格错行错列；"
    "印章、手写、歪斜或模糊页更容易错。"
    "适合先看个大概；要对数字、对原文，请换上面那种材料。"
)

_OCR_ENGINE: Any = None

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


class DocIOError(ValueError):
    """Raised when normalize/extract cannot proceed."""


@dataclass
class ExtractUnit:
    unit_id: str
    kind: str
    locator: str
    text: str
    tags: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "unit_id": self.unit_id,
            "kind": self.kind,
            "locator": self.locator,
            "text": self.text,
            "tags": self.tags,
        }
        if self.meta:
            out["meta"] = self.meta
        return out


@dataclass
class ExtractResult:
    ok: bool
    format: str
    source: str
    path: str
    doc_key: str
    units: list[ExtractUnit] = field(default_factory=list)
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    normalized_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok,
            "format": self.format,
            "source": self.source,
            "path": self.path,
            "doc_key": self.doc_key,
            "units": [u.to_dict() for u in self.units],
            "truncated": self.truncated,
            "warnings": self.warnings,
        }
        if self.normalized_path is not None:
            out["normalized_path"] = self.normalized_path
        if self.error is not None:
            out["error"] = self.error
        return out


def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def short_doc_key(path: Path) -> str:
    return file_sha1(path)[:10]


def _tags_for(text: str) -> list[str]:
    return ["has_data"] if _HAS_DATA.search(text) else []


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
    if _CN_HEADER_PREFIX.match(text) or text.startswith(("附件", "抄送", "主送")):
        return 1 if not text.startswith(("附件", "抄送", "主送")) else 3
    return 0


def normalized_dir(workspace_root: Path) -> Path:
    path = workspace_root / NORMALIZED_REL
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_path(
    src: Path,
    workspace_root: Path,
    *,
    force: bool = False,
) -> tuple[Path, str, list[str]]:
    """Return (modern_path, format, warnings). format is docx|xlsx."""
    src = src.resolve()
    if not src.is_file():
        raise DocIOError(f"not a file: {src}")
    suffix = src.suffix.lower()
    warnings: list[str] = []

    if suffix == ".docx":
        return src, "docx", warnings
    if suffix == ".xlsx":
        return src, "xlsx", warnings
    if suffix == ".pdf":
        return src, "pdf", warnings
    if suffix == ".doc":
        out = _normalize_doc(src, workspace_root, force=force)
        return out, "docx", warnings
    if suffix == ".xls":
        out = _normalize_xls(src, workspace_root, force=force)
        return out, "xlsx", warnings
    raise DocIOError(
        f"unsupported format for normalize: {suffix} "
        "(supported: .doc .docx .xls .xlsx .pdf)"
    )


def _target_normalized(src: Path, workspace_root: Path, new_suffix: str) -> Path:
    dest_dir = normalized_dir(workspace_root)
    return dest_dir / f"{src.stem}{new_suffix}"


def _normalize_xls(src: Path, workspace_root: Path, *, force: bool) -> Path:
    dest = _target_normalized(src, workspace_root, ".xlsx")
    if dest.is_file() and not force and dest.stat().st_mtime >= src.stat().st_mtime:
        return dest
    try:
        import xlrd
        from openpyxl import Workbook
    except ImportError as e:
        raise DocIOError(
            "reading .xls requires xlrd and openpyxl; install runtime deps"
        ) from e

    book = xlrd.open_workbook(str(src), formatting_info=False)
    wb = Workbook()
    # remove default sheet after we create real ones
    default = wb.active
    first = True
    for sheet in book.sheets():
        if first:
            ws = default
            ws.title = (sheet.name or "Sheet1")[:31]
            first = False
        else:
            ws = wb.create_sheet(title=(sheet.name or "Sheet")[:31])
        for r in range(sheet.nrows):
            row_vals = []
            for c in range(sheet.ncols):
                cell = sheet.cell(r, c)
                val = cell.value
                if val is None:
                    row_vals.append(None)
                elif sheet.cell_type(r, c) == xlrd.XL_CELL_DATE:
                    try:
                        from datetime import datetime

                        dt = xlrd.xldate_as_datetime(val, book.datemode)
                        row_vals.append(dt)
                    except Exception:  # noqa: BLE001
                        row_vals.append(val)
                else:
                    row_vals.append(val)
            ws.append(row_vals)
    if first:
        # empty workbook
        default.title = "Sheet1"
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(dest))
    return dest


def _which(names: list[str]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _find_soffice() -> str | None:
    """Locate LibreOffice soffice on PATH or common Windows install dirs."""
    found = _which(["soffice", "libreoffice", "soffice.exe"])
    if found:
        return found
    if not sys.platform.startswith("win"):
        return None
    program_files = [
        os.environ.get("PROGRAMFILES"),
        os.environ.get("PROGRAMFILES(X86)"),
        os.environ.get("LOCALAPPDATA"),
    ]
    rels = [
        Path("LibreOffice") / "program" / "soffice.exe",
        Path("Programs") / "LibreOffice" / "program" / "soffice.exe",
    ]
    for root in program_files:
        if not root:
            continue
        base = Path(root)
        for rel in rels:
            candidate = base / rel
            if candidate.is_file():
                return str(candidate)
    return None


def _normalize_doc(src: Path, workspace_root: Path, *, force: bool) -> Path:
    dest = _target_normalized(src, workspace_root, ".docx")
    if dest.is_file() and not force and dest.stat().st_mtime >= src.stat().st_mtime:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    soffice = _find_soffice()
    if soffice:
        try:
            _run_soffice_convert(soffice, src, dest)
            if dest.is_file():
                return dest
            errors.append("soffice produced no output")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"soffice: {exc}")

    if sys.platform == "darwin":
        textutil = shutil.which("textutil")
        if textutil:
            try:
                subprocess.run(
                    [textutil, "-convert", "docx", "-output", str(dest), str(src)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if dest.is_file():
                    return dest
                errors.append("textutil produced no output")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"textutil: {exc}")

    if sys.platform.startswith("win"):
        try:
            if _normalize_doc_win32(src, dest):
                return dest
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Word COM: {exc}")

    detail = "; ".join(errors) if errors else "no converter available"
    raise DocIOError(
        f"无法将 .doc 转为 .docx（{detail}）。"
        "请安装 LibreOffice 或 Microsoft Word，或在本机将文件另存为 .docx 后重试。"
    )


def _run_soffice_convert(soffice: str, src: Path, dest: Path) -> None:
    outdir = dest.parent
    subprocess.run(
        [
            soffice,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--convert-to",
            "docx",
            "--outdir",
            str(outdir),
            str(src),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    produced = outdir / f"{src.stem}.docx"
    if produced.is_file() and produced.resolve() != dest.resolve():
        produced.replace(dest)


def _normalize_doc_win32(src: Path, dest: Path) -> bool:
    """Best-effort Word COM conversion on Windows (pywin32, then PowerShell)."""
    if _normalize_doc_win32_pywin32(src, dest):
        return True
    return _normalize_doc_win32_powershell(src, dest)


def _normalize_doc_win32_pywin32(src: Path, dest: Path) -> bool:
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return False
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    # 3 = msoAutomationSecurityForceDisable
    word.AutomationSecurity = 3
    try:
        doc = word.Documents.Open(str(src))
        # 16 = wdFormatXMLDocument (.docx)
        doc.SaveAs(str(dest), FileFormat=16)
        doc.Close(False)
    finally:
        word.Quit()
    return dest.is_file()


def _normalize_doc_win32_powershell(src: Path, dest: Path) -> bool:
    """Drive Word.Application via PowerShell when pywin32 is unavailable."""
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        return False
    # Pass paths via env to avoid quoting/encoding pitfalls with Chinese paths.
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "$src = $env:WST_DOC_SRC; $dest = $env:WST_DOC_DEST; "
        "$word = New-Object -ComObject Word.Application; "
        "$word.Visible = $false; $word.DisplayAlerts = 0; "
        "$word.AutomationSecurity = 3; "
        "try { "
        "$doc = $word.Documents.Open($src, $false, $true); "
        "try { $doc.SaveAs2([string]$dest, 16) } "
        "finally { $doc.Close($false) } "
        "} finally { $word.Quit() }"
    )
    env = os.environ.copy()
    env["WST_DOC_SRC"] = str(src)
    env["WST_DOC_DEST"] = str(dest)
    subprocess.run(
        [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    return dest.is_file()


def extract_docx(
    path: Path,
    doc_key: str,
    *,
    max_chars: int,
    max_units: int,
    granularity: str = "section",
) -> tuple[list[ExtractUnit], bool, list[str]]:
    from docx import Document

    gran = (granularity or "section").strip().lower()
    if gran not in {"section", "paragraph"}:
        gran = "section"

    warnings: list[str] = []
    doc = Document(str(path))
    structure: list[dict[str, Any]] = []
    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue
        style_name = para.style.name if para.style else "Normal"
        level = detect_heading_level(text, style_name)
        structure.append(
            {
                "text": text,
                "level": level,
                "is_heading": level > 0,
                "para_idx": i,
                "char_count": len(text),
            }
        )

    units_raw: list[dict[str, Any]] = []

    if gran == "paragraph":
        for para in structure:
            kind = "heading" if para["is_heading"] else "paragraph"
            units_raw.append(
                {
                    "title": para["text"][:40],
                    "level": para["level"],
                    "paragraphs": [para["text"]],
                    "start": para["para_idx"],
                    "end": para["para_idx"],
                    "kind": kind,
                }
            )
    else:
        current: dict[str, Any] | None = None
        for para in structure:
            if para["is_heading"]:
                if current and current["paragraphs"]:
                    units_raw.append(current)
                current = {
                    "title": para["text"],
                    "level": para["level"],
                    "paragraphs": [para["text"]],
                    "start": para["para_idx"],
                    "end": para["para_idx"],
                }
            else:
                if current is None:
                    current = {
                        "title": "(前言)",
                        "level": 0,
                        "paragraphs": [],
                        "start": para["para_idx"],
                        "end": para["para_idx"],
                    }
                current["paragraphs"].append(para["text"])
                current["end"] = para["para_idx"]
        if current and current["paragraphs"]:
            units_raw.append(current)

    # Also pull tables as separate units
    for ti, table in enumerate(doc.tables):
        rows: list[str] = []
        for row in table.rows:
            cells = [" ".join(c.text.split()) for c in row.cells]
            line = " | ".join(cells).strip()
            if line:
                rows.append(line)
        if rows:
            units_raw.append(
                {
                    "title": f"(表格{ti + 1})",
                    "level": 0,
                    "paragraphs": rows,
                    "start": -1,
                    "end": -1,
                    "kind": "table",
                }
            )

    units: list[ExtractUnit] = []
    total_chars = 0
    truncated = False
    for idx, raw in enumerate(units_raw, start=1):
        if len(units) >= max_units:
            truncated = True
            break
        text = "\n".join(raw["paragraphs"]).strip()
        if not text:
            continue
        if total_chars + len(text) > max_chars:
            remain = max_chars - total_chars
            if remain <= 0:
                truncated = True
                break
            text = text[:remain] + "…"
            truncated = True
        kind = str(raw.get("kind") or "paragraph")
        locator = raw["title"]
        if raw["start"] >= 0:
            locator = f"{raw['title']}@p{raw['start']}-{raw['end']}"
        meta: dict[str, Any] = {
            "level": int(raw.get("level") or 0),
            "para_start": int(raw["start"]),
            "para_end": int(raw["end"]),
            "granularity": gran,
        }
        units.append(
            ExtractUnit(
                unit_id=f"{doc_key}#u{idx:02d}",
                kind=kind,
                locator=locator,
                text=text,
                tags=_tags_for(text),
                meta=meta,
            )
        )
        total_chars += len(text)
        if truncated:
            break
    if not units and not structure:
        warnings.append("docx 未解析到段落文本")
    return units, truncated, warnings


def _col_letters(index_1based: int) -> str:
    """1-based column index → Excel letters (1→A, 27→AA)."""
    n = index_1based
    letters: list[str] = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters)) or "A"


def extract_xlsx(
    path: Path,
    doc_key: str,
    *,
    max_chars: int,
    max_units: int,
    max_rows_per_sheet: int = 500,
    granularity: str = "section",
) -> tuple[list[ExtractUnit], bool, list[str]]:
    from openpyxl import load_workbook

    gran = (granularity or "section").strip().lower()
    if gran not in {"section", "cells"}:
        gran = "section"

    warnings: list[str] = []
    wb = load_workbook(str(path), read_only=True, data_only=True)
    units: list[ExtractUnit] = []
    total_chars = 0
    truncated = False
    unit_i = 0

    for sheet in wb.worksheets:
        if gran == "cells":
            headers: dict[int, str] = {}
            row_i = 0
            for row in sheet.iter_rows(values_only=True):
                row_i += 1
                if row_i > max_rows_per_sheet:
                    warnings.append(f"工作表 {sheet.title} 超过 {max_rows_per_sheet} 行，已截断")
                    truncated = True
                    break
                for col_i, v in enumerate(row, start=1):
                    if v is None:
                        continue
                    text = str(v).strip()
                    if not text:
                        continue
                    if row_i == 1:
                        headers[col_i] = text
                    if len(units) >= max_units:
                        truncated = True
                        break
                    cell_ref = f"{_col_letters(col_i)}{row_i}"
                    locator = f"{sheet.title}!{cell_ref}"
                    header = headers.get(col_i, "")
                    line = f"{cell_ref}\t{text}"
                    if header and row_i > 1:
                        line = f"{cell_ref}\t{header}={text}"
                    if total_chars + len(line) > max_chars:
                        truncated = True
                        break
                    unit_i += 1
                    units.append(
                        ExtractUnit(
                            unit_id=f"{doc_key}#u{unit_i:02d}",
                            kind="cell",
                            locator=locator,
                            text=line,
                            tags=_tags_for(text),
                            meta={
                                "sheet": sheet.title,
                                "cell": cell_ref,
                                "row": row_i,
                                "col": col_i,
                                "header": header,
                                "granularity": "cells",
                            },
                        )
                    )
                    total_chars += len(line)
                if truncated or len(units) >= max_units:
                    break
            if truncated or len(units) >= max_units:
                break
            continue

        rows_out: list[str] = []
        row_count = 0
        for row in sheet.iter_rows(values_only=True):
            if row_count >= max_rows_per_sheet:
                warnings.append(f"工作表 {sheet.title} 超过 {max_rows_per_sheet} 行，已截断")
                truncated = True
                break
            cells = []
            empty = True
            for v in row:
                if v is None:
                    cells.append("")
                else:
                    empty = False
                    cells.append(str(v).strip())
            if empty:
                continue
            rows_out.append("\t".join(cells))
            row_count += 1
        if not rows_out:
            continue
        # pack sheet into one or more units of ~80 lines
        chunk_size = 80
        for start in range(0, len(rows_out), chunk_size):
            if len(units) >= max_units:
                truncated = True
                break
            chunk = rows_out[start : start + chunk_size]
            text = "\n".join(chunk)
            if total_chars + len(text) > max_chars:
                remain = max_chars - total_chars
                if remain <= 0:
                    truncated = True
                    break
                text = text[:remain] + "…"
                truncated = True
            unit_i += 1
            end_row = start + len(chunk)
            units.append(
                ExtractUnit(
                    unit_id=f"{doc_key}#u{unit_i:02d}",
                    kind="table_rows",
                    locator=f"{sheet.title}!rows {start + 1}-{end_row}",
                    text=text,
                    tags=_tags_for(text),
                    meta={"granularity": "section", "sheet": sheet.title},
                )
            )
            total_chars += len(text)
            if truncated:
                break
        if truncated or len(units) >= max_units:
            break

    wb.close()
    if not units:
        warnings.append("xlsx 未解析到表格内容")
    return units, truncated, warnings


def _pdf_page_has_text_layer(page: Any) -> bool:
    """True when pdfplumber exposes at least one non-whitespace char on the page."""
    try:
        chars = getattr(page, "chars", None) or []
        return any((c.get("text") or "").strip() for c in chars)
    except Exception:  # noqa: BLE001
        return bool((page.extract_text() or "").strip())


def _pdf_extract_text_pdfium(path: Path, page_index: int, *, _doc_cache: dict[str, Any] | None = None) -> str:
    """Fallback text extract via PDFium (often more robust for CJK encodings)."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return ""

    cache_key = str(path.resolve())
    owns_doc = False
    doc = None
    raw = ""
    try:
        if _doc_cache is not None and cache_key in _doc_cache:
            doc = _doc_cache[cache_key]
        else:
            # Read bytes so non-ASCII Windows paths do not trip the native loader.
            doc = pdfium.PdfDocument(path.read_bytes())
            owns_doc = True
            if _doc_cache is not None:
                _doc_cache[cache_key] = doc
                owns_doc = False
        if page_index < 0 or page_index >= len(doc):
            return ""
        page = doc[page_index]
        textpage = page.get_textpage()
        try:
            raw = textpage.get_text_bounded() or ""
        finally:
            textpage.close()
            page.close()
    except Exception:  # noqa: BLE001
        return ""
    finally:
        if owns_doc and doc is not None:
            try:
                doc.close()
            except Exception:  # noqa: BLE001
                pass
    return raw.replace("\r\n", "\n").replace("\r", "\n").strip()


def _page_ranges_text(pages: list[int]) -> str:
    if not pages:
        return ""
    ranges: list[str] = []
    range_start = range_end = pages[0]
    for page_no in pages[1:]:
        if page_no == range_end + 1:
            range_end = page_no
            continue
        ranges.append(
            str(range_start) if range_start == range_end else f"{range_start}–{range_end}"
        )
        range_start = range_end = page_no
    ranges.append(
        str(range_start) if range_start == range_end else f"{range_start}–{range_end}"
    )
    return "、".join(ranges)


def _pdf_render_page_image(
    path: Path,
    page_index: int,
    *,
    _doc_cache: dict[str, Any] | None = None,
) -> Any | None:
    """Rasterize one page for printed OCR. Returns a PIL Image or None."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None

    cache_key = str(path.resolve())
    owns_doc = False
    doc = None
    try:
        if _doc_cache is not None and cache_key in _doc_cache:
            doc = _doc_cache[cache_key]
        else:
            if not path.is_file():
                return None
            doc = pdfium.PdfDocument(path.read_bytes())
            owns_doc = True
            if _doc_cache is not None:
                _doc_cache[cache_key] = doc
                owns_doc = False
        if page_index < 0 or page_index >= len(doc):
            return None
        page = doc[page_index]
        try:
            bitmap = page.render(scale=PDF_OCR_RENDER_DPI / 72.0)
            return bitmap.to_pil()
        finally:
            page.close()
    except Exception:  # noqa: BLE001
        return None
    finally:
        if owns_doc and doc is not None:
            try:
                doc.close()
            except Exception:  # noqa: BLE001
                pass


def _rapidocr_engine() -> Any | None:
    """Lazy RapidOCR singleton. False sentinel after a failed import/init."""
    global _OCR_ENGINE
    if _OCR_ENGINE is False:
        return None
    if _OCR_ENGINE is None:
        try:
            # Official install: pip install rapidocr onnxruntime
            # Source: https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/install/
            from rapidocr import RapidOCR

            _OCR_ENGINE = RapidOCR()
        except Exception:  # noqa: BLE001
            _OCR_ENGINE = False
            return None
    return _OCR_ENGINE


def _pdf_ocr_printed_text(image: Any) -> str:
    """Run printed-text OCR on a page image. Empty on missing engine or no text."""
    engine = _rapidocr_engine()
    if engine is None or image is None:
        return ""
    try:
        result = engine(image)
    except Exception:  # noqa: BLE001
        return ""
    txts = getattr(result, "txts", None) or ()
    lines = [str(t).strip() for t in txts if t and str(t).strip()]
    return "\n".join(lines)


def _pdf_ocr_page_text(
    path: Path,
    page_index: int,
    *,
    _doc_cache: dict[str, Any] | None = None,
) -> str:
    image = _pdf_render_page_image(path, page_index, _doc_cache=_doc_cache)
    if image is None:
        return ""
    return _pdf_ocr_printed_text(image)


def extract_pdf(
    path: Path,
    doc_key: str,
    *,
    max_chars: int,
    max_units: int,
    granularity: str = "section",
    max_ocr_pages: int = PDF_OCR_MAX_PAGES_DEFAULT,
) -> tuple[list[ExtractUnit], bool, list[str]]:
    try:
        import pdfplumber
    except ImportError as e:
        raise DocIOError(
            "reading .pdf requires pdfplumber; install runtime deps"
        ) from e

    gran = (granularity or "section").strip().lower()
    if gran == "cells":
        gran = "section"
        cells_fallback = True
    else:
        cells_fallback = False
    if gran not in {"section", "paragraph"}:
        gran = "section"

    warnings: list[str] = []
    if cells_fallback:
        warnings.append("pdf 不支持 granularity=cells，已回退为 section")

    units: list[ExtractUnit] = []
    total_chars = 0
    truncated = False
    unit_i = 0
    no_text_pages: list[int] = []
    ocr_pages: list[int] = []
    skipped_ocr_pages: list[int] = []
    ocr_used = 0
    pdfium_cache: dict[str, Any] = {}

    def _append(kind: str, locator: str, text: str, meta: dict[str, Any]) -> bool:
        nonlocal unit_i, total_chars, truncated
        text = text.strip()
        if not text:
            return False
        if len(units) >= max_units:
            truncated = True
            return True
        if total_chars + len(text) > max_chars:
            remain = max_chars - total_chars
            if remain <= 0:
                truncated = True
                return True
            text = text[:remain] + "…"
            truncated = True
        unit_i += 1
        units.append(
            ExtractUnit(
                unit_id=f"{doc_key}#u{unit_i:02d}",
                kind=kind,
                locator=locator,
                text=text,
                tags=_tags_for(text),
                meta=meta,
            )
        )
        total_chars += len(text)
        return truncated

    def _append_body(page_no: int, body: str, *, source: str = "text") -> None:
        if gran == "paragraph":
            blocks = [b.strip() for b in body.split("\n") if b.strip()]
            for bi, block in enumerate(blocks, start=1):
                if _append(
                    "paragraph",
                    f"第{page_no}页@块{bi}",
                    block,
                    {
                        "page": page_no,
                        "block": bi,
                        "granularity": "paragraph",
                        "source": source,
                    },
                ):
                    break
        elif body:
            _append(
                "page",
                f"第{page_no}页",
                body,
                {
                    "page": page_no,
                    "granularity": "section",
                    "source": source,
                },
            )

    # Prefer Path over str so Unicode paths stay intact on Windows.
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            page_units_start = len(units)
            table_objs = []
            try:
                table_objs = page.find_tables() or []
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"第{page_no}页: 表检测失败（{exc}）")
                table_objs = []

            # Body text: prefer filtering out table bboxes; fall back to full page.
            try:
                if table_objs:
                    bboxes = [t.bbox for t in table_objs if getattr(t, "bbox", None)]

                    def _not_in_tables(obj: dict[str, Any]) -> bool:
                        x0 = float(obj.get("x0", 0))
                        x1 = float(obj.get("x1", 0))
                        top = float(obj.get("top", 0))
                        bottom = float(obj.get("bottom", 0))
                        cx = (x0 + x1) / 2
                        cy = (top + bottom) / 2
                        for bx0, btop, bx1, bbottom in bboxes:
                            if bx0 <= cx <= bx1 and btop <= cy <= bbottom:
                                return False
                        return True

                    filtered = page.filter(_not_in_tables)
                    body = filtered.extract_text() or ""
                else:
                    body = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                body = page.extract_text() or ""

            body = (body or "").strip()
            # Non-empty extract_text is sufficient proof of a text layer; page.chars
            # can be empty for some CJK / custom-encoding digital PDFs.
            has_text_layer = bool(body) or _pdf_page_has_text_layer(page)
            if not has_text_layer:
                pdfium_body = _pdf_extract_text_pdfium(
                    path, page_no - 1, _doc_cache=pdfium_cache
                )
                if pdfium_body:
                    body = pdfium_body
                    has_text_layer = True

            if not has_text_layer:
                if max_ocr_pages > 0 and ocr_used >= max_ocr_pages:
                    skipped_ocr_pages.append(page_no)
                elif max_ocr_pages > 0:
                    ocr_used += 1
                    ocr_body = _pdf_ocr_page_text(
                        path, page_no - 1, _doc_cache=pdfium_cache
                    )
                    if ocr_body:
                        _append_body(page_no, ocr_body, source="ocr")
                        ocr_pages.append(page_no)
                    else:
                        no_text_pages.append(page_no)
                else:
                    no_text_pages.append(page_no)
            else:
                _append_body(page_no, body, source="text")

            for ti, tobj in enumerate(table_objs, start=1):
                try:
                    grid = tobj.extract()
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"第{page_no}页-表{ti}: 抽取失败（{exc}）")
                    continue
                if not grid:
                    continue
                rows: list[str] = []
                for row in grid:
                    cells = [
                        " ".join(str(c).split()) if c is not None else ""
                        for c in row
                    ]
                    if not any(cells):
                        continue
                    line = " | ".join(cells).strip()
                    if line:
                        rows.append(line)
                if not rows:
                    continue
                if _append(
                    "table",
                    f"第{page_no}页-表{ti}",
                    "\n".join(rows),
                    {
                        "page": page_no,
                        "table_index": ti,
                        "granularity": gran,
                    },
                ):
                    break

            if (
                len(units) == page_units_start
                and table_objs
                and not body
                and has_text_layer
                and not truncated
            ):
                fallback_body = (page.extract_text() or "").strip()
                if not fallback_body:
                    fallback_body = _pdf_extract_text_pdfium(
                        path, page_no - 1, _doc_cache=pdfium_cache
                    )
                _append_body(page_no, fallback_body)

            page.flush_cache()
            if len(units) >= max_units:
                truncated = True
                break
            if truncated:
                break

    for cached in pdfium_cache.values():
        try:
            cached.close()
        except Exception:  # noqa: BLE001
            pass

    if ocr_pages:
        warnings.append(
            f"第{_page_ranges_text(ocr_pages)}页等共{len(ocr_pages)}页。"
            f"{PDF_OCR_QUALITY_HINT}"
        )
    if skipped_ocr_pages:
        truncated = True
        warnings.append(
            f"第{_page_ranges_text(skipped_ocr_pages)}页未做印刷体识别"
            f"（已达上限 {max_ocr_pages} 页）"
        )
    if no_text_pages:
        warnings.append(
            f"第{_page_ranges_text(no_text_pages)}页等共{len(no_text_pages)}页无文本层"
            "（疑似纯图或印刷体识别无结果）"
        )
    if not units and not no_text_pages and not skipped_ocr_pages:
        warnings.append("pdf 未解析到文本或表格")
    return units, truncated, warnings


def extract_file(
    path: Path,
    workspace_root: Path | None = None,
    *,
    max_chars: int = 80_000,
    max_units: int = 200,
    force_normalize: bool = False,
    granularity: str = "section",
    max_ocr_pages: int = PDF_OCR_MAX_PAGES_DEFAULT,
) -> ExtractResult:
    """Normalize if needed, then extract units from docx/xlsx/pdf."""
    path = path.resolve()
    source_name = path.name
    warnings: list[str] = []
    normalized_rel: str | None = None

    try:
        if workspace_root is None:
            # Without workspace, only accept modern formats in-place
            suffix = path.suffix.lower()
            if suffix in {".doc", ".xls"}:
                raise DocIOError(
                    f"{suffix} requires workspace_root for normalize output"
                )
            modern, fmt, w = path, suffix.lstrip("."), []
            warnings.extend(w)
        else:
            workspace_root = workspace_root.resolve()
            modern, fmt, w = normalize_path(
                path, workspace_root, force=force_normalize
            )
            warnings.extend(w)
            try:
                if modern.resolve() != path.resolve():
                    normalized_rel = str(modern.relative_to(workspace_root))
            except ValueError:
                normalized_rel = str(modern)

        # Key from original bytes when possible (stable for same source file)
        key_src = path if path.is_file() else modern
        doc_key = short_doc_key(key_src)

        if fmt == "docx":
            units, truncated, w2 = extract_docx(
                modern,
                doc_key,
                max_chars=max_chars,
                max_units=max_units,
                granularity=granularity,
            )
        elif fmt == "xlsx":
            units, truncated, w2 = extract_xlsx(
                modern,
                doc_key,
                max_chars=max_chars,
                max_units=max_units,
                granularity=granularity,
            )
        elif fmt == "pdf":
            units, truncated, w2 = extract_pdf(
                modern,
                doc_key,
                max_chars=max_chars,
                max_units=max_units,
                granularity=granularity,
                max_ocr_pages=max_ocr_pages,
            )
        else:
            raise DocIOError(f"unsupported extract format: {fmt}")
        warnings.extend(w2)

        return ExtractResult(
            ok=True,
            format=fmt,
            source=source_name,
            path=str(path),
            doc_key=doc_key,
            units=units,
            truncated=truncated,
            warnings=warnings,
            normalized_path=normalized_rel,
        )
    except DocIOError as e:
        return ExtractResult(
            ok=False,
            format=path.suffix.lower().lstrip(".") or "unknown",
            source=source_name,
            path=str(path),
            doc_key="",
            error=str(e),
            warnings=warnings,
        )
    except Exception as e:  # noqa: BLE001
        return ExtractResult(
            ok=False,
            format=path.suffix.lower().lstrip(".") or "unknown",
            source=source_name,
            path=str(path),
            doc_key="",
            error=f"extract failed: {e}",
            warnings=warnings,
        )
