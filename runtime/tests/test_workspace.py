from pathlib import Path
import pytest
from office_agent.workspace import Workspace, SandboxError


def test_list_and_read_within_root(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    ws = Workspace(tmp_path)
    names = {e["name"] for e in ws.list_dir(".")}
    assert "a.txt" in names
    assert ws.read_text("a.txt") == "hello"


def test_rejects_path_escape(tmp_path: Path):
    ws = Workspace(tmp_path)
    with pytest.raises(SandboxError):
        ws.resolve("../outside.txt")


def test_write_creates_file(tmp_path: Path):
    ws = Workspace(tmp_path)
    ws.write_text("out/note.md", "# ok")
    assert (tmp_path / "out" / "note.md").read_text(encoding="utf-8") == "# ok"


def test_agent_work_dir_created_with_readme(tmp_path: Path):
    from office_agent.workspace import AGENT_OUTPUT_REL, AGENT_WORK_REL

    ws = Workspace(tmp_path)
    ws.ensure_layout()
    work = tmp_path / AGENT_WORK_REL
    out = tmp_path / AGENT_OUTPUT_REL
    assert work.is_dir()
    assert out.is_dir()
    assert "output" in (work / "README.txt").read_text(encoding="utf-8")
    assert "成果" in (out / "README.txt").read_text(encoding="utf-8")
