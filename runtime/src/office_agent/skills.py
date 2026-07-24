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
