"""Contract: MS Store Windows workflow exists and calls -MicrosoftStore."""

from __future__ import annotations

from pathlib import Path

WF = (
    Path(__file__).resolve().parents[3]
    / ".github"
    / "workflows"
    / "build-windows-msstore.yml"
)
LEGACY = (
    Path(__file__).resolve().parents[3]
    / ".github"
    / "workflows"
    / "build-windows.yml"
)


def test_msstore_workflow_exists_and_is_manual():
    text = WF.read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "Build Windows MS Store" in text
    assert "wenshutong-windows-msstore" in text
    assert "-MicrosoftStore" in text or "MicrosoftStore" in text


def test_legacy_windows_workflow_unchanged_marker():
    """Smoke: legacy workflow still present and does not opt into Store mode."""
    text = LEGACY.read_text(encoding="utf-8")
    assert "Build Windows Installer" in text
    assert "MicrosoftStore" not in text
    assert "wenshutong-windows-nsis" in text
