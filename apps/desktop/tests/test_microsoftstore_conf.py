"""Contract: Microsoft Store overlay config for Tauri Windows builds."""

from __future__ import annotations

import json
from pathlib import Path

CONF = (
    Path(__file__).resolve().parents[1]
    / "src-tauri"
    / "tauri.microsoftstore.conf.json"
)


def test_microsoftstore_conf_exists():
    assert CONF.is_file(), f"missing {CONF}"


def test_offline_installer_and_publisher():
    data = json.loads(CONF.read_text(encoding="utf-8"))
    webview = data["bundle"]["windows"]["webviewInstallMode"]
    assert webview["type"] == "offlineInstaller"
    assert data["bundle"]["publisher"] == "Chenzai"
    assert data["bundle"]["publisher"] != "文书通"
