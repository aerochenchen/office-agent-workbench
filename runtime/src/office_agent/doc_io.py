#!/usr/bin/env python3
"""Document I/O: normalize legacy Office formats and extract text units.

- .doc  → .docx (soffice / textutil / optional Word COM later)
- .xls  → .xlsx (xlrd → openpyxl)
- extract: .docx / .xlsx → list of units with stable unit_id anchors
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NORMALIZED_REL = ".office-agent/work/normalized"

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "kind": self.kind,
            "locator": self.locator,
            "text": self.text,
            "tags": self.tags,
        }


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
    if suffix == ".doc":
        out = _normalize_doc(src, workspace_root, force=force)
        return out, "docx", warnings
    if suffix == ".xls":
        out = _normalize_xls(src, workspace_root, force=force)
        return out, "xlsx", warnings
    raise DocIOError(
        f"unsupported format for normalize: {suffix} "
        "(supported: .doc .docx .xls .xlsx)"
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


def _normalize_doc(src: Path, workspace_root: Path, *, force: bool) -> Path:
    dest = _target_normalized(src, workspace_root, ".docx")
    if dest.is_file() and not force and dest.stat().st_mtime >= src.stat().st_mtime:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    soffice = _which(["soffice", "libreoffice"])
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
        "请安装 LibreOffice，或在本机将文件另存为 .docx 后重试。"
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
    """Best-effort Word COM conversion on Windows."""
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return False
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    try:
        doc = word.Documents.Open(str(src))
        # 16 = wdFormatXMLDocument (.docx)
        doc.SaveAs(str(dest), FileFormat=16)
        doc.Close(False)
    finally:
        word.Quit()
    return dest.is_file()


def extract_docx(path: Path, doc_key: str, *, max_chars: int, max_units: int) -> tuple[list[ExtractUnit], bool, list[str]]:
    from docx import Document

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
        units.append(
            ExtractUnit(
                unit_id=f"{doc_key}#u{idx:02d}",
                kind=kind,
                locator=locator,
                text=text,
                tags=_tags_for(text),
            )
        )
        total_chars += len(text)
        if truncated:
            break
    if not units and not structure:
        warnings.append("docx 未解析到段落文本")
    return units, truncated, warnings


def extract_xlsx(
    path: Path,
    doc_key: str,
    *,
    max_chars: int,
    max_units: int,
    max_rows_per_sheet: int = 500,
) -> tuple[list[ExtractUnit], bool, list[str]]:
    from openpyxl import load_workbook

    warnings: list[str] = []
    wb = load_workbook(str(path), read_only=True, data_only=True)
    units: list[ExtractUnit] = []
    total_chars = 0
    truncated = False
    unit_i = 0

    for sheet in wb.worksheets:
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


def extract_file(
    path: Path,
    workspace_root: Path | None = None,
    *,
    max_chars: int = 80_000,
    max_units: int = 200,
    force_normalize: bool = False,
) -> ExtractResult:
    """Normalize if needed, then extract units from docx/xlsx."""
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
                modern, doc_key, max_chars=max_chars, max_units=max_units
            )
        elif fmt == "xlsx":
            units, truncated, w2 = extract_xlsx(
                modern, doc_key, max_chars=max_chars, max_units=max_units
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
