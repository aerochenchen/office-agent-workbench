from pathlib import Path
import sqlite3
import subprocess

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
        allow_workspace_scripts=True,
    )
    # Bare name at root is relocated to .office-agent/work/
    result = ex.execute("run_workspace_script", {"path": "hello.py", "args": []})
    assert result["ok"] is True
    assert "from-workspace" in result["stdout"]


def test_run_workspace_script_disabled_audits_error_code(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    audit = AuditLog(tmp_path / "db" / "disabled.sqlite")
    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="trust",
        audit=audit,
        session_id="sess-disabled",
        allow_workspace_scripts=False,
    )
    result = ex.execute("run_workspace_script", {"path": "hello.py", "args": []})
    assert result["ok"] is False
    with sqlite3.connect(audit.db_path) as conn:
        row = conn.execute(
            "SELECT event_type, session_id, error_code, detail, ok FROM audit "
            "WHERE tool = 'run_workspace_script' ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    event_type, session_id, error_code, detail, ok = row
    assert event_type == "tool_invoked"
    assert session_id == "sess-disabled"
    assert ok == 0
    assert error_code == "workspace_scripts_disabled" or "disabled" in (detail or "").lower()


def test_run_workspace_script_propagates_turn_id_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    work = ws / ".office-agent" / "work"
    work.mkdir(parents=True)
    (work / "echo_turn.py").write_text(
        "import os\nprint(os.environ.get('OFFICE_AGENT_TURN_ID', ''))\n",
        encoding="utf-8",
    )
    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="trust",
        turn_id="turn-abc",
        allow_workspace_scripts=True,
    )
    result = ex.execute("run_workspace_script", {"path": "echo_turn.py", "args": []})
    assert result["ok"] is True
    assert "turn-abc" in result["stdout"]


def test_script_timeout_sets_error_code_and_emits(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    work = ws / ".office-agent" / "work"
    work.mkdir(parents=True)
    (work / "slow.py").write_text("print('never')\n", encoding="utf-8")
    audit = AuditLog(tmp_path / "db" / "timeout.sqlite")
    emitted: list[tuple] = []

    def _fake_emit(event, **fields):
        emitted.append((event, fields))

    monkeypatch.setattr("office_agent.diagnostic.emit", _fake_emit)

    def _timeout_run(*_a, **_kw):
        raise subprocess.TimeoutExpired(cmd="py", timeout=1)

    monkeypatch.setattr("office_agent.tools.subprocess.run", _timeout_run)
    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="trust",
        audit=audit,
        session_id="sess-to",
        allow_workspace_scripts=True,
    )
    result = ex.execute("run_workspace_script", {"path": "slow.py", "args": []})
    assert result["ok"] is False
    assert "timeout" in result["error"].lower()
    with sqlite3.connect(audit.db_path) as conn:
        row = conn.execute(
            "SELECT error_code FROM audit WHERE tool = 'run_workspace_script' "
            "ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row[0] == "script_timeout"
    assert any(ev == "script_timeout" for ev, _ in emitted)


def test_script_stderr_outside_does_not_create_sandbox_escape_event(
    tmp_path: Path, monkeypatch
):
    """Python stderr like 'index outside range' must not look like a jail escape."""
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    work = ws / ".office-agent" / "work"
    work.mkdir(parents=True)
    (work / "outside_stderr.py").write_text(
        "import sys\n"
        "sys.stderr.write('index outside range\\n')\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    audit = AuditLog(tmp_path / "db" / "outside-stderr.sqlite")
    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="trust",
        audit=audit,
        session_id="sess-stderr",
        allow_workspace_scripts=True,
    )
    result = ex.execute("run_workspace_script", {"path": "outside_stderr.py", "args": []})
    assert result["ok"] is False
    assert "outside" in (result.get("stderr") or "").lower()
    with sqlite3.connect(audit.db_path) as conn:
        escape_n = conn.execute(
            "SELECT count(*) FROM audit WHERE event_type = 'sandbox_escape_blocked'"
        ).fetchone()[0]
        tool_row = conn.execute(
            "SELECT event_type, error_code FROM audit "
            "WHERE tool = 'run_workspace_script' ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    assert escape_n == 0
    assert tool_row is not None
    assert tool_row[0] == "tool_invoked"
    assert tool_row[1] != "sandbox_escape_blocked"


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
    assert result["path"] == "工作成果/AI.docx"
    assert (ws / "工作成果" / "AI.docx").is_file()
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


def test_run_shared_script_not_found_lists_available(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "shared-scripts").mkdir(parents=True)
    (tmp_path / "shared-scripts" / "format_gongwen.py").write_text(
        "print('formatted')\n", encoding="utf-8"
    )
    (tmp_path / "skills").mkdir(exist_ok=True)
    (tmp_path / "ws").mkdir()
    ex = ToolExecutor(
        Workspace(tmp_path / "ws"),
        SkillRegistry(),
        permission_mode="trust",
    )
    result = ex.execute("run_shared_script", {"name": "python", "args": []})
    assert result["ok"] is False
    assert "python" in result["error"]
    assert "format_gongwen" in result["error"]
    assert "available" in result["error"] or "已安装" in result["error"]

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


def test_finish_without_deliverables_still_ok(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute("finish", {"summary": "闲聊结束"})
    assert result["ok"] is True
    assert result["finished"] is True
    assert result["summary"] == "闲聊结束"


def test_finish_rejects_missing_deliverables(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute(
        "finish",
        {
            "summary": "已汇总成表",
            "deliverables": ["工作成果/产品汇总.xlsx"],
        },
    )
    assert result["ok"] is False
    assert "工作成果/产品汇总.xlsx" in str(result.get("error") or "")
    assert result.get("finished") is not True


def test_finish_accepts_existing_nonempty_deliverables(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    out = ws / "工作成果"
    out.mkdir()
    target = out / "产品汇总.xlsx"
    target.write_bytes(b"PK\x03\x04fake-xlsx")
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute(
        "finish",
        {
            "summary": "已写入 `工作成果/产品汇总.xlsx`",
            "deliverables": ["工作成果/产品汇总.xlsx"],
        },
    )
    assert result["ok"] is True
    assert result["finished"] is True
    assert result["deliverables"] == ["工作成果/产品汇总.xlsx"]


def test_finish_rejects_empty_deliverable_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    out = ws / "工作成果"
    out.mkdir()
    (out / "空表.xlsx").write_bytes(b"")
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute(
        "finish",
        {"summary": "好了", "deliverables": ["工作成果/空表.xlsx"]},
    )
    assert result["ok"] is False
    assert "空" in str(result.get("error") or "") or "empty" in str(result.get("error") or "").lower()


def test_finish_non_zip_docx_still_ok_but_unverified(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "工作成果").mkdir()
    (ws / "工作成果" / "a.docx").write_text("not-zip", encoding="utf-8")
    emitted: list[tuple] = []

    def _fake_emit(event, **fields):
        emitted.append((event, fields))

    monkeypatch.setattr("office_agent.diagnostic.emit", _fake_emit)
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute("finish", {"summary": "x", "deliverables": ["工作成果/a.docx"]})
    assert result["ok"] is True
    assert result.get("unverified") is True
    assert any(e == "deliverable_claimed" for e, _ in emitted)
    verified = [f for e, f in emitted if e == "deliverable_verified"]
    assert verified
    assert verified[0].get("exists") is True
    assert verified[0].get("kind") == "other"


def test_finish_zip_docx_verified_kind(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    (tmp_path / "skills").mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "工作成果").mkdir()
    (ws / "工作成果" / "a.docx").write_bytes(b"PK\x03\x04docx-body")
    emitted: list[tuple] = []

    def _fake_emit(event, **fields):
        emitted.append((event, fields))

    monkeypatch.setattr("office_agent.diagnostic.emit", _fake_emit)
    ex = ToolExecutor(Workspace(ws), SkillRegistry(), permission_mode="trust")
    result = ex.execute("finish", {"summary": "x", "deliverables": ["工作成果/a.docx"]})
    assert result["ok"] is True
    assert result.get("unverified") is not True
    verified = [f for e, f in emitted if e == "deliverable_verified"]
    assert verified
    assert verified[0].get("kind") == "docx"
