"""Contract: Store MSIX workflow is manual and separate from spike/NSIS."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows" / "build-windows-msix-store.yml"
SPIKE = ROOT / ".github" / "workflows" / "build-windows-msix.yml"
LEGACY = ROOT / ".github" / "workflows" / "build-windows.yml"
MSSTORE_EXE = ROOT / ".github" / "workflows" / "build-windows-msstore.yml"


def test_store_msix_workflow_manual_inputs_and_artifact():
    text = WF.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "Build Windows MSIX Store" in text
    assert "wenshutong-windows-msix-store" in text
    assert "MsixStore" in text
    assert "store_package_name" in text or "StorePackageName" in text
    assert "store_publisher" in text or "StorePublisher" in text
    assert "winapp" in text.lower() or "WinApp" in text


def test_spike_and_exe_workflows_remain_separate():
    spike = SPIKE.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")
    exe = MSSTORE_EXE.read_text(encoding="utf-8")
    assert "wenshutong-windows-msix-store" not in spike
    assert "MsixStore" not in legacy
    assert "MsixStore" not in exe
