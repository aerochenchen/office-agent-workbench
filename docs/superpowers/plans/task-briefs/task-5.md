### Task 5: Agent loop

**Files:**
- Create: `runtime/src/office_agent/agent_loop.py`
- Create: `runtime/tests/test_agent_loop.py`

**Interfaces:**
- `run_agent(user_message, attached_paths, gateway, tools, catalog, max_steps) -> AgentResult`
- `AgentResult(messages, final_text, tool_events)`
- Exports `TOOL_SCHEMAS` matching Task 3 tool names

- [ ] **Step 1: Fake gateway test** — first response returns `workspace_list` tool_call; second returns text `目录已列出`; assert one tool event.

- [ ] **Step 2: pytest fail**

- [ ] **Step 3: Implement loop** — system prompt in 简体中文; inject enabled skill catalog JSON; stop on `finish`, plain text, or `max_steps`.

- [ ] **Step 4: pytest PASS**

- [ ] **Step 5: Commit if requested** — `feat: add agent tool loop with finish and step limit`

---

