"""Contract: PKS offline installer never requires network."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INSTALL = ROOT / "packaging" / "pks" / "install-offline.sh"


def test_install_offline_script_is_airgap_safe():
    assert INSTALL.is_file(), f"missing {INSTALL}"
    text = INSTALL.read_text(encoding="utf-8")
    assert text.startswith("#!")
    assert "dpkg" in text
    # Must not curl/wget the internet
    lower = text.lower()
    assert "curl " not in lower
    assert "wget " not in lower
    assert "apt-get update" not in lower
    assert "deps" in text
