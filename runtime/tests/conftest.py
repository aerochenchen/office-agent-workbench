import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TEST_API_TOKEN = "test-token"
_orig_request = TestClient.request
_orig_stream = TestClient.stream


def _with_test_auth(kwargs: dict) -> dict:
    headers = dict(kwargs.pop("headers", None) or {})
    lower = {key.lower() for key in headers}
    omit = os.environ.get("OFFICE_AGENT_TEST_OMIT_AUTH") == "1"
    token = os.environ.get("OFFICE_AGENT_API_TOKEN", "").strip()
    if not omit and token and "authorization" not in lower:
        headers["Authorization"] = f"Bearer {token}"
    kwargs["headers"] = headers
    return kwargs


def _request_with_test_token(self, method, url, **kwargs):
    return _orig_request(self, method, url, **_with_test_auth(kwargs))


def _stream_with_test_token(self, method, url, **kwargs):
    return _orig_stream(self, method, url, **_with_test_auth(kwargs))


TestClient.request = _request_with_test_token  # type: ignore[method-assign]
TestClient.stream = _stream_with_test_token  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _clear_deployment_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OFFICE_AGENT_DEPLOYMENT", raising=False)
    monkeypatch.delenv("OFFICE_AGENT_BUNDLED", raising=False)
    monkeypatch.delenv("OFFICE_AGENT_TEST_OMIT_AUTH", raising=False)
    if not os.environ.get("OFFICE_AGENT_API_TOKEN", "").strip():
        monkeypatch.setenv("OFFICE_AGENT_API_TOKEN", _TEST_API_TOKEN)
