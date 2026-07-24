# Task 4 Report: Model gateway (allowlist)

**Status:** DONE  
**Commits:** none (per user instruction)  
**Date:** 2026-07-23

## Scope delivered

| File | Action |
|------|--------|
| `runtime/src/office_agent/config.py` | Created |
| `runtime/src/office_agent/gateway.py` | Created |
| `runtime/tests/test_gateway.py` | Created |

## Interfaces

- `AppConfig(api_base, api_key, model, allowed_hosts, permission_mode="standard", max_tool_steps=20)` — dataclass.
- `ModelGateway(cfg)` — validates host on init via `assert_allowed()`; builds `openai.OpenAI(base_url=..., api_key=...)`.
- `ModelGateway.assert_allowed()` — `urlparse(api_base).hostname` must be in `allowed_hosts`; else `GatewayError`.
- `ModelGateway.chat(messages, tools=None)` — delegates to `chat.completions.create`.

## TDD evidence

### RED (Step 1)

```text
ModuleNotFoundError: No module named 'office_agent.config'
```

### GREEN (Step 2–4)

```bash
cd runtime && .venv/bin/pytest tests/test_gateway.py tests/ -v
```

```text
11 passed (2 gateway + 9 prior)
```

## Acceptance mapping

| Requirement | Met |
|-------------|-----|
| Reject non-allowlisted hostname at gateway construction | Yes (`evil.example` vs `10.0.0.8`) |
| Allow configured host with port in URL | Yes (`http://10.0.0.8:8000/v1`) |
| Host check uses `urlparse(...).hostname` | Yes |

## Concerns / follow-ups

- No unit test for `chat()` (network); Task 5 will use a fake gateway.
- `AppConfig` is in-memory only; env/settings loading likely in a later task.
- IPv6 or literal-IP edge cases not covered; extend allowlist tests if production uses them.
