### Task 4: Model gateway (allowlist)

**Files:**
- Create: `runtime/src/office_agent/config.py`
- Create: `runtime/src/office_agent/gateway.py`
- Create: `runtime/tests/test_gateway.py`

**Interfaces:**
- `AppConfig(api_base, api_key, model, allowed_hosts, permission_mode, max_tool_steps)`
- `ModelGateway.assert_allowed()` / `chat(messages, tools=None)`
- Raises `GatewayError` if hostname not in allowlist

- [ ] **Step 1: Failing tests**

```python
from office_agent.config import AppConfig
from office_agent.gateway import ModelGateway, GatewayError
import pytest

def test_rejects_host_not_in_allowlist():
    cfg = AppConfig(
        api_base="https://evil.example/v1",
        api_key="x",
        model="deepseek-v4-flash",
        allowed_hosts=["10.0.0.8"],
    )
    with pytest.raises(GatewayError):
        ModelGateway(cfg)

def test_allows_configured_host():
    cfg = AppConfig(
        api_base="http://10.0.0.8:8000/v1",
        api_key="x",
        model="deepseek-v4-flash",
        allowed_hosts=["10.0.0.8"],
    )
    ModelGateway(cfg).assert_allowed()
```

- [ ] **Step 2–4: Implement with `urllib.parse.urlparse` + `openai.OpenAI`; pytest PASS**

- [ ] **Step 5: Commit if requested** — `feat: add allowlisted OpenAI-compatible model gateway`

---

