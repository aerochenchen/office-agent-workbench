"""Contract: build-kylin-pks.sh exists and documents Docker linux/arm64 offline bundle."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "build-kylin-pks.sh"


def test_build_kylin_pks_script_exists_and_is_executable_bit_friendly():
    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!"), "missing shebang"
    assert "linux/arm64" in text or "linux/aarch64" in text
    assert "docker" in text.lower()
    assert "packaging/pks" in text or "packaging/pks/" in text
    assert "wenshutong-pks" in text
    assert "install-offline.sh" in text
