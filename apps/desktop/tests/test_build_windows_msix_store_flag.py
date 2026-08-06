"""Contract: build-windows.ps1 exposes -MsixStore independent of spike -Msix."""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build-windows.ps1"


def test_script_defines_msix_store_switch():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$MsixStore" in text or "$MsixStore" in text
    assert "StorePackageName" in text
    assert "StorePublisher" in text
    assert "Package.store.appxmanifest" in text
    assert "Build-MsixStore" in text or "MsixStore" in text


def test_msix_store_mutex_with_other_pack_modes():
    text = SCRIPT.read_text(encoding="utf-8")
    # Must refuse combining store pack with spike Msix or MicrosoftStore EXE mode.
    assert "MsixStore" in text and "MicrosoftStore" in text and "Msix" in text
    assert "cannot be combined" in text.lower() or "互斥" in text or "throw" in text
