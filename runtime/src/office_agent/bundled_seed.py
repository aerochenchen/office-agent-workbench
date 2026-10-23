from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import yaml

from office_agent.paths import app_data_dir

RETIRED_BUNDLED_SKILL_IDS = frozenset({"brief-deck", "office-visual-design"})


def bundled_dir() -> Path:
    override = os.environ.get("OFFICE_AGENT_BUNDLED")
    if override:
        return Path(override)
    # Packaged sidecar / frozen exe: look next to the binary (Tauri resources).
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for candidate in (
            exe_dir / "bundled",
            exe_dir.parent / "bundled",
            exe_dir.parent.parent / "bundled",
        ):
            if candidate.is_dir():
                return candidate
    # .../runtime/src/office_agent/bundled_seed.py -> repo root
    return Path(__file__).resolve().parents[3] / "bundled"


def _overridden_skill_ids(data_dir: Path) -> set[str]:
    state_path = data_dir / "skills_state.json"
    if not state_path.is_file():
        return set()
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, dict):
        return set()
    bucket = data.get("overridden") or {}
    if not isinstance(bucket, dict):
        return set()
    return {str(k) for k, v in bucket.items() if v}


def _frontmatter_data(md_path: Path) -> dict:
    if not md_path.is_file():
        return {}
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data = yaml.safe_load(parts[1]) or {}
    return data if isinstance(data, dict) else {}


def _frontmatter_display_name(md_path: Path) -> str | None:
    value = str(_frontmatter_data(md_path).get("display_name") or "").strip()
    return value or None


def _version_tuple(raw: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in str(raw or "").split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def _should_refresh_factory(src_md: Path, dest_md: Path) -> bool:
    """Replace factory copy when bundled version is newer. Skip unknown dest versions."""
    src_ver = str(_frontmatter_data(src_md).get("version") or "").strip()
    dest_ver = str(_frontmatter_data(dest_md).get("version") or "").strip()
    if not src_ver or not dest_ver:
        return False
    return _version_tuple(src_ver) > _version_tuple(dest_ver)


def _remove_retired_factory_skills(
    skills_src: Path, skills_dest: Path, overridden: set[str]
) -> None:
    if not skills_dest.is_dir():
        return
    bundled_ids = {
        path.name
        for path in skills_src.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    for skill_id in RETIRED_BUNDLED_SKILL_IDS:
        if skill_id in overridden or skill_id in bundled_ids:
            continue
        stale = skills_dest / skill_id
        if stale.is_dir():
            shutil.rmtree(stale)


def _patch_display_name(md_path: Path, display_name: str) -> bool:
    """Update display_name in SKILL.md frontmatter; preserve body and other keys."""
    text = md_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return False
    parts = text.split("---", 2)
    if len(parts) < 3:
        return False
    data = yaml.safe_load(parts[1]) or {}
    if not isinstance(data, dict):
        return False
    current = str(data.get("display_name") or "").strip()
    want = display_name.strip()
    if not want or current == want:
        return False
    data["display_name"] = want
    dumped = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    body = parts[2]
    if body.startswith("\n"):
        body = body[1:]
    md_path.write_text(f"---\n{dumped}---\n{body}", encoding="utf-8")
    return True


def seed_bundled_assets(bundled_root: Path | None = None, *, overwrite: bool = False) -> None:
    """Sync standard bundled skills/scripts into app_data.

    Skills are copied when missing. Pass overwrite=True to replace existing
    bundled skill directories. Shared product scripts always refresh.

    For existing factory skills that are not marked overridden:
    - if bundled ``version`` is newer, replace the whole directory;
    - otherwise refresh ``display_name`` only.
    Retired factory ids (not overridden) are removed from app_data.
    """
    src_root = bundled_root or bundled_dir()
    if not src_root.is_dir():
        return

    data = app_data_dir()
    overridden = _overridden_skill_ids(data)

    scripts_src = src_root / "shared-scripts"
    scripts_dest = data / "shared-scripts"
    if scripts_src.is_dir():
        scripts_dest.mkdir(parents=True, exist_ok=True)
        for item in scripts_src.iterdir():
            if not item.is_file():
                continue
            target = scripts_dest / item.name
            # Product formatting scripts should always ship with updates.
            shutil.copy2(item, target)

    skills_src = src_root / "skills"
    skills_dest = data / "skills"
    if skills_src.is_dir():
        skills_dest.mkdir(parents=True, exist_ok=True)
        for skill_dir in skills_src.iterdir():
            if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").is_file():
                continue
            target = skills_dest / skill_dir.name
            if target.exists() and overwrite:
                shutil.rmtree(target)
            if not target.exists():
                shutil.copytree(skill_dir, target)
                continue
            if skill_dir.name in overridden:
                continue
            if _should_refresh_factory(skill_dir / "SKILL.md", target / "SKILL.md"):
                shutil.rmtree(target)
                shutil.copytree(skill_dir, target)
                continue
            factory_name = _frontmatter_display_name(skill_dir / "SKILL.md")
            if not factory_name:
                continue
            dest_md = target / "SKILL.md"
            if dest_md.is_file():
                _patch_display_name(dest_md, factory_name)
        _remove_retired_factory_skills(skills_src, skills_dest, overridden)
