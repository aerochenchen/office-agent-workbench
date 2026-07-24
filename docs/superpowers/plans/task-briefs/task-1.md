### Task 1: Python runtime scaffold + Workspace sandbox

**Files:**
- Create: `runtime/pyproject.toml`
- Create: `runtime/requirements.txt`
- Create: `runtime/src/office_agent/__init__.py`
- Create: `runtime/src/office_agent/paths.py`
- Create: `runtime/src/office_agent/workspace.py`
- Create: `runtime/tests/conftest.py`
- Create: `runtime/tests/test_workspace.py`

**Interfaces:**
- Produces: `Workspace(root: Path)` with `resolve`, `list_dir`, `read_text`, `write_text`; raises `SandboxError` on escape.
- Produces: `app_data_dir() -> Path` honoring `OFFICE_AGENT_DATA`.

- [ ] **Step 1: Write failing tests**

```python
# runtime/tests/test_workspace.py
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
```

- [ ] **Step 2: Run tests — expect fail**

```bash
cd runtime && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/test_workspace.py -v
```

Expected: FAIL (import / not installed)

- [ ] **Step 3: Minimal implementation**

`runtime/requirements.txt` must be exactly light deps (no torch):

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
openai>=1.40.0
pydantic>=2.7.0
pydantic-settings>=2.3.0
pyyaml>=6.0.1
httpx>=0.27.0
pytest>=8.2.0
```

`runtime/pyproject.toml`:

```toml
[project]
name = "office-agent-runtime"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "openai>=1.40.0",
  "pydantic>=2.7.0",
  "pydantic-settings>=2.3.0",
  "pyyaml>=6.0.1",
  "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.2.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

`runtime/src/office_agent/workspace.py`:

```python
from __future__ import annotations
from pathlib import Path


class SandboxError(ValueError):
    pass


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        if not self.root.is_dir():
            raise SandboxError(f"workspace root is not a directory: {self.root}")

    def resolve(self, rel_or_abs: str) -> Path:
        raw = Path(rel_or_abs)
        candidate = (self.root / raw).resolve() if not raw.is_absolute() else raw.resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as e:
            raise SandboxError(f"path escapes workspace: {rel_or_abs}") from e
        return candidate

    def list_dir(self, rel: str = ".") -> list[dict]:
        target = self.resolve(rel)
        if not target.is_dir():
            raise SandboxError(f"not a directory: {rel}")
        out: list[dict] = []
        for p in sorted(target.iterdir(), key=lambda x: x.name.lower()):
            out.append({
                "name": p.name,
                "path": str(p.relative_to(self.root)),
                "is_dir": p.is_dir(),
            })
        return out

    def read_text(self, rel: str, max_bytes: int = 512_000) -> str:
        path = self.resolve(rel)
        if not path.is_file():
            raise SandboxError(f"not a file: {rel}")
        data = path.read_bytes()
        if len(data) > max_bytes:
            raise SandboxError(f"file too large: {rel}")
        return data.decode("utf-8", errors="replace")

    def write_text(self, rel: str, content: str) -> Path:
        path = self.resolve(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path
```

`runtime/src/office_agent/paths.py`:

```python
from __future__ import annotations
import os
from pathlib import Path


def app_data_dir() -> Path:
    override = os.environ.get("OFFICE_AGENT_DATA")
    p = Path(override) if override else Path.home() / ".office-agent"
    p.mkdir(parents=True, exist_ok=True)
    for sub in ("skills", "shared-scripts", "db", "logs"):
        (p / sub).mkdir(exist_ok=True)
    return p
```

`runtime/src/office_agent/__init__.py`:

```python
__version__ = "0.1.0"
```

`runtime/tests/conftest.py`:

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd runtime && source .venv/bin/activate && pytest tests/test_workspace.py -v
```

- [ ] **Step 5: Commit only if user requested**

```bash
git add runtime && git commit -m "feat: add workspace sandbox for office agent runtime"
```

---

