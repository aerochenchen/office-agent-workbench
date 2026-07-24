# Task 2 Report: Skill registry (parse, install zip, tier metadata)

**Status:** DONE  
**Commits:** none (per user instruction)  
**Date:** 2026-07-23

## Scope delivered

| File | Action |
|------|--------|
| `runtime/src/office_agent/skills.py` | Created |
| `runtime/tests/test_skills.py` | Created |

## Interfaces

- `SkillMeta` — dataclass with `id`, `name`, `description`, `version`, `tier`, `min_ram_gb`, `permissions`, `shared_scripts`, `path`, `enabled`, `body`.
- `parse_skill_md(text, skill_dir) -> SkillMeta` — YAML frontmatter via regex + PyYAML.
- `SkillRegistry` — `scan`, `install_dir`, `install_zip`, `set_enabled`, `enabled_catalog`; persists enable state in `skills_state.json` under `app_data_dir()`.
- `SkillError(ValueError)` — invalid/missing SKILL.md.

## TDD evidence

### RED (Step 2)

```text
pytest tests/test_skills.py -v
ModuleNotFoundError: No module named 'office_agent.skills'
```

### GREEN (Step 4)

```bash
cd runtime && source .venv/bin/activate && pytest tests/test_skills.py tests/test_workspace.py -v
```

```text
tests/test_skills.py::test_scan_parses_frontmatter PASSED
tests/test_skills.py::test_install_zip_heavy_tier PASSED
tests/test_skills.py::test_reject_without_skill_md PASSED
tests/test_workspace.py (3 tests) PASSED
6 passed in 0.39s
```

## Test summary

- **3/3** new skill tests passed (frontmatter scan, zip install heavy tier + `min_ram_gb`, reject dir without SKILL.md).
- **3/3** Task 1 workspace tests still pass.

## Self-review

| Check | Result |
|-------|--------|
| Consumes `app_data_dir()` from `paths.py` | Yes |
| Tier `light` / `heavy` and optional `min_ram_gb` | Yes |
| Zip extract uses `_tmp_extract` with cleanup | Yes |
| `enabled_catalog` / `set_enabled` implemented (not yet tested in Task 2 spec) | Yes |

## Concerns

- No dedicated tests yet for `set_enabled`, `enabled_catalog`, or malformed frontmatter (future tasks may extend coverage).
- `install_dir` single-child heuristic when extract root has multiple dirs could be ambiguous; current zip layout matches one skill folder.

## Notes for Task 3+

- Registry ready for HTTP/API wiring and tool loop skill catalog injection.
