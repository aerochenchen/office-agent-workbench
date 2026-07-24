from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppConfig:
    api_base: str
    api_key: str
    model: str
    allowed_hosts: list[str]
    permission_mode: str = "standard"
    max_tool_steps: int = 20
