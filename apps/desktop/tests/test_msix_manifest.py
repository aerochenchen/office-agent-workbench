"""Contract: MSIX Package.appxmanifest for spike packaging."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src-tauri"
MANIFEST = ROOT / "Package.appxmanifest"


def test_manifest_exists():
    assert MANIFEST.is_file(), f"missing {MANIFEST}"


def test_identity_and_entry_are_spike_safe():
    text = MANIFEST.read_text(encoding="utf-8")
    assert 'Name="ChenZai.Wenshutong"' in text or "Name='ChenZai.Wenshutong'" in text
    assert "CN=ChenZai Wenshutong Spike" in text
    assert re.search(r'Version="0\.1\.0\.0"', text)
    # Nested under App\ to avoid package-root resources/ vs resources.pri clash;
    # ASCII exe name avoids MakeAppx non-ASCII path failures.
    assert 'Executable="App\\Wenshutong.exe"' in text
    assert "文书通.exe" not in text
    assert "runFullTrust" in text or "partialTrust" in text or "windows.fullTrustApplication" in text
