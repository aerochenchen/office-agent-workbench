"""Contract: MSIX Windows workflow is manual and isolated from NSIS store workflow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows" / "build-windows-msix.yml"
LEGACY = ROOT / ".github" / "workflows" / "build-windows.yml"
MSSTORE = ROOT / ".github" / "workflows" / "build-windows-msstore.yml"


def test_msix_workflow_exists_and_is_manual():
    text = WF.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "Build Windows MSIX" in text
    assert "wenshutong-windows-msix" in text
    assert "-Msix" in text or "Msix" in text
    assert "winapp" in text.lower() or "WinApp" in text or "microsoft.winappcli" in text.lower()


def test_other_windows_workflows_untouched_by_msix_flag():
    legacy = LEGACY.read_text(encoding="utf-8")
    store = MSSTORE.read_text(encoding="utf-8")
    assert "Build Windows Installer" in legacy
    assert "Msix" not in legacy
    assert "Build Windows MS Store" in store
    assert "Msix" not in store
