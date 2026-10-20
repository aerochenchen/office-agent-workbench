"""Tests for bundled material-gap inventory.py path bounds."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_SCRIPT = (
    REPO_ROOT / "bundled" / "skills" / "material-gap" / "scripts" / "inventory.py"
)


def test_inventory_writes_inside_workspace(tmp_path: Path):
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    out = tmp_path / ".office-agent" / "work" / "material-gap" / "inventory.json"
    proc = subprocess.run(
        [sys.executable, str(INVENTORY_SCRIPT), ".", "--out", str(out.relative_to(tmp_path))],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["total"] >= 1


def test_inventory_rejects_out_outside_workspace(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside-inventory.json"
    proc = subprocess.run(
        [sys.executable, str(INVENTORY_SCRIPT), ".", "--out", str(outside)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "escapes workspace" in proc.stderr
    assert not outside.exists()
