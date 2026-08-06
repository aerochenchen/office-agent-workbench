"""Contract: Store-targeted Package.store.appxmanifest template."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src-tauri"
MANIFEST = ROOT / "Package.store.appxmanifest"


def test_store_manifest_exists():
    assert MANIFEST.is_file(), f"missing {MANIFEST}"


def test_store_manifest_placeholders_and_display_name():
    text = MANIFEST.read_text(encoding="utf-8")
    assert "__STORE_PACKAGE_NAME__" in text
    assert "__STORE_PUBLISHER__" in text
    assert "__STORE_PUBLISHER_DISPLAY_NAME__" in text
    assert "__STORE_VERSION__" in text
    assert "「文书通」" in text
    assert "ChenZai Wenshutong Spike" not in text
    assert 'Executable="App\\Wenshutong.exe"' in text
    assert "runFullTrust" in text
    assert re.search(r'Version="__STORE_VERSION__"', text)
    assert 'ProcessorArchitecture="x64"' in text
