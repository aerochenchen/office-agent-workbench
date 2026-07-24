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

