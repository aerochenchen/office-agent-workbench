from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from openai import OpenAI

from office_agent.config import AppConfig


class GatewayError(ValueError):
    pass


class ModelGateway:
    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self.assert_allowed()
        self._client = OpenAI(base_url=cfg.api_base, api_key=cfg.api_key)

    def assert_allowed(self) -> None:
        host = urlparse(self._cfg.api_base).hostname
        if host is None or host not in self._cfg.allowed_hosts:
            raise GatewayError(
                f"api host not allowlisted: {host!r} (allowed: {self._cfg.allowed_hosts})"
            )

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
        kwargs: dict[str, Any] = {
            "model": self._cfg.model,
            "messages": messages,
        }
        if tools is not None:
            kwargs["tools"] = tools
        return self._client.chat.completions.create(**kwargs)
