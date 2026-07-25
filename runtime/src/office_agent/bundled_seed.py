from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from office_agent.paths import app_data_dir


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


def seed_bundled_assets(bundled_root: Path | None = None, *, overwrite: bool = False) -> None:
    """Sync standard bundled skills/scripts into app_data.

    Skills are copied only when missing (overwrite=False by default) so user
    copies are not clobbered on startup. Shared product scripts always refresh.
    Pass overwrite=True to replace existing bundled skill directories.
    """
    src_root = bundled_root or bundled_dir()
    if not src_root.is_dir():
        return

    data = app_data_dir()

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
