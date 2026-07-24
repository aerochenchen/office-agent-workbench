# Task 1 Report: Python runtime scaffold + Workspace sandbox

**Status:** DONE  
**Commits:** none (per user instruction)  
**Date:** 2026-07-23

## Scope delivered

| File | Action |
|------|--------|
| `runtime/pyproject.toml` | Created |
| `runtime/requirements.txt` | Created (light deps only) |
| `runtime/src/office_agent/__init__.py` | Created |
| `runtime/src/office_agent/paths.py` | Created |
| `runtime/src/office_agent/workspace.py` | Created |
| `runtime/tests/conftest.py` | Created |
| `runtime/tests/test_workspace.py` | Created |

## Interfaces

- `Workspace(root: Path)` — `resolve`, `list_dir`, `read_text`, `write_text`; `SandboxError` on escape or invalid ops.
- `app_data_dir() -> Path` — honors `OFFICE_AGENT_DATA`; ensures `skills`, `shared-scripts`, `db`, `logs` subdirs.

## TDD evidence

### RED (Step 2)

Command (before implementation; only `pytest` in venv):

```text
pytest tests/test_workspace.py -v
```

Result:

```text
ERROR tests/test_workspace.py
ModuleNotFoundError: No module named 'office_agent'
```

### GREEN (Step 4)

Command:

```bash
cd runtime && source .venv/bin/activate && pip install -e ".[dev]" && pytest tests/test_workspace.py -v
```

Result:

```text
tests/test_workspace.py::test_list_and_read_within_root PASSED
tests/test_workspace.py::test_rejects_path_escape PASSED
tests/test_workspace.py::test_write_creates_file PASSED
3 passed in 0.01s
```

## Test summary

- **3/3 passed** — list/read in root, path escape rejection, nested write.

## Self-review

| Check | Result |
|-------|--------|
| Plan file list matches repo | Yes |
| `requirements.txt` has no torch / sentence-transformers / transformers | Yes (grep clean) |
| Sandbox uses `relative_to(root)` after resolve | Yes |
| `pyproject.toml` matches plan | Yes |
| `app_data_dir` unit test | Not in Task 1 spec; covered in later tasks via `monkeypatch` |

## Concerns

- Local venv uses **Python 3.14**; plan specifies `>=3.11` — compatible but not the stated 3.11 CI target until CI is added.
- `task-briefs/task-1.md` was empty; implementation followed `2026-07-23-office-agent-runtime.md` Task 1 section.

## Notes for Task 2+

- `conftest.py` adds `src/` to `sys.path`; editable install also exposes `office_agent` package.
