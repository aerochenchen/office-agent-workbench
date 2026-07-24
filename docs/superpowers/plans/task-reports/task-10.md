# Task 10 Report — DONE (skill code migrated; model weights not vendored)

**Status:** DONE_WITH_CONCERNS

**What changed:**
- Migrated `gongwen-rag-writing` from zip → `optional-skills/gongwen-rag-writing/`
- Frontmatter: `tier: heavy`, `min_ram_gb: 8`, `shared_scripts: [format_gongwen]`
- Added `scripts/model_path.py` — local `models/bge-small-zh-v1.5` or `GONGWEN_EMBEDDING_MODEL`; fail closed when HF offline
- Patched `build_index.py` / `search_*.py` to use `resolve_embedding_model`
- Default index path: workspace `.office-agent/rag/gongwen-rag-writing/index.json`
- `requirements.txt` under optional skill (torch etc.) — not in standard runtime
- Updated packaging README

**Concerns:**
- Zip did **not** include embedding model weights; operators must place `models/bge-small-zh-v1.5/` or set env before use.
- Optional deps (torch/sentence-transformers) not installed in standard venv by design.
