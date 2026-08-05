"""Contract: build-windows.ps1 exposes -MicrosoftStore and passes Tauri --config."""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build-windows.ps1"


def test_script_defines_microsoft_store_switch():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$MicrosoftStore" in text


def test_script_passes_store_config_to_tauri():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "tauri.microsoftstore.conf.json" in text
    assert "--config" in text
