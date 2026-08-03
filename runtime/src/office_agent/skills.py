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
from office_agent.skill_validate import (
    enrich_validation_with_autofix,
    propose_auto_fixes,
    validate_skill_dir,
    validate_skill_text,
)


class SkillError(ValueError):
    def __init__(self, message: str, *, validation: dict | None = None) -> None:
        super().__init__(message)
        self.validation = validation


def _raise_if_invalid(validation: dict) -> None:
    if validation.get("ok"):
        return
    errors = validation.get("errors") or []
    summary = "; ".join(str(e) for e in errors[:3]) or "skill validation failed"
    raise SkillError(summary, validation=validation)


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
SAFE_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def compare_versions(a: str, b: str) -> int:
    """Compare dotted versions. Return -1 if a<b, 0 if equal, 1 if a>b."""

    def parts(v: str) -> list[tuple[int, int | str]]:
        out: list[tuple[int, int | str]] = []
        for p in re.split(r"[.+_-]", (v or "").strip() or "0"):
            if not p:
                continue
            if p.isdigit():
                out.append((0, int(p)))
            else:
                out.append((1, p))
        return out or [(0, 0)]

    pa, pb = parts(a), parts(b)
    n = max(len(pa), len(pb))
    for i in range(n):
        xa = pa[i] if i < len(pa) else (0, 0)
        xb = pb[i] if i < len(pb) else (0, 0)
        if xa == xb:
            continue
        return -1 if xa < xb else 1
    return 0


def list_bundled_skill_ids(bundled_root: Path | None = None) -> set[str]:
    """Skill directory names present in the product bundled/skills catalog."""
    from office_agent.bundled_seed import bundled_dir

    root = bundled_root if bundled_root is not None else bundled_dir()
    skills = root / "skills"
    if not skills.is_dir():
        return set()
    out: set[str] = set()
    for d in skills.iterdir():
        if d.is_dir() and (d / "SKILL.md").is_file():
            out.add(d.name)
    return out


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
    source: str = "user"  # bundled | user
    overridden: bool = False

    @property
    def ui_name(self) -> str:
        """Name shown in UI; prefers display_name when set."""
        return (self.display_name or self.name or self.id).strip() or self.id

    @property
    def can_uninstall(self) -> bool:
        return self.source != "bundled"

    @property
    def can_export(self) -> bool:
        return self.source != "bundled"


def parse_skill_md(text: str, skill_dir: Path) -> SkillMeta:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise SkillError("SKILL.md missing YAML frontmatter")
    data = yaml.safe_load(m.group(1)) or {}
    name = str(data.get("name") or skill_dir.name)
    skill_id = _slug_id(name, fallback=_slug_id(skill_dir.name))
    display_name = str(data.get("display_name") or data.get("title") or "").strip()
    return SkillMeta(
        id=skill_id,
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
        catalog = list_bundled_skill_ids()
        overridden = self._state.get("overridden") or {}
        for d in sorted(self.skills_dir.iterdir()):
            md = d / "SKILL.md"
            if d.is_dir() and md.is_file():
                meta = parse_skill_md(md.read_text(encoding="utf-8"), d)
                meta.enabled = self._state.get("enabled", {}).get(meta.id, True)
                meta.source = "bundled" if meta.id in catalog else "user"
                meta.overridden = bool(overridden.get(meta.id))
                out.append(meta)
        return out

    def is_bundled_id(self, skill_id: str) -> bool:
        return skill_id in list_bundled_skill_ids()

    def set_overridden(self, skill_id: str, value: bool) -> None:
        bucket = self._state.setdefault("overridden", {})
        if value:
            bucket[skill_id] = True
        elif skill_id in bucket:
            del bucket[skill_id]
        self._save_state()

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
        catalog = list_bundled_skill_ids()
        source = meta.source or ("bundled" if meta.id in catalog else "user")
        overridden = bool(meta.overridden)
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
            "source": source,
            "overridden": overridden,
            "can_uninstall": source != "bundled",
            "can_export": source != "bundled",
        }

    def replace_info(self, incoming: SkillMeta) -> dict | None:
        """Describe conflict when installing over an existing skill (if any)."""
        dest = self.skills_dir / incoming.id
        if not dest.is_dir() or not (dest / "SKILL.md").is_file():
            if self.is_bundled_id(incoming.id):
                return {
                    "existing_id": incoming.id,
                    "existing_version": None,
                    "incoming_version": incoming.version,
                    "is_bundled": True,
                    "installed": False,
                    "requires_force": False,
                    "will_override_bundled": True,
                }
            return None
        existing = parse_skill_md((dest / "SKILL.md").read_text(encoding="utf-8"), dest)
        is_bundled = self.is_bundled_id(incoming.id)
        requires_force = is_bundled and compare_versions(incoming.version, existing.version) < 0
        return {
            "existing_id": existing.id,
            "existing_version": existing.version,
            "incoming_version": incoming.version,
            "is_bundled": is_bundled,
            "installed": True,
            "requires_force": requires_force,
            "will_override_bundled": is_bundled,
        }

    def inspect_path(self, path: Path) -> SkillMeta:
        """Parse Skill metadata from dir / zip / md without installing."""
        meta, _ = self.inspect_with_validation(path)
        return meta

    def inspect_with_validation(self, path: Path) -> tuple[SkillMeta, dict]:
        """Parse metadata and run lightweight validation (does not install)."""
        path = path.expanduser().resolve()
        if not path.exists():
            raise SkillError(f"path not found: {path}")
        if path.is_dir():
            root = _resolve_skill_root(path)
            text = (root / "SKILL.md").read_text(encoding="utf-8")
            meta = parse_skill_md(text, root)
            validation = enrich_validation_with_autofix(
                validate_skill_dir(root),
                text=text,
                skill_id=root.name,
                skill_dir=root,
            )
            return meta, validation
        if path.is_file() and path.suffix.lower() == ".zip":
            return self._inspect_zip_with_validation(path)
        if path.is_file() and (path.suffix.lower() == ".md" or path.name == "SKILL.md"):
            text = path.read_text(encoding="utf-8")
            fallback = path.stem if path.name.lower() != "skill.md" else path.parent.name
            skill_id = _skill_id_from_text(text, fallback)
            meta = parse_skill_md(text, Path(skill_id))
            validation = enrich_validation_with_autofix(
                validate_skill_text(text, skill_id),
                text=text,
                skill_id=skill_id,
            )
            return meta, validation
        raise SkillError("unsupported package: use a Skill folder, .zip, or .md / SKILL.md")

    def _inspect_zip_with_validation(self, zip_path: Path) -> tuple[SkillMeta, dict]:
        with tempfile.TemporaryDirectory(prefix="oa-skill-inspect-") as tmp:
            extract = Path(tmp)
            with zipfile.ZipFile(zip_path, "r") as zf:
                _safe_extractall(zf, extract)
            root = _resolve_skill_root(extract)
            text = (root / "SKILL.md").read_text(encoding="utf-8")
            meta = parse_skill_md(text, root)
            validation = enrich_validation_with_autofix(
                validate_skill_dir(root),
                text=text,
                skill_id=root.name,
                skill_dir=root,
            )
            return meta, validation

    def install_path(
        self,
        path: Path,
        *,
        enabled: bool = True,
        apply_fixes: bool = False,
        force_overwrite: bool = False,
    ) -> SkillMeta:
        """Install from folder, zip, or single markdown file."""
        path = path.expanduser().resolve()
        if not path.exists():
            raise SkillError(f"path not found: {path}")
        if path.is_dir():
            meta = self.install_dir(
                path, apply_fixes=apply_fixes, force_overwrite=force_overwrite
            )
        elif path.is_file() and path.suffix.lower() == ".zip":
            meta = self.install_zip(
                path, apply_fixes=apply_fixes, force_overwrite=force_overwrite
            )
        elif path.is_file() and (path.suffix.lower() == ".md" or path.name == "SKILL.md"):
            meta = self.install_md(
                path, apply_fixes=apply_fixes, force_overwrite=force_overwrite
            )
        else:
            raise SkillError("unsupported package: use a Skill folder, .zip, or .md / SKILL.md")
        self.set_enabled(meta.id, enabled)
        meta.enabled = enabled
        catalog = list_bundled_skill_ids()
        meta.source = "bundled" if meta.id in catalog else "user"
        meta.overridden = bool((self._state.get("overridden") or {}).get(meta.id))
        return meta

    @staticmethod
    def _apply_fixes_on_dest(dest: Path) -> list[str]:
        md = dest / "SKILL.md"
        text = md.read_text(encoding="utf-8")
        fixed, fixes = propose_auto_fixes(text, dest.name)
        if fixes:
            md.write_text(fixed, encoding="utf-8")
        return fixes

    def _gate_bundled_replace(self, incoming: SkillMeta, *, force_overwrite: bool) -> None:
        info = self.replace_info(incoming)
        if not info or not info.get("is_bundled"):
            return
        if info.get("requires_force") and not force_overwrite:
            cur = info.get("existing_version") or "?"
            raise SkillError(
                f"预置技能「{incoming.id}」新包版本 {incoming.version} 低于已安装 "
                f"{cur}；如需强制覆盖请勾选强制覆盖"
            )

    def _finish_install(self, dest: Path, meta: SkillMeta) -> SkillMeta:
        if self.is_bundled_id(meta.id):
            self.set_overridden(meta.id, True)
        installed = parse_skill_md((dest / "SKILL.md").read_text(encoding="utf-8"), dest)
        catalog = list_bundled_skill_ids()
        installed.source = "bundled" if installed.id in catalog else "user"
        installed.overridden = bool((self._state.get("overridden") or {}).get(installed.id))
        return installed

    def install_dir(
        self,
        src: Path,
        *,
        apply_fixes: bool = False,
        force_overwrite: bool = False,
    ) -> SkillMeta:
        src = _resolve_skill_root(src)
        validation = validate_skill_dir(src)
        if not validation.get("ok") and not apply_fixes:
            _raise_if_invalid(validation)
        meta = parse_skill_md((src / "SKILL.md").read_text(encoding="utf-8"), src)
        self._gate_bundled_replace(meta, force_overwrite=force_overwrite)
        dest = self.skills_dir / meta.id
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        if apply_fixes:
            self._apply_fixes_on_dest(dest)
        _raise_if_invalid(validate_skill_dir(dest))
        return self._finish_install(dest, meta)

    def install_zip(
        self,
        zip_path: Path,
        *,
        apply_fixes: bool = False,
        force_overwrite: bool = False,
    ) -> SkillMeta:
        with tempfile.TemporaryDirectory(prefix="oa-skill-install-") as tmp:
            extract = Path(tmp)
            with zipfile.ZipFile(zip_path, "r") as zf:
                _safe_extractall(zf, extract)
            return self.install_dir(
                extract, apply_fixes=apply_fixes, force_overwrite=force_overwrite
            )

    def install_md(
        self,
        md_path: Path,
        *,
        apply_fixes: bool = False,
        force_overwrite: bool = False,
    ) -> SkillMeta:
        """Install a lightweight prompt-only Skill from a single markdown file."""
        md_path = md_path.resolve()
        text = md_path.read_text(encoding="utf-8")
        fallback = md_path.stem if md_path.name.lower() != "skill.md" else md_path.parent.name
        skill_id = _skill_id_from_text(text, fallback)
        meta = parse_skill_md(text, Path(skill_id))
        validation = validate_skill_text(text, skill_id)
        if not validation.get("ok"):
            if not apply_fixes:
                _raise_if_invalid(validation)
            text, fixes = propose_auto_fixes(text, skill_id)
            if not fixes:
                _raise_if_invalid(validation)
            _raise_if_invalid(validate_skill_text(text, skill_id))
            meta = parse_skill_md(text, Path(skill_id))
        self._gate_bundled_replace(meta, force_overwrite=force_overwrite)
        dest = self.skills_dir / skill_id
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        (dest / "SKILL.md").write_text(text, encoding="utf-8")
        return self._finish_install(dest, meta)

    def restore_bundled(self, skill_id: str) -> SkillMeta:
        """Replace installed copy with the factory skill from bundled/skills."""
        if (
            not skill_id
            or skill_id in (".", "..")
            or ".." in skill_id
            or "/" in skill_id
            or "\\" in skill_id
        ):
            raise SkillError(f"invalid skill_id: {skill_id}")
        if not self.is_bundled_id(skill_id):
            raise SkillError(f"仅预置技能可恢复出厂版本: {skill_id}")
        from office_agent.bundled_seed import bundled_dir

        src = bundled_dir() / "skills" / skill_id
        if not src.is_dir() or not (src / "SKILL.md").is_file():
            raise SkillError(f"出厂技能包缺失: {skill_id}")
        dest = self.skills_dir / skill_id
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        self.set_overridden(skill_id, False)
        meta = parse_skill_md((dest / "SKILL.md").read_text(encoding="utf-8"), dest)
        meta.source = "bundled"
        meta.overridden = False
        meta.enabled = self._state.get("enabled", {}).get(skill_id, True)
        return meta

    def uninstall(self, skill_id: str) -> None:
        if (
            not skill_id
            or skill_id in (".", "..")
            or ".." in skill_id
            or "/" in skill_id
            or "\\" in skill_id
        ):
            raise SkillError(f"invalid skill_id: {skill_id}")
        if self.is_bundled_id(skill_id):
            raise SkillError("预置技能不可卸载；可停用，或使用「恢复预置」还原出厂版本")
        skills_root = self.skills_dir.resolve()
        dest = (self.skills_dir / skill_id).resolve()
        try:
            dest.relative_to(skills_root)
        except ValueError as e:
            raise SkillError(f"invalid skill_id: {skill_id}") from e
        if not dest.is_dir() or not (dest / "SKILL.md").is_file():
            raise SkillError(f"skill not found: {skill_id}")
        shutil.rmtree(dest)
        enabled = self._state.get("enabled", {})
        if skill_id in enabled:
            del enabled[skill_id]
        overridden = self._state.get("overridden", {})
        if skill_id in overridden:
            del overridden[skill_id]
        self._save_state()
