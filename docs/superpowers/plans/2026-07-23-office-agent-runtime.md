# Office Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付精炼的内网办公 Agent 工作台（Tauri UI + Python Runtime）：工作区对话、Tool Loop、本地 Skill 选装；标准包不含写作 RAG 重依赖。

**Architecture:** Tauri 2 壳管理窗口与工作区选择；本地 Python Runtime（127.0.0.1 HTTP）负责会话、Skill 注册、沙箱工具与 OpenAI 兼容网关；混合型 Skill 以 `SKILL.md` + `scripts/` 安装到 `app_data`；重量 RAG 仅可选包。

**Tech Stack:** Tauri 2 · React · TypeScript · Vite · Python 3.11+ · FastAPI · uvicorn · openai · pydantic · PyYAML · pytest · SQLite

**Spec:** `docs/superpowers/specs/2026-07-23-office-agent-runtime-design.md` (V1.1)

## Global Constraints

- 严格内网：仅白名单 DeepSeek API Host；Skill/模型禁止运行时连公网下载。
- 标准底座 `runtime/requirements.txt` **不得**包含 `torch` / `sentence-transformers` / `transformers`。
- 无通用 `shell` Tool；仅 `run_skill_script` / `run_shared_script`。
- 文件系统沙箱 = 当前工作区根；越界必须拒绝。
- Skill frontmatter 支持 `tier: light|heavy` 与可选 `min_ram_gb`。
- 许可证：仅 MIT/Apache/BSD/PSF 等宽松协议；发版前扫描。
- 平台：Windows 10+ 为交付重点；开发可在 macOS 进行。
- 仅在用户明确要求时 commit；message 用英文 conventional commits。

---

## File Structure (target)

```
/
├── apps/desktop/                 # Tauri + React UI
│   ├── src/
│   │   ├── App.tsx
│   │   ├── lib/runtimeClient.ts
│   │   └── components/
│   │       ├── WorkspaceTree.tsx
│   │       ├── ChatPanel.tsx
│   │       ├── SkillPanel.tsx
│   │       └── SettingsModal.tsx
│   └── src-tauri/                # spawn/kill Python runtime
├── runtime/
│   ├── pyproject.toml
│   ├── requirements.txt          # light only — NO torch
│   ├── src/office_agent/
│   │   ├── config.py
│   │   ├── paths.py
│   │   ├── workspace.py
│   │   ├── session_store.py
│   │   ├── skills.py
│   │   ├── tools.py
│   │   ├── gateway.py
│   │   ├── agent_loop.py
│   │   ├── audit.py
│   │   └── app.py
│   └── tests/
├── bundled/
│   ├── skills/government-document-format/
│   └── shared-scripts/format_gongwen.py
├── optional-skills/
│   └── gongwen-rag-writing/      # NOT in standard package
└── packaging/
    ├── README-standard.md
    └── README-writing-rag-optional.md
```

---

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

### Task 2: Skill registry (parse, install zip, tier metadata)

**Files:**
- Create: `runtime/src/office_agent/skills.py`
- Create: `runtime/tests/test_skills.py`

**Interfaces:**
- Consumes: `app_data_dir()`
- Produces: `SkillMeta`, `SkillRegistry.scan|install_dir|install_zip|set_enabled|enabled_catalog`

- [ ] **Step 1: Write failing tests**

```python
# runtime/tests/test_skills.py
from pathlib import Path
import zipfile
import pytest
from office_agent.skills import SkillRegistry, SkillError

def test_scan_parses_frontmatter(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = tmp_path / "skills" / "demo-light"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo-light\ndescription: 测试轻量技能\nversion: 0.0.1\ntier: light\n"
        "permissions:\n  - workspace_read\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    metas = SkillRegistry().scan()
    assert len(metas) == 1
    assert metas[0].name == "demo-light"
    assert metas[0].tier == "light"

def test_install_zip_heavy_tier(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    src = tmp_path / "pkg" / "heavy-demo"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: heavy-demo\ndescription: 重量\nversion: 0.1.0\ntier: heavy\nmin_ram_gb: 8\n"
        "permissions:\n  - run_python\n---\n\n# H\n",
        encoding="utf-8",
    )
    z = tmp_path / "heavy.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(src / "SKILL.md", arcname="heavy-demo/SKILL.md")
    meta = SkillRegistry().install_zip(z)
    assert meta.tier == "heavy"
    assert meta.min_ram_gb == 8
    assert (tmp_path / "skills" / "heavy-demo" / "SKILL.md").is_file()

def test_reject_without_skill_md(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "readme.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SkillError):
        SkillRegistry().install_dir(bad)
```

- [ ] **Step 2: Run — expect fail**

```bash
cd runtime && source .venv/bin/activate && pytest tests/test_skills.py -v
```

- [ ] **Step 3: Implement `skills.py`**

```python
from __future__ import annotations
import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from office_agent.paths import app_data_dir


class SkillError(ValueError):
    pass


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass
class SkillMeta:
    id: str
    name: str
    description: str
    version: str = "0.0.0"
    tier: str = "light"
    min_ram_gb: int | None = None
    permissions: list[str] = field(default_factory=list)
    shared_scripts: list[str] = field(default_factory=list)
    path: Path | None = None
    enabled: bool = True
    body: str = ""


def parse_skill_md(text: str, skill_dir: Path) -> SkillMeta:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise SkillError("SKILL.md missing YAML frontmatter")
    data = yaml.safe_load(m.group(1)) or {}
    return SkillMeta(
        id=skill_dir.name,
        name=str(data.get("name") or skill_dir.name),
        description=str(data.get("description") or ""),
        version=str(data.get("version") or "0.0.0"),
        tier=str(data.get("tier") or "light"),
        min_ram_gb=int(data["min_ram_gb"]) if data.get("min_ram_gb") is not None else None,
        permissions=list(data.get("permissions") or []),
        shared_scripts=list(data.get("shared_scripts") or []),
        path=skill_dir,
        body=m.group(2),
    )


class SkillRegistry:
    def __init__(self) -> None:
        self.root = app_data_dir()
        self.skills_dir = self.root / "skills"
        self.state_path = self.root / "skills_state.json"
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_path.is_file():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {"enabled": {}}

    def _save_state(self) -> None:
        self.state_path.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def scan(self) -> list[SkillMeta]:
        out: list[SkillMeta] = []
        if not self.skills_dir.is_dir():
            return out
        for d in sorted(self.skills_dir.iterdir()):
            md = d / "SKILL.md"
            if d.is_dir() and md.is_file():
                meta = parse_skill_md(md.read_text(encoding="utf-8"), d)
                meta.enabled = self._state.get("enabled", {}).get(meta.id, True)
                out.append(meta)
        return out

    def set_enabled(self, skill_id: str, enabled: bool) -> None:
        self._state.setdefault("enabled", {})[skill_id] = enabled
        self._save_state()

    def enabled_catalog(self) -> list[dict]:
        return [
            {"id": m.id, "name": m.name, "description": m.description, "tier": m.tier}
            for m in self.scan()
            if m.enabled
        ]

    def install_dir(self, src: Path) -> SkillMeta:
        src = src.resolve()
        if not (src / "SKILL.md").is_file():
            children = [p for p in src.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()]
            if len(children) != 1:
                raise SkillError("SKILL.md not found")
            src = children[0]
        meta = parse_skill_md((src / "SKILL.md").read_text(encoding="utf-8"), src)
        dest = self.skills_dir / meta.id
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        return parse_skill_md((dest / "SKILL.md").read_text(encoding="utf-8"), dest)

    def install_zip(self, zip_path: Path) -> SkillMeta:
        extract = self.root / "_tmp_extract"
        if extract.exists():
            shutil.rmtree(extract)
        extract.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract)
        try:
            return self.install_dir(extract)
        finally:
            shutil.rmtree(extract, ignore_errors=True)
```

- [ ] **Step 4: pytest tests/test_skills.py -v — PASS**

- [ ] **Step 5: Commit if requested** — `feat: add skill registry with tier metadata and zip install`

---

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

### Task 4: Model gateway (allowlist)

**Files:**
- Create: `runtime/src/office_agent/config.py`
- Create: `runtime/src/office_agent/gateway.py`
- Create: `runtime/tests/test_gateway.py`

**Interfaces:**
- `AppConfig(api_base, api_key, model, allowed_hosts, permission_mode, max_tool_steps)`
- `ModelGateway.assert_allowed()` / `chat(messages, tools=None)`
- Raises `GatewayError` if hostname not in allowlist

- [ ] **Step 1: Failing tests**

```python
from office_agent.config import AppConfig
from office_agent.gateway import ModelGateway, GatewayError
import pytest

def test_rejects_host_not_in_allowlist():
    cfg = AppConfig(
        api_base="https://evil.example/v1",
        api_key="x",
        model="deepseek-v4-flash",
        allowed_hosts=["10.0.0.8"],
    )
    with pytest.raises(GatewayError):
        ModelGateway(cfg)

def test_allows_configured_host():
    cfg = AppConfig(
        api_base="http://10.0.0.8:8000/v1",
        api_key="x",
        model="deepseek-v4-flash",
        allowed_hosts=["10.0.0.8"],
    )
    ModelGateway(cfg).assert_allowed()
```

- [ ] **Step 2–4: Implement with `urllib.parse.urlparse` + `openai.OpenAI`; pytest PASS**

- [ ] **Step 5: Commit if requested** — `feat: add allowlisted OpenAI-compatible model gateway`

---

### Task 5: Agent loop

**Files:**
- Create: `runtime/src/office_agent/agent_loop.py`
- Create: `runtime/tests/test_agent_loop.py`

**Interfaces:**
- `run_agent(user_message, attached_paths, gateway, tools, catalog, max_steps) -> AgentResult`
- `AgentResult(messages, final_text, tool_events)`
- Exports `TOOL_SCHEMAS` matching Task 3 tool names

- [ ] **Step 1: Fake gateway test** — first response returns `workspace_list` tool_call; second returns text `目录已列出`; assert one tool event.

- [ ] **Step 2: pytest fail**

- [ ] **Step 3: Implement loop** — system prompt in 简体中文; inject enabled skill catalog JSON; stop on `finish`, plain text, or `max_steps`.

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit if requested** — `feat: add agent tool loop with finish and step limit`

---

### Task 6: FastAPI HTTP API

**Files:**
- Create: `runtime/src/office_agent/session_store.py`
- Create: `runtime/src/office_agent/app.py`
- Create: `runtime/tests/test_app_api.py`

**Interfaces (HTTP):**
- `GET /health` → `{ok: true}`
- `POST /workspace/open` `{path}`
- `GET /workspace/tree`
- `GET /skills` (include `tier`, `min_ram_gb`, `enabled`)
- `POST /skills/install` `{path}` or multipart zip
- `POST /skills/{id}/enabled` `{enabled}`
- `POST /config` update api_base / allowed_hosts
- `POST /chat` `{message, attached_paths?, session_id?}` → `{reply, tool_events, session_id}`

- [ ] **Step 1: TestClient health + open workspace test**

- [ ] **Step 2: pytest fail**

- [ ] **Step 3: `create_app()` with process state; wire `/chat` to `run_agent`**

Also add module entry for uvicorn. Example:

```bash
cd runtime && source .venv/bin/activate
uvicorn office_agent.app:app --app-dir src --host 127.0.0.1 --port 8765
```

- [ ] **Step 4: `pytest -v` all runtime tests PASS**

- [ ] **Step 5: Commit if requested** — `feat: expose office agent runtime HTTP API`

---

### Task 7: Tauri desktop workbench (M0 UI)

**UI Design Direction (审美约束 — 必须遵守):**

面向机关办公，气质应是「沉稳文书工作台」，不是消费级 AI 聊天玩具。

| 维度 | 要求 |
|---|---|
| 视觉方向 | 浅色为主（机关白天办公）；冷灰纸感背景 + 深墨字；点缀色用 muted 青绿或靛蓝（**禁止**紫粉渐变、霓虹 glow、大面积圆角胶囊） |
| 字体 | 中文用「思源黑体 / Noto Sans SC」或系统「PingFang SC / Microsoft YaHei」层级清晰；英文/代码用等宽；**禁止** Inter / Roboto 作为品牌感来源 |
| 布局 | 三栏工作台一体构图；左侧文件树、中间对话为视觉重心、右侧 Skill 次要；留白克制，信息密度中等 |
| 组件 | 默认少用「卡片叠卡片」；工具调用用细分割线/行内状态条，而非厚阴影卡片墙 |
| 动效 | 2–3 处即可：消息淡入、工具状态点、侧栏展开；禁止花哨 |
| 品牌 | 产品名在顶栏清晰可辨；不要用泛 AI 插画填空 |

实现时用 CSS 变量集中定义色板与字号；Task 7 验收含「不像通用 AI 模板页」。

**Files:**
- Create: `apps/desktop/**` (React-TS Tauri template)
- Create: `apps/desktop/src/lib/runtimeClient.ts`
- Create: `apps/desktop/src/components/WorkspaceTree.tsx`
- Create: `apps/desktop/src/components/ChatPanel.tsx`
- Create: `apps/desktop/src/components/SkillPanel.tsx`
- Create: `apps/desktop/src/components/SettingsModal.tsx`
- Modify: `apps/desktop/src-tauri` to spawn runtime on `127.0.0.1:8765`

**Interfaces:**
- `runtimeClient.health|openWorkspace|getTree|chat|listSkills|installSkill|setEnabled|saveConfig`
- Tauri `pick_folder(): Promise<string>`
- SkillPanel shows tier badge; heavy shows `min_ram_gb` confirm on install

- [ ] **Step 1: Scaffold**

```bash
mkdir -p apps && cd apps
npm create tauri-app@latest desktop -- --template react-ts
cd desktop && npm install
```

- [ ] **Step 2: Implement `runtimeClient.ts` against `http://127.0.0.1:8765`**

- [ ] **Step 3: Three-pane App** — 文件树 | 对话（含 tool_events 卡片）| Skill 列表

- [ ] **Step 4: Manual verify**

```bash
# A: runtime
cd runtime && source .venv/bin/activate
uvicorn office_agent.app:app --app-dir src --host 127.0.0.1 --port 8765

# B: UI
cd apps/desktop && npm run tauri dev
```

Expected: 选文件夹 → 树刷新；发消息（无有效 API 时可看到明确错误，不崩溃）。

- [ ] **Step 5: Commit if requested** — `feat: add Tauri workbench UI wired to local runtime`

---

### Task 8: Bundle light format skill stub

**Files:**
- Create: `bundled/shared-scripts/format_gongwen.py`
- Create: `bundled/skills/government-document-format/SKILL.md`
- Modify: runtime startup (`app.py` lifespan) copy bundled → `OFFICE_AGENT_DATA` if missing

- [ ] **Step 1: Placeholder script**

```python
import sys
print(f"[format_gongwen placeholder] args={sys.argv[1:]}")
```

- [ ] **Step 2: SKILL.md with `tier: light`, `shared_scripts: [format_gongwen]`**

- [ ] **Step 3: API/registry test that bundled skill appears after boot seed**

- [ ] **Step 4: Commit if requested** — `feat: bundle light format skill stub for standard package`

---

### Task 9: Migrate real 公文排版 (M3 light)

**Files:**
- Replace `bundled/shared-scripts/format_gongwen.py` with production script from Hermes
- Replace `bundled/skills/government-document-format/` content
- Create sample fixture docx under `runtime/tests/fixtures/` if available

**Steps:**
- [ ] Remove hard-coded `~/.hermes` paths; CLI args only
- [ ] Smoke: chat「排版某某.docx」→ `run_shared_script` ok
- [ ] Commit if requested — `feat: migrate government document format skill`

---

### Task 10: Optional heavy writing RAG skill (M3)

**Files:**
- Create: `optional-skills/gongwen-rag-writing/` (full skill + `models/` dir docs)
- Create: `packaging/README-writing-rag-optional.md`
- Modify scripts: local model only via `GONGWEN_EMBEDDING_MODEL` or `./models/bge-small-zh-v1.5`; index under workspace `.office-agent/rag/gongwen-rag-writing/`

**Steps:**
- [ ] Confirm `runtime/requirements.txt` still has no torch
- [ ] Import zip in UI → heavy warning with min_ram_gb=8
- [ ] Offline build_index + search path on capable machine
- [ ] Commit if requested — `feat: add optional offline gongwen RAG writing skill package`

---

### Task 11: Hardening & dual packaging (M4)

**Files:**
- Create: `packaging/README-standard.md`
- Create: `scripts/check_licenses.sh`
- Add About/NOTICE in desktop UI

**Steps:**
- [ ] `pip-licenses` / SBOM on runtime env; fail on GPL/AGPL
- [ ] Disconnect public net smoke: only allowlisted API; HF download blocked
- [ ] Document standard vs optional writing package
- [ ] Commit if requested — `chore: add license scan and air-gap packaging docs`

---

## Spec Coverage Self-Review

| Spec requirement | Task |
|---|---|
| Lean runtime, no platform RAG | T1–T6, T10 isolation |
| Workspace + chat UI | T7 |
| Skill zip install + tier | T2, T7, T8 |
| Tools without shell | T3 |
| Allowlisted DeepSeek | T4, T11 |
| Light format skill | T8–T9 |
| Heavy writing optional | T10 |
| Standard package no torch | T1 requirements + T10/T11 checks |
| Audit | T3 |
| Machine baseline messaging | T2 frontmatter + T7 SkillPanel + packaging |

**Placeholder scan:** Task 6/7 UI wiring described with concrete endpoints; implementers must not leave TBD hosts.  
**Consistency:** Tool names and `tier` fields match across T2/T3/T5/T7.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-23-office-agent-runtime.md`.

**Two execution options:**

1. **Subagent-Driven（推荐）** — 每任务新开子代理，任务间评审  
2. **Inline Execution** — 本会话按计划连续执行并设检查点  

选哪一种？
