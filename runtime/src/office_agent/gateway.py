from __future__ import annotations

from typing import Any

from office_agent.config import AppConfig
from office_agent.deployment import (
    PROFILE_LOCAL,
    is_intranet_model_host,
    model_host_from_api_base,
)


class GatewayError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "gateway_error",
        host_class: str = "",
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.host_class = host_class


def _classify_host(host: str) -> str:
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return ""
    if h in {"127.0.0.1", "localhost"}:
        return "loopback"
    if is_intranet_model_host(host):
        return "intranet"
    return ""


class ModelGateway:
    def __init__(self, cfg: AppConfig) -> None:
        from httpx import Timeout
        from openai import OpenAI

        self._cfg = cfg
        self.assert_allowed()
        api_key = (cfg.api_key or "").strip()
        if not api_key:
            if cfg.resolved_profile() == PROFILE_LOCAL:
                # OpenAI SDK requires a non-empty string; local servers often skip auth.
                api_key = "not-needed"
            else:
                raise GatewayError(
                    "未配置 API Key，请在设置中填写后再试",
                    host_class=self._host_class(),
                )
        # Long tool-heavy turns (PPT/docx scripting) need more than the SDK default.
        self._client = OpenAI(
            base_url=cfg.api_base,
            api_key=api_key,
            timeout=Timeout(600.0, connect=30.0),
        )

    def _host_class(self) -> str:
        return _classify_host(model_host_from_api_base(self._cfg.api_base or ""))

    def assert_allowed(self) -> None:
        api_base = (self._cfg.api_base or "").strip()
        if not api_base:
            raise GatewayError("未配置模型地址，请在设置中填写后再试")
        host = model_host_from_api_base(api_base)
        if host is None or host == "":
            raise GatewayError("模型地址无效，无法解析主机名")
        if host not in self._cfg.allowed_hosts:
            raise GatewayError(
                f"api host not allowlisted: {host!r} (allowed: {self._cfg.allowed_hosts})",
                host_class=_classify_host(host),
            )
        if self._cfg.resolved_profile() == PROFILE_LOCAL and not is_intranet_model_host(host):
            raise GatewayError(
                "本地部署版本仅允许本机或内网模型地址，"
                f"拒绝公网主机 {host!r}",
                error_code="model_host_rejected",
                host_class="denied",
            )

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
        kwargs: dict[str, Any] = {
            "model": self._cfg.model,
            "messages": messages,
        }
        if tools is not None:
            kwargs["tools"] = tools
        try:
            return self._client.chat.completions.create(**kwargs)
        except GatewayError:
            raise
        except Exception as e:
            code = "timeout" if "timeout" in type(e).__name__.lower() else "gateway_error"
            raise GatewayError(
                str(e),
                error_code=code,
                host_class=self._host_class(),
            ) from e
