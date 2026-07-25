from pathlib import Path
import pytest
from office_agent.workspace import Workspace
from office_agent.skills import SkillRegistry
from office_agent.tools import MAX_SKILL_FILE_BYTES, ToolExecutor
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

def test_run_skill_script_rejects_skill_id_escape(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    outside = tmp_path / "outside" / "scripts"
    outside.mkdir(parents=True)
    (outside / "evil.py").write_text("print('escaped')\n", encoding="utf-8")
    (tmp_path / "ws").mkdir()
    ex = ToolExecutor(Workspace(tmp_path / "ws"), SkillRegistry(), permission_mode="trust")
    result = ex.execute(
        "run_skill_script",
        {"skill_id": "../outside", "script": "evil.py", "args": []},
    )
    assert result["ok"] is False
    assert "escaped" not in str(result)


def _install_skill(root: Path, skill_id: str, body: str = "# 标题\n\n正文\n") -> Path:
    skill = root / "skills" / skill_id
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: d\ntier: light\n---\n\n{body}",
        encoding="utf-8",
    )
    (skill / "references" / "spec.md").write_text("引用规范\n", encoding="utf-8")
    return skill


def _executor(root: Path) -> ToolExecutor:
    ws = root / "ws"
    ws.mkdir(exist_ok=True)
    return ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")


def test_read_skill_defaults_to_skill_md(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    _install_skill(tmp_path, "s1", body="# 六步纪律\n\nStep 1 做事\n")
    result = _executor(tmp_path).execute("read_skill", {"skill_id": "s1"})
    assert result["ok"] is True
    assert result["file"] == "SKILL.md"
    assert "六步纪律" in result["content"]
    assert result["truncated"] is False
    assert "references/spec.md" in result["files"]


def test_read_skill_reads_reference_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    _install_skill(tmp_path, "s1")
    result = _executor(tmp_path).execute(
        "read_skill", {"skill_id": "s1", "file": "references/spec.md"}
    )
    assert result["ok"] is True
    assert "引用规范" in result["content"]


def test_read_skill_rejects_escape(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    _install_skill(tmp_path, "s1")
    (tmp_path / "secret.md").write_text("绝密\n", encoding="utf-8")
    ex = _executor(tmp_path)
    for bad in ("../secret.md", "../../secret.md", "/etc/hosts"):
        result = ex.execute("read_skill", {"skill_id": "s1", "file": bad})
        assert result["ok"] is False, bad
        assert "绝密" not in str(result)


def test_read_skill_rejects_skill_id_escape(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    _install_skill(tmp_path, "s1")
    result = _executor(tmp_path).execute("read_skill", {"skill_id": "../.."})
    assert result["ok"] is False


def test_read_skill_missing_skill_and_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    _install_skill(tmp_path, "s1")
    ex = _executor(tmp_path)
    missing_skill = ex.execute("read_skill", {"skill_id": "nope"})
    assert missing_skill["ok"] is False
    assert "not installed" in missing_skill["error"]
    missing_file = ex.execute("read_skill", {"skill_id": "s1", "file": "references/nope.md"})
    assert missing_file["ok"] is False
    # File list still returned so the agent can pick a real file next.
    assert "references/spec.md" in missing_file["files"]


def test_read_skill_rejects_binary_suffix(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = _install_skill(tmp_path, "s1")
    (skill / "sample.docx").write_bytes(b"PK\x03\x04binary")
    result = _executor(tmp_path).execute("read_skill", {"skill_id": "s1", "file": "sample.docx"})
    assert result["ok"] is False
    assert "sample.docx" not in result["files"]


def test_read_skill_truncates_large_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    _install_skill(tmp_path, "s1", body="x" * (MAX_SKILL_FILE_BYTES + 500))
    result = _executor(tmp_path).execute("read_skill", {"skill_id": "s1"})
    assert result["ok"] is True
    assert result["truncated"] is True
    assert len(result["content"]) == MAX_SKILL_FILE_BYTES


def test_read_skill_skips_pycache(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = _install_skill(tmp_path, "s1")
    cache = skill / "scripts" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "x.py").write_text("cached\n", encoding="utf-8")
    result = _executor(tmp_path).execute("read_skill", {"skill_id": "s1"})
    assert result["ok"] is True
    assert not any("__pycache__" in f for f in result["files"])


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
