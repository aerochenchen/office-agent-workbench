### Task 3: Tools executor + audit (no shell)

**Files:**
- Create: `runtime/src/office_agent/tools.py`
- Create: `runtime/src/office_agent/audit.py`
- Create: `runtime/tests/test_tools.py`

**Interfaces:**
- Produces: `ToolExecutor.execute(name, args) -> dict`
- Tool names: `workspace_list|workspace_read|workspace_write|run_skill_script|run_shared_script|ask_user|finish`
- Child env sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`

- [ ] **Step 1: Write failing tests**

```python
# runtime/tests/test_tools.py
from pathlib import Path
import pytest
from office_agent.workspace import Workspace, SandboxError
from office_agent.skills import SkillRegistry
from office_agent.tools import ToolExecutor
from office_agent.audit import AuditLog

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
    with pytest.raises(SandboxError):
        ex.execute("workspace_write", {"path": "../x.txt", "content": "no"})
```

- [ ] **Step 2: pytest — expect fail**

- [ ] **Step 3: Implement `audit.py` and `tools.py`**

`audit.py`: SQLite table `audit(ts, tool, args_json, ok, detail)`.

`tools.py` core:

```python
def _run_python(self, script: Path, argv: list[str], cwd: Path) -> dict:
    env = os.environ.copy()
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("TRANSFORMERS_OFFLINE", "1")
    proc = subprocess.run(
        [self.python_bin, str(script), *argv],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
```

Reject script names containing `..`. Resolve skill scripts only under `{app_data}/skills/{id}/scripts/`. Shared scripts only under `{app_data}/shared-scripts/{name}.py`.

- [ ] **Step 4: pytest tests/test_tools.py -v — PASS**

- [ ] **Step 5: Commit if requested** — `feat: add sandboxed tool executor without shell`

---

