"""Deployment profiles: standard (may use public models) vs local (intranet-only)."""

from __future__ import annotations

import ipaddress
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

PROFILE_STANDARD = "standard"
PROFILE_LOCAL = "local"
_VALID_PROFILES = frozenset({PROFILE_STANDARD, PROFILE_LOCAL})

DEPLOYMENT_ENV = "OFFICE_AGENT_DEPLOYMENT"

# Public AI APIs that must never be used in the local/intranet profile.
PUBLIC_AI_HOST_SUFFIXES = (
    "deepseek.com",
    "openai.com",
    "anthropic.com",
    "googleapis.com",
    "google.com",
    "azure.com",
    "openai.azure.com",
    "cloudflare.com",
    "x.ai",
    "together.ai",
    "groq.com",
    "mistral.ai",
    "cohere.ai",
    "cohere.com",
)


def _normalize_profile_token(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    if value in {"local", "intranet", "airgap", "onprem"}:
        return PROFILE_LOCAL
    if value in {"standard", "cloud", "public"}:
        return PROFILE_STANDARD
    if value in _VALID_PROFILES:
        return value
    return None


def read_packaged_deployment_profile() -> str | None:
    """Read resources/deployment-profile next to the packaged runtime.

    The file is the source of truth for a shipped build. Environment variables
    cannot downgrade it.
    """
    candidates: list[Path] = []
    exe = Path(sys.executable).resolve()
    # Packaged layout: {install}/resources/runtime/office-agent-runtime.exe
    candidates.append(exe.parent.parent / "deployment-profile")
    candidates.append(exe.parent / "deployment-profile")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        root = Path(meipass).resolve()
        candidates.append(root.parent / "deployment-profile")
        candidates.append(root / "deployment-profile")
    bundled = os.environ.get("OFFICE_AGENT_BUNDLED", "").strip()
    if bundled:
        candidates.append(Path(bundled).resolve().parent / "deployment-profile")
    for path in candidates:
        try:
            if not path.is_file():
                continue
            profile = _normalize_profile_token(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if profile:
            return profile
    return None


def resolve_deployment_profile(configured: str | None = None) -> str:
    """Packaged profile file wins. Env may only tighten standard to local."""
    packaged = read_packaged_deployment_profile()
    configured_profile = _normalize_profile_token(configured)
    base = packaged or configured_profile or PROFILE_STANDARD
    env_profile = _normalize_profile_token(os.environ.get(DEPLOYMENT_ENV, ""))
    if env_profile == PROFILE_LOCAL:
        return PROFILE_LOCAL
    if env_profile == PROFILE_STANDARD and base == PROFILE_LOCAL:
        return PROFILE_LOCAL
    if env_profile == PROFILE_STANDARD:
        return PROFILE_STANDARD
    return base


def is_local_profile(profile: str | None = None) -> bool:
    return resolve_deployment_profile(profile) == PROFILE_LOCAL


def _ip_ok(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(ip.is_loopback or ip.is_private or ip.is_link_local)


def is_known_public_ai_host(host: str) -> bool:
    h = host.strip().lower().rstrip(".")
    for suffix in PUBLIC_AI_HOST_SUFFIXES:
        if h == suffix or h.endswith("." + suffix):
            return True
    return False


def is_intranet_model_host(host: str, *, resolve: bool = True) -> bool:
    """True when the model host is loopback, private, link-local, or an intranet name.

    Public AI API hostnames are always rejected. IP literals must themselves be
    loopback, private, or link-local. Named hosts are resolved so a public DNS
    name cannot be used in the local profile.
    """
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return False
    if h in {"localhost", "localhost."}:
        return True
    if is_known_public_ai_host(h):
        return False
    try:
        return _ip_ok(ipaddress.ip_address(h))
    except ValueError:
        pass
    if h.endswith(".local") or h.endswith(".lan") or h.endswith(".intranet"):
        return True
    if not resolve:
        return False
    try:
        infos = socket.getaddrinfo(h, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        if not _ip_ok(ip):
            return False
    return True


def model_host_from_api_base(api_base: str) -> str:
    return (urlparse(api_base or "").hostname or "").strip()
