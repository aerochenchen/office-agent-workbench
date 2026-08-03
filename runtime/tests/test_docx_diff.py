"""Tests for bundled shared-script docx_diff."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from docx import Document

REPO_ROOT = Path(__file__).resolve().parents[2]
DIFF_SCRIPT = REPO_ROOT / "bundled" / "shared-scripts" / "docx_diff.py"


def _write_docx(path: Path, paragraphs: list[str]) -> None:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))


def test_docx_diff_detects_replace_add_delete(tmp_path: Path):
    old = tmp_path / "old.docx"
    new = tmp_path / "new.docx"
    _write_docx(old, ["标题", "原有段落甲", "原有段落乙", "将被删除"])
    _write_docx(new, ["标题", "修改后段落甲", "原有段落乙", "新增段落"])
    out = tmp_path / "diff.json"
    proc = subprocess.run(
        [sys.executable, str(DIFF_SCRIPT), str(old), str(new), "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is True
    ops = {c["op"] for c in report["changes"]}
    assert "replace" in ops
    texts = " ".join(
        f"{c.get('old_text', '')} {c.get('new_text', '')}" for c in report["changes"]
    )
    assert "修改后段落甲" in texts
    assert "将被删除" in texts or "新增段落" in texts
    assert report["summary"]["replace"] >= 1
    assert out.is_file()


def test_docx_diff_identical_empty_changes(tmp_path: Path):
    a = tmp_path / "a.docx"
    b = tmp_path / "b.docx"
    paras = ["一、进展", "完成试点 3 个。"]
    _write_docx(a, paras)
    _write_docx(b, paras)
    out = tmp_path / "same.json"
    proc = subprocess.run(
        [sys.executable, str(DIFF_SCRIPT), str(a), str(b), "--out", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["changes"] == []
    assert report["summary"] == {"add": 0, "delete": 0, "replace": 0}


def test_docx_diff_missing_file(tmp_path: Path):
    a = tmp_path / "a.docx"
    _write_docx(a, ["x"])
    proc = subprocess.run(
        [
            sys.executable,
            str(DIFF_SCRIPT),
            str(a),
            str(tmp_path / "missing.docx"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "ERROR:" in proc.stderr
