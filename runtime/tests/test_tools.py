from pathlib import Path
import pytest
from office_agent.workspace import Workspace
from office_agent.skills import SkillRegistry
from office_agent.tools import ToolExecutor
from office_agent.audit import AuditLog

def test_run_workspace_script(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    work = ws / ".office-agent" / "work"
    work.mkdir(parents=True)
    (work / "hello.py").write_text("print('from-workspace')\n", encoding="utf-8")
    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="trust",
        audit=AuditLog(tmp_path / "db" / "a.sqlite"),
    )
    # Bare name at root is relocated to .office-agent/work/
    result = ex.execute("run_workspace_script", {"path": "hello.py", "args": []})
    assert result["ok"] is True
    assert "from-workspace" in result["stdout"]


def test_workspace_write_relocates_root_py(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute(
        "workspace_write",
        {"path": "merge_docs.py", "content": "print(1)\n"},
    )
    assert result["ok"] is True
    assert result["path"] == ".office-agent/work/merge_docs.py"
    assert (ws / ".office-agent" / "work" / "merge_docs.py").is_file()
    assert not (ws / "merge_docs.py").exists()


def test_workspace_write_relocates_root_docx_to_output(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute(
        "workspace_write",
        {"path": "AI.docx", "content": "final\n"},
    )
    assert result["ok"] is True
    assert result["path"] == "output/AI.docx"
    assert (ws / "output" / "AI.docx").is_file()
    assert not (ws / "AI.docx").exists()


def test_workspace_write_keeps_non_deliverable_at_root(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute(
        "workspace_write",
        {"path": "notes.txt", "content": "memo\n"},
    )
    assert result["ok"] is True
    assert result["path"] == "notes.txt"
    assert (ws / "notes.txt").is_file()


def test_run_skill_script_captures_stdout(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = tmp_path / "skills" / "s1"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: s1\ndescription: d\ntier: light\npermissions: [run_python]\n---\n\n#\n",
        encoding="utf-8",
    )
    (skill / "scripts" / "hello.py").write_text("print('hi-skill')\n", encoding="utf-8")
    (tmp_path / "ws").mkdir()
    ex = ToolExecutor(
        Workspace(tmp_path / "ws"),
        SkillRegistry(),
        permission_mode="trust",
        audit=AuditLog(tmp_path / "db" / "a.sqlite"),
    )
    result = ex.execute("run_skill_script", {"skill_id": "s1", "script": "hello.py", "args": []})
    assert result["ok"] is True
    assert "hi-skill" in result["stdout"]

def test_run_shared_script(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "shared-scripts").mkdir(parents=True)
    (tmp_path / "shared-scripts" / "format_gongwen.py").write_text("print('formatted')\n", encoding="utf-8")
    (tmp_path / "skills").mkdir(exist_ok=True)
    (tmp_path / "ws").mkdir()
    ex = ToolExecutor(
        Workspace(tmp_path / "ws"),
        SkillRegistry(),
        permission_mode="trust",
        audit=AuditLog(tmp_path / "db" / "a.sqlite"),
    )
    result = ex.execute("run_shared_script", {"name": "format_gongwen", "args": []})
    assert result["ok"] is True
    assert "formatted" in result["stdout"]

def test_write_escape_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    (tmp_path / "ws").mkdir()
    ex = ToolExecutor(
        Workspace(tmp_path / "ws"),
        SkillRegistry(),
        permission_mode="trust",
        audit=AuditLog(tmp_path / "db" / "a.sqlite"),
    )
    result = ex.execute("workspace_write", {"path": "../x.txt", "content": "no"})
    assert result["ok"] is False
    assert "escapes" in result["error"] or "sandbox" in result["error"].lower() or "path" in result["error"].lower()
