# Task 9 Report — DONE

**Status:** DONE

**What changed:**
- Replaced placeholder with real `government-document-format` from `公文排版_government-document-format.zip`
- Real `format_gongwen.py` → `bundled/shared-scripts/` and skill `scripts/`
- SKILL.md frontmatter: `tier: light`, `shared_scripts: [format_gongwen]`
- Hermes/`terminal` paths rewritten to `run_shared_script` / `run_skill_script`
- `bundled_seed` now overwrites standard bundle assets on boot
- Added `python-docx` to standard `runtime/requirements.txt` (light skill)

**Tests:** parse SkillMeta OK; full pytest after deps install.
