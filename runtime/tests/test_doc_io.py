"""Tests for document normalize + workspace_extract."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from docx import Document
from openpyxl import Workbook

from office_agent.audit import AuditLog
from office_agent.doc_io import DocIOError, extract_file, normalize_path
from office_agent.skills import SkillRegistry
from office_agent.tools import ToolExecutor
from office_agent.workspace import Workspace


def _write_docx(path: Path) -> None:
    doc = Document()
    doc.add_heading("专项汇报", level=1)
    doc.add_paragraph("一、工作进展")
    doc.add_paragraph("建成智能平台，覆盖基层网点 128 个。")
    doc.add_paragraph("二、下一步打算")
    doc.add_paragraph("持续推进重点任务落地。")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))


def _write_xlsx(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "汇总"
    ws.append(["部门", "完成率", "备注"])
    ws.append(["办公室", "95%", "含试点"])
    ws.append(["业务处", "88%", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))


def _write_xls(path: Path) -> None:
    xlwt = pytest.importorskip("xlwt")
    book = xlwt.Workbook()
    sheet = book.add_sheet("数据")
    sheet.write(0, 0, "项目")
    sheet.write(0, 1, "金额")
    sheet.write(1, 0, "数字化")
    sheet.write(1, 1, 128)
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(str(path))


def test_extract_docx_units(tmp_path: Path):
    src = tmp_path / "a.docx"
    _write_docx(src)
    result = extract_file(src, tmp_path)
    assert result.ok is True
    assert result.format == "docx"
    assert result.doc_key
    assert result.units
    blob = "\n".join(u.text for u in result.units)
    assert "128" in blob
    assert result.units[0].unit_id.startswith(result.doc_key + "#u")
    assert result.units[0].meta.get("granularity") == "section"
    assert "para_start" in result.units[0].meta
    d = result.units[0].to_dict()
    assert "meta" in d


def test_extract_docx_paragraph_granularity(tmp_path: Path):
    src = tmp_path / "para.docx"
    _write_docx(src)
    section = extract_file(src, tmp_path, granularity="section")
    paragraph = extract_file(src, tmp_path, granularity="paragraph")
    assert paragraph.ok is True
    # _write_docx: heading + 4 body paras = 5 non-empty paragraphs
    para_units = [u for u in paragraph.units if u.kind in {"paragraph", "heading"}]
    assert len(para_units) == 5
    assert len(para_units) >= len(section.units)
    assert all(u.meta.get("granularity") == "paragraph" for u in para_units)
    assert all(u.meta.get("para_start") == u.meta.get("para_end") for u in para_units)
    assert any(u.kind == "heading" for u in para_units)


def test_extract_xlsx_units(tmp_path: Path):
    src = tmp_path / "b.xlsx"
    _write_xlsx(src)
    result = extract_file(src, tmp_path)
    assert result.ok is True
    assert result.format == "xlsx"
    blob = "\n".join(u.text for u in result.units)
    assert "办公室" in blob
    assert "95%" in blob


def test_normalize_xls_to_xlsx(tmp_path: Path):
    src = tmp_path / "legacy.xls"
    _write_xls(src)
    modern, fmt, _ = normalize_path(src, tmp_path)
    assert fmt == "xlsx"
    assert modern.suffix.lower() == ".xlsx"
    assert modern.is_file()
    result = extract_file(src, tmp_path)
    assert result.ok is True
    assert result.normalized_path
    blob = "\n".join(u.text for u in result.units)
    assert "数字化" in blob


def test_normalize_doc_uses_converter(tmp_path: Path):
    src = tmp_path / "old.doc"
    src.write_bytes(b"fake-doc-bytes")
    dest = tmp_path / ".office-agent" / "work" / "normalized" / "old.docx"

    def fake_soffice(cmd, **kwargs):
        _write_docx(dest)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    with patch("office_agent.doc_io._which", return_value="/usr/bin/soffice"):
        with patch("office_agent.doc_io.subprocess.run", side_effect=fake_soffice):
            modern, fmt, _ = normalize_path(src, tmp_path, force=True)
    assert fmt == "docx"
    assert modern == dest
    result = extract_file(src, tmp_path)
    assert result.ok is True
    assert any("128" in u.text for u in result.units)


def test_normalize_doc_fails_clearly_without_converter(tmp_path: Path):
    src = tmp_path / "old.doc"
    src.write_bytes(b"fake")
    with patch("office_agent.doc_io._which", return_value=None):
        with patch("office_agent.doc_io.shutil.which", return_value=None):
            with pytest.raises(DocIOError, match="无法将 .doc"):
                normalize_path(src, tmp_path, force=True)


def test_workspace_extract_tool(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path / "data"))
    (tmp_path / "data" / "skills").mkdir(parents=True)
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_docx(ws / "汇报.docx")
    _write_xlsx(ws / "表.xlsx")
    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="trust",
        audit=AuditLog(tmp_path / "data" / "a.sqlite"),
    )
    r1 = ex.execute("workspace_extract", {"path": "汇报.docx"})
    assert r1["ok"] is True
    assert r1["format"] == "docx"
    assert r1["units"]
    r2 = ex.execute("workspace_extract", {"path": "表.xlsx"})
    assert r2["ok"] is True
    assert any("办公室" in u["text"] for u in r2["units"])


def test_workspace_extract_xls_via_tool(tmp_path: Path, monkeypatch):
    pytest.importorskip("xlwt")
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path / "data"))
    (tmp_path / "data" / "skills").mkdir(parents=True)
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_xls(ws / "旧表.xls")
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    r = ex.execute("workspace_extract", {"path": "旧表.xls"})
    assert r["ok"] is True
    assert r["format"] == "xlsx"
    assert r.get("normalized_path")
    assert any("数字化" in u["text"] for u in r["units"])


def test_workspace_extract_passes_granularity(tmp_path: Path):
    (tmp_path / "data" / "skills").mkdir(parents=True)
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_docx(ws / "稿.docx")
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    r = ex.execute(
        "workspace_extract",
        {"path": "稿.docx", "granularity": "paragraph"},
    )
    assert r["ok"] is True
    assert len([u for u in r["units"] if u["kind"] in {"paragraph", "heading"}]) == 5
    assert r["units"][0]["meta"]["granularity"] == "paragraph"
