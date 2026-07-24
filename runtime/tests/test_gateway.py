from office_agent.config import AppConfig
from office_agent.gateway import GatewayError, ModelGateway
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
