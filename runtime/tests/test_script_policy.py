from __future__ import annotations

import os
from pathlib import Path

import pytest

from office_agent.script_policy import assert_argv_within_roots, build_script_env
from office_agent.tools import ToolError, ToolExecutor
from office_agent.workspace import Workspace
from office_agent.skills import SkillRegistry


def test_build_script_env_forces_offline_and_clears_proxy() -> None:
    env = build_script_env(
        {
            "HF_HUB_OFFLINE": "0",
            "TRANSFORMERS_OFFLINE": "0",
            "HTTP_PROXY": "http://proxy:8080",
            "HTTPS_PROXY": "http://proxy:8080",
            "http_proxy": "http://proxy:8080",
            "OTHER": "keep",
        }
    )
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["TRANSFORMERS_OFFLINE"] == "1"
    assert env["NO_PROXY"] == "*"
    assert "HTTP_PROXY" not in env
    assert "HTTPS_PROXY" not in env
    assert "http_proxy" not in env
    assert env["OTHER"] == "keep"


def test_build_script_env_defaults_from_os_environ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("HTTP_PROXY", "http://evil:1")
    env = build_script_env()
    assert env["HF_HUB_OFFLINE"] == "1"
    assert "HTTP_PROXY" not in env


def test_build_script_env_strips_sensitive_credentials() -> None:
    """敏感凭据 env（token/key/secret/password 等）不得透传给脚本子进程。"""
    env = build_script_env(
        {
            "OFFICE_AGENT_API_TOKEN": "SECRET_TOKEN_POC",
            "SOME_API_KEY": "leak_me",
            "MY_DATABASE_PASSWORD": "p@ss",
            "AUTH_HEADER": "bearer xxx",
            "CREDENTIALS_BLOB": "xxx",
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp/home",
            "OTHER": "keep",
        }
    )
    # 敏感凭据必须被剥离
    assert "OFFICE_AGENT_API_TOKEN" not in env
    assert "SOME_API_KEY" not in env
    assert "MY_DATABASE_PASSWORD" not in env
    assert "AUTH_HEADER" not in env
    assert "CREDENTIALS_BLOB" not in env
    # 非敏感系统 env 必须保留
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["HOME"] == "/tmp/home"
    assert env["OTHER"] == "keep"
    # 业务白名单 env 保留
    assert env["HF_HUB_OFFLINE"] == "1"


def test_assert_argv_rejects_absolute_outside_roots(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(ToolError, match="outside allowed roots"):
        assert_argv_within_roots(["/etc/passwd"], [root])


def test_assert_argv_allows_workspace_relative_path(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    doc = root / "工作成果" / "report.docx"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"PK")
    assert_argv_within_roots(["工作成果/report.docx"], [root])


def test_assert_argv_allows_non_path_flags_and_literals() -> None:
    assert_argv_within_roots(["--verbose", "42", "hello"], [Path("/tmp/ws")])


def test_assert_argv_rejects_relative_escape(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    outside = tmp_path / "secret.docx"
    outside.write_bytes(b"PK")
    with pytest.raises(ToolError, match="outside allowed roots"):
        assert_argv_within_roots(["../secret.docx"], [root])


def test_run_workspace_script_rejects_outside_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    work = ws / ".office-agent" / "work"
    work.mkdir(parents=True)
    (work / "runner.py").write_text("import sys\nprint('ran', sys.argv[1:])\n", encoding="utf-8")
    outside = tmp_path / "outside.docx"
    outside.write_bytes(b"PK")
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute(
        "run_workspace_script",
        {"path": "runner.py", "args": [str(outside)]},
    )
    assert result["ok"] is False
    assert "outside allowed roots" in result["error"]


def test_run_workspace_script_allows_in_workspace_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    work = ws / ".office-agent" / "work"
    work.mkdir(parents=True)
    (work / "runner.py").write_text("import sys\nprint('ok', sys.argv[1])\n", encoding="utf-8")
    target = ws / "notes.txt"
    target.write_text("data\n", encoding="utf-8")
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute(
        "run_workspace_script",
        {"path": "runner.py", "args": ["notes.txt"]},
    )
    assert result["ok"] is True
    assert "ok notes.txt" in result["stdout"]


def test_run_skill_script_allows_skill_dir_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = tmp_path / "skills" / "s1"
    scripts = skill / "scripts"
    scripts.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: s1\ndescription: d\ntier: light\npermissions: [run_python]\n---\n\n#\n",
        encoding="utf-8",
    )
    fixture = skill / "fixtures" / "sample.docx"
    fixture.parent.mkdir()
    fixture.write_bytes(b"PK")
    (scripts / "run.py").write_text(
        "import sys\nprint('skill-arg', sys.argv[1])\n",
        encoding="utf-8",
    )
    (tmp_path / "ws").mkdir()
    ex = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    rel = "fixtures/sample.docx"
    result = ex.execute(
        "run_skill_script",
        {"skill_id": "s1", "script": "run.py", "args": [rel]},
    )
    assert result["ok"] is True
    assert "skill-arg fixtures/sample.docx" in result["stdout"]


def test_run_shared_script_allows_shared_dir_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    shared = tmp_path / "shared-scripts"
    shared.mkdir(parents=True)
    helper = shared / "helper.txt"
    helper.write_text("x\n", encoding="utf-8")
    (shared / "fmt.py").write_text(
        "import sys\nprint('shared-arg', sys.argv[1])\n",
        encoding="utf-8",
    )
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()
    ex = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    result = ex.execute(
        "run_shared_script",
        {"name": "fmt", "args": ["helper.txt"]},
    )
    assert result["ok"] is True
    assert "shared-arg helper.txt" in result["stdout"]
