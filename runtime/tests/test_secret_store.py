from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from office_agent.app import load_config, save_config
from office_agent.config import AppConfig
from office_agent.secret_store import SEAL_PREFIX, seal_secret, unseal_secret


def _cfg(**overrides: object) -> AppConfig:
    data = {
        "api_base": "http://127.0.0.1:8000/v1",
        "api_key": "sk-secret-value-123456",
        "model": "m",
        "allowed_hosts": ["127.0.0.1", "localhost"],
    }
    data.update(overrides)
    return AppConfig(**data)  # type: ignore[arg-type]


def test_seal_roundtrip_does_not_embed_plaintext(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    sealed = seal_secret("sk-secret-value-123456")
    assert sealed.startswith(SEAL_PREFIX)
    assert "sk-secret-value-123456" not in sealed
    assert unseal_secret(sealed) == "sk-secret-value-123456"


def test_unseal_legacy_plaintext_passthrough() -> None:
    assert unseal_secret("sk-legacy-plain") == "sk-legacy-plain"
    assert unseal_secret("") == ""


def test_save_config_does_not_write_plaintext_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    save_config(_cfg())
    raw = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert "sk-secret-value-123456" not in raw
    stored = json.loads(raw)["api_key"]
    assert stored.startswith(SEAL_PREFIX)
    loaded = load_config()
    assert loaded.api_key == "sk-secret-value-123456"


def test_load_config_migrates_legacy_plaintext_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "config.json").write_text(
        json.dumps({"api_base": "http://127.0.0.1:8000/v1", "api_key": "legacy-key", "model": "m"}),
        encoding="utf-8",
    )
    loaded = load_config()
    assert loaded.api_key == "legacy-key"
    raw = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert "legacy-key" not in raw
    assert load_config().api_key == "legacy-key"


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes only")
def test_save_config_sets_owner_only_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    save_config(_cfg())
    mode = stat.S_IMODE((tmp_path / "config.json").stat().st_mode)
    assert mode == 0o600
    wrap = tmp_path / "secrets.key"
    if wrap.is_file():
        assert stat.S_IMODE(wrap.stat().st_mode) == 0o600
