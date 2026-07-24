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
