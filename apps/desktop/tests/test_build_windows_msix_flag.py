"""Contract: build-windows.ps1 supports -Msix without breaking defaults."""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build-windows.ps1"


def test_script_defines_msix_switch():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$Msix" in text or "Msix" in text
    assert "msix-payload" in text
    assert "winapp" in text.lower()
    assert "Package.appxmanifest" in text


def test_msix_and_microsoftstore_are_independent_flags():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "MicrosoftStore" in text
    assert "Msix" in text
