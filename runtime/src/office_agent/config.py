from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

LOCAL_ALLOWED_HOSTS = ("127.0.0.1", "localhost")


@dataclass
class AppConfig:
    api_base: str
    api_key: str
    model: str
    allowed_hosts: list[str]
    permission_mode: str = "standard"
    max_tool_steps: int = 40


def merge_allowed_hosts(api_base: str, current: list[str] | None = None) -> list[str]:
    """Ensure local defaults and the api_base hostname are always allowlisted."""
    result: list[str] = []
    for host in (*LOCAL_ALLOWED_HOSTS, *(current or [])):
        if host and host not in result:
            result.append(host)
    parsed_host = urlparse(api_base).hostname
    if parsed_host and parsed_host not in result:
        result.append(parsed_host)
    return result
