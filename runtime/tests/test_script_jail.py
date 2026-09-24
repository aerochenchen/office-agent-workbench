from __future__ import annotations

import builtins
import io
import os
import sys
from pathlib import Path

import pytest

from office_agent.script_jail import install_fs_jail, is_denied_secret_path
from office_agent.skills import SkillRegistry
from office_agent.tools import ToolExecutor, script_jail_roots
from office_agent.workspace import Workspace


def test_script_jail_roots_exclude_app_data_root(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    roots = [p.resolve() for p in script_jail_roots(ws, data)]
    assert data.resolve() not in roots
    assert (data / "skills").resolve() in roots
    assert (data / "shared-scripts").resolve() in roots
    assert ws.resolve() in roots


def test_config_json_under_app_data_is_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    cfg = tmp_path / "config.json"
    cfg.write_text('{"api_key":"sk-should-not-leak"}', encoding="utf-8")
    assert is_denied_secret_path(cfg)
    assert not is_denied_secret_path(tmp_path / "skills" / "s1" / "SKILL.md")
    assert not is_denied_secret_path(tmp_path / "ws" / "config.json")


def test_guarded_open_blocks_config_json_even_if_root_includes_app_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    monkeypatch.setenv("OFFICE_AGENT_SCRIPT_JAIL", "1")
    cfg = tmp_path / "config.json"
    cfg.write_text('{"api_key":"sk-should-not-leak"}', encoding="utf-8")
    real_open = builtins.open
    real_os_open = os.open
    real_io_open = io.open
    real_remove = os.remove
    real_unlink = os.unlink
    real_rename = os.rename
    real_replace = os.replace
    saved_modules = {name: sys.modules.get(name) for name in ("subprocess", "ctypes", "socket")}
    try:
        install_fs_jail([tmp_path])
        with pytest.raises(PermissionError, match="denied secret"):
            cfg.read_text(encoding="utf-8")
        with pytest.raises(PermissionError, match="path mutation blocked"):
            os.remove(cfg)
        with pytest.raises(PermissionError, match="module blocked"):
            import subprocess as blocked_subprocess

            blocked_subprocess.run(["python", "-c", "print(1)"])
    finally:
        builtins.open = real_open
        os.open = real_os_open
        io.open = real_io_open
        os.remove = real_remove
        os.unlink = real_unlink
        os.rename = real_rename
        os.replace = real_replace
        for name, module in saved_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_workspace_script_cannot_read_app_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "config.json").write_text(
        '{"api_key":"sk-secret-should-not-leak"}', encoding="utf-8"
    )
    ws = tmp_path / "ws"
    work = ws / ".office-agent" / "work"
    work.mkdir(parents=True)
    (work / "steal.py").write_text(
        "from pathlib import Path\n"
        "import os\n"
        "p = Path(os.environ['OFFICE_AGENT_DATA']) / 'config.json'\n"
        "print(p.read_text(encoding='utf-8'))\n",
        encoding="utf-8",
    )
    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="trust",
        allow_workspace_scripts=True,
    )
    result = ex.execute("run_workspace_script", {"path": "steal.py", "args": []})
    combined = f"{result.get('stdout') or ''}{result.get('stderr') or ''}{result.get('error') or ''}"
    assert "sk-secret-should-not-leak" not in combined
    assert result["ok"] is False
