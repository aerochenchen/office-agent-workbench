from office_agent.config import AppConfig
from office_agent.deployment import (
    PROFILE_LOCAL,
    PROFILE_STANDARD,
    is_intranet_model_host,
    is_known_public_ai_host,
    resolve_deployment_profile,
)
from office_agent.gateway import GatewayError, ModelGateway
import pytest


def test_env_local_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFICE_AGENT_DEPLOYMENT", "local")
    assert resolve_deployment_profile("standard") == PROFILE_LOCAL


def test_known_public_ai_hosts() -> None:
    assert is_known_public_ai_host("api.deepseek.com")
    assert is_known_public_ai_host("api.openai.com")
    assert not is_known_public_ai_host("10.0.0.8")
    assert not is_known_public_ai_host("llm.unit.local")


def test_intranet_host_literals() -> None:
    assert is_intranet_model_host("127.0.0.1", resolve=False)
    assert is_intranet_model_host("10.0.0.8", resolve=False)
    assert is_intranet_model_host("192.168.1.2", resolve=False)
    assert not is_intranet_model_host("api.deepseek.com", resolve=False)


def test_intranet_host_allows_any_ip_literal() -> None:
    """专网常用非 RFC1918 号段，按 IP 字面量放行；公网厂商域名仍拒绝。"""
    assert is_intranet_model_host("88.12.1.2", resolve=False)
    assert is_intranet_model_host("1.1.1.1", resolve=False)
    assert is_intranet_model_host("::1", resolve=False)
    assert not is_intranet_model_host("api.deepseek.com", resolve=False)
    assert not is_intranet_model_host("example.com", resolve=False)


def test_env_cannot_downgrade_packaged_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "office_agent.deployment.read_packaged_deployment_profile",
        lambda: PROFILE_LOCAL,
    )
    monkeypatch.setenv("OFFICE_AGENT_DEPLOYMENT", "standard")
    assert resolve_deployment_profile("standard") == PROFILE_LOCAL


def test_env_can_tighten_packaged_standard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "office_agent.deployment.read_packaged_deployment_profile",
        lambda: PROFILE_STANDARD,
    )
    monkeypatch.setenv("OFFICE_AGENT_DEPLOYMENT", "local")
    assert resolve_deployment_profile("standard") == PROFILE_LOCAL


def test_local_gateway_rejects_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OFFICE_AGENT_DEPLOYMENT", raising=False)
    cfg = AppConfig(
        api_base="https://api.deepseek.com",
        api_key="x",
        model="deepseek-v4-flash",
        allowed_hosts=["api.deepseek.com", "127.0.0.1", "localhost"],
        deployment_profile=PROFILE_LOCAL,
    )
    with pytest.raises(GatewayError, match="本地部署"):
        ModelGateway(cfg)


def test_local_gateway_allows_private_ip() -> None:
    cfg = AppConfig(
        api_base="http://10.0.0.8:8000/v1",
        api_key="x",
        model="local-llm",
        allowed_hosts=["10.0.0.8", "127.0.0.1", "localhost"],
        deployment_profile=PROFILE_LOCAL,
    )
    ModelGateway(cfg).assert_allowed()


def test_local_gateway_allows_public_looking_ip() -> None:
    cfg = AppConfig(
        api_base="http://88.12.1.2:9081/v1",
        api_key="x",
        model="Qwen3.8-27B",
        allowed_hosts=["88.12.1.2", "127.0.0.1", "localhost"],
        deployment_profile=PROFILE_LOCAL,
    )
    ModelGateway(cfg).assert_allowed()


def test_local_gateway_allows_empty_api_key() -> None:
    cfg = AppConfig(
        api_base="http://10.0.0.8:9081/v1",
        api_key="",
        model="Qwen3.8-27B",
        allowed_hosts=["10.0.0.8", "127.0.0.1", "localhost"],
        deployment_profile=PROFILE_LOCAL,
    )
    ModelGateway(cfg)


def test_local_gateway_rejects_empty_base() -> None:
    cfg = AppConfig(
        api_base="",
        api_key="x",
        model="local-llm",
        allowed_hosts=["127.0.0.1"],
        deployment_profile=PROFILE_LOCAL,
    )
    with pytest.raises(GatewayError, match="未配置模型地址"):
        ModelGateway(cfg)
