"""Contract: build-windows.ps1 exposes -MsixStore independent of spike -Msix."""

from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build-windows.ps1"


def test_script_defines_msix_store_switch():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "[switch]$MsixStore" in text or "$MsixStore" in text
    assert "StorePackageName" in text
    assert "StorePublisher" in text
    assert "StorePublisherDisplayName" in text
    assert "StoreVersion" in text
    assert "Package.store.appxmanifest" in text
    assert "Build-MsixStore" in text


def test_msix_store_mutex_with_other_pack_modes():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "-MsixStore cannot be combined with -Msix" in text
    assert "-MsixStore cannot be combined with -MicrosoftStore" in text


def test_msix_store_inputs_and_winapp_are_validated_before_build_steps():
    text = SCRIPT.read_text(encoding="utf-8")

    validation = text.index("Assert-MsixStorePrerequisites")
    ensure_python = text.index("Ensure-Python")
    build_sidecar = text.index("Build-Sidecar")
    build_tauri = text.index("Build-Tauri")

    assert validation < ensure_python < build_sidecar < build_tauri
    assert "StorePackageName" in text[validation:ensure_python]
    assert "StorePublisher" in text[validation:ensure_python]
    assert "StorePublisherDisplayName" in text[validation:ensure_python]
    assert "StoreVersion must match x.y.z.0" in text[validation:ensure_python]
    assert "winapp CLI not found on PATH" in text[validation:ensure_python]
