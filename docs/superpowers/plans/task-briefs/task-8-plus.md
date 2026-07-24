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

