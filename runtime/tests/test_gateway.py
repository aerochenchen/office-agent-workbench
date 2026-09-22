from office_agent.config import AppConfig
from office_agent.gateway import GatewayError, ModelGateway
import pytest


def test_gateway_module_does_not_import_openai_at_load():
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "src/office_agent/gateway.py"
    text = src.read_text(encoding="utf-8")
    preamble = text.split("class ModelGateway")[0]
    assert "from openai import OpenAI" not in preamble
    assert "from httpx import Timeout" not in preamble
    cfg = AppConfig(
        api_base="http://10.0.0.8:8000/v1",
        api_key="x",
        model="deepseek-v4-flash",
        allowed_hosts=["10.0.0.8"],
    )
    ModelGateway(cfg).assert_allowed()


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


def test_rejects_missing_api_key():
    cfg = AppConfig(
        api_base="https://api.deepseek.com/v1",
        api_key="  ",
        model="deepseek-v4-flash",
        allowed_hosts=["api.deepseek.com"],
    )
    with pytest.raises(GatewayError, match="API Key"):
        ModelGateway(cfg)


def test_local_profile_public_host_sets_error_code():
    from office_agent.config import AppConfig
    from office_agent.gateway import GatewayError, ModelGateway

    cfg = AppConfig(
        api_base="https://api.deepseek.com",
        api_key="k",
        model="m",
        allowed_hosts=["api.deepseek.com"],
        deployment_profile="local",
    )
    try:
        ModelGateway(cfg)
        assert False, "expected GatewayError"
    except GatewayError as e:
        assert e.error_code == "model_host_rejected"
        assert e.host_class == "denied"
