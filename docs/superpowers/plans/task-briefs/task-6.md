### Task 6: FastAPI HTTP API

**Files:**
- Create: `runtime/src/office_agent/session_store.py`
- Create: `runtime/src/office_agent/app.py`
- Create: `runtime/tests/test_app_api.py`

**Interfaces (HTTP):**
- `GET /health` → `{ok: true}`
- `POST /workspace/open` `{path}`
- `GET /workspace/tree`
- `GET /skills` (include `tier`, `min_ram_gb`, `enabled`)
- `POST /skills/install` `{path}` or multipart zip
- `POST /skills/{id}/enabled` `{enabled}`
- `POST /config` update api_base / allowed_hosts
- `POST /chat` `{message, attached_paths?, session_id?}` → `{reply, tool_events, session_id}`

- [ ] **Step 1: TestClient health + open workspace test**

- [ ] **Step 2: pytest fail**

- [ ] **Step 3: `create_app()` with process state; wire `/chat` to `run_agent`**

Also add module entry for uvicorn. Example:

```bash
cd runtime && source .venv/bin/activate
uvicorn office_agent.app:app --app-dir src --host 127.0.0.1 --port 8765
```

- [ ] **Step 4: `pytest -v` all runtime tests PASS**

- [ ] **Step 5: Commit if requested** — `feat: expose office agent runtime HTTP API`

---

