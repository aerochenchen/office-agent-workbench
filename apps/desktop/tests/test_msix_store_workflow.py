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


def test_store_msix_workflow_passes_inputs_via_environment():
    text = WF.read_text(encoding="utf-8")
    build_step = text[text.index("- name: Build Windows MSIX (Store identity)") :]
    run_block = build_step[build_step.index("run: |") :]

    assert "env:" in build_step[: build_step.index("run: |")]
    assert "STORE_PACKAGE_NAME: ${{ inputs.store_package_name }}" in build_step
    assert "STORE_PUBLISHER: ${{ inputs.store_publisher }}" in build_step
    assert (
        "STORE_PUBLISHER_DISPLAY_NAME: "
        "${{ inputs.store_publisher_display_name }}" in build_step
    )
    assert "STORE_VERSION: ${{ inputs.store_version }}" in build_step
    assert '-StorePackageName "$env:STORE_PACKAGE_NAME"' in run_block
    assert '-StorePublisher "$env:STORE_PUBLISHER"' in run_block
    assert (
        '-StorePublisherDisplayName "$env:STORE_PUBLISHER_DISPLAY_NAME"' in run_block
    )
    assert '-StoreVersion "$env:STORE_VERSION"' in run_block
    assert "${{ inputs." not in run_block


def test_spike_and_exe_workflows_remain_separate():
    spike = SPIKE.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")
    exe = MSSTORE_EXE.read_text(encoding="utf-8")
    assert "wenshutong-windows-msix-store" not in spike
    assert "MsixStore" not in legacy
    assert "MsixStore" not in exe
