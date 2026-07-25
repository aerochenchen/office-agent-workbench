from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from office_agent.paths import app_data_dir


class SkillError(ValueError):
    pass


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")


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
    display_name: str = ""

    @property
    def ui_name(self) -> str:
        """Name shown in UI; prefers display_name when set."""
        return (self.display_name or self.name or self.id).strip() or self.id


def parse_skill_md(text: str, skill_dir: Path) -> SkillMeta:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise SkillError("SKILL.md missing YAML frontmatter")
    data = yaml.safe_load(m.group(1)) or {}
    name = str(data.get("name") or skill_dir.name)
    display_name = str(data.get("display_name") or data.get("title") or "").strip()
    return SkillMeta(
        id=skill_dir.name,
        name=name,
        description=str(data.get("description") or ""),
        version=str(data.get("version") or "0.0.0"),
        tier=str(data.get("tier") or "light"),
        min_ram_gb=int(data["min_ram_gb"]) if data.get("min_ram_gb") is not None else None,
        permissions=list(data.get("permissions") or []),
        shared_scripts=list(data.get("shared_scripts") or []),
        path=skill_dir,
        body=m.group(2),
        display_name=display_name,
    )


def _slug_id(raw: str, fallback: str = "skill") -> str:
    text = (raw or "").strip() or fallback
    slug = SAFE_ID_RE.sub("-", text).strip("-_.")
    return slug or fallback


def _skill_id_from_text(text: str, fallback: str) -> str:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise SkillError("SKILL.md missing YAML frontmatter")
    data = yaml.safe_load(m.group(1)) or {}
    return _slug_id(str(data.get("name") or fallback), fallback=_slug_id(fallback))


def _resolve_skill_root(src: Path) -> Path:
    """Return the directory that directly contains SKILL.md."""
    src = src.resolve()
    if (src / "SKILL.md").is_file():
        return src
    if not src.is_dir():
        raise SkillError("SKILL.md not found")
    children = [p for p in src.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()]
    if len(children) != 1:
        raise SkillError("SKILL.md not found")
    return children[0]


def _safe_extractall(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    for info in zf.infolist():
        name = info.filename
        if not name or name.endswith("/"):
            target_check = name.rstrip("/")
        else:
            target_check = name
        parts = Path(target_check).parts
        if Path(target_check).is_absolute() or any(p == ".." for p in parts):
            raise SkillError(f"unsafe zip entry: {name}")
        raw = name.replace("\\", "/")
        if raw.startswith("/") or raw.startswith("../") or "/../" in f"/{raw}/" or (
            len(raw) > 1 and raw[1] == ":"
        ):
            raise SkillError(f"unsafe zip entry: {name}")
        target = (dest / name).resolve()
        try:
            target.relative_to(dest)
        except ValueError as e:
            raise SkillError(f"unsafe zip entry: {name}") from e
    zf.extractall(dest)


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
            {
                "id": m.id,
                "name": m.ui_name,
                "description": m.description,
                "tier": m.tier,
            }
            for m in self.scan()
            if m.enabled
        ]

    def meta_payload(self, meta: SkillMeta) -> dict:
        return {
            "id": meta.id,
            "name": meta.ui_name,
            "display_name": meta.display_name or meta.ui_name,
            "description": meta.description,
            "version": meta.version,
            "tier": meta.tier,
            "min_ram_gb": meta.min_ram_gb,
            "permissions": list(meta.permissions),
            "shared_scripts": list(meta.shared_scripts),
            "enabled": meta.enabled,
        }

    def inspect_path(self, path: Path) -> SkillMeta:
        """Parse Skill metadata from dir / zip / md without installing."""
        path = path.expanduser().resolve()
        if not path.exists():
            raise SkillError(f"path not found: {path}")
        if path.is_dir():
            root = _resolve_skill_root(path)
            return parse_skill_md((root / "SKILL.md").read_text(encoding="utf-8"), root)
        if path.is_file() and path.suffix.lower() == ".zip":
            return self._inspect_zip(path)
        if path.is_file() and (path.suffix.lower() == ".md" or path.name == "SKILL.md"):
            text = path.read_text(encoding="utf-8")
            fallback = path.stem if path.name.lower() != "skill.md" else path.parent.name
            skill_id = _skill_id_from_text(text, fallback)
            return parse_skill_md(text, Path(skill_id))
        raise SkillError("unsupported package: use a Skill folder, .zip, or .md / SKILL.md")

    def _inspect_zip(self, zip_path: Path) -> SkillMeta:
        with tempfile.TemporaryDirectory(prefix="oa-skill-inspect-") as tmp:
            extract = Path(tmp)
            with zipfile.ZipFile(zip_path, "r") as zf:
                _safe_extractall(zf, extract)
            root = _resolve_skill_root(extract)
            return parse_skill_md((root / "SKILL.md").read_text(encoding="utf-8"), root)

    def install_path(self, path: Path, *, enabled: bool = True) -> SkillMeta:
        """Install from folder, zip, or single markdown file."""
        path = path.expanduser().resolve()
        if not path.exists():
            raise SkillError(f"path not found: {path}")
        if path.is_dir():
            meta = self.install_dir(path)
        elif path.is_file() and path.suffix.lower() == ".zip":
            meta = self.install_zip(path)
        elif path.is_file() and (path.suffix.lower() == ".md" or path.name == "SKILL.md"):
            meta = self.install_md(path)
        else:
            raise SkillError("unsupported package: use a Skill folder, .zip, or .md / SKILL.md")
        self.set_enabled(meta.id, enabled)
        meta.enabled = enabled
        return meta

    def install_dir(self, src: Path) -> SkillMeta:
        src = _resolve_skill_root(src)
        meta = parse_skill_md((src / "SKILL.md").read_text(encoding="utf-8"), src)
        dest = self.skills_dir / meta.id
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        return parse_skill_md((dest / "SKILL.md").read_text(encoding="utf-8"), dest)

    def install_zip(self, zip_path: Path) -> SkillMeta:
        extract = self.root / "_tmp_extract"
        if extract.exists():
            shutil.rmtree(extract)
        extract.mkdir(parents=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            _safe_extractall(zf, extract)
        try:
            return self.install_dir(extract)
        finally:
            shutil.rmtree(extract, ignore_errors=True)

    def install_md(self, md_path: Path) -> SkillMeta:
        """Install a lightweight prompt-only Skill from a single markdown file."""
        md_path = md_path.resolve()
        text = md_path.read_text(encoding="utf-8")
        fallback = md_path.stem if md_path.name.lower() != "skill.md" else md_path.parent.name
        skill_id = _skill_id_from_text(text, fallback)
        # Validate frontmatter before writing
        parse_skill_md(text, Path(skill_id))
        dest = self.skills_dir / skill_id
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        (dest / "SKILL.md").write_text(text, encoding="utf-8")
        return parse_skill_md((dest / "SKILL.md").read_text(encoding="utf-8"), dest)

    def uninstall(self, skill_id: str) -> None:
        dest = self.skills_dir / skill_id
        if not dest.is_dir() or not (dest / "SKILL.md").is_file():
            raise SkillError(f"skill not found: {skill_id}")
        shutil.rmtree(dest)
        enabled = self._state.get("enabled", {})
        if skill_id in enabled:
            del enabled[skill_id]
            self._save_state()
