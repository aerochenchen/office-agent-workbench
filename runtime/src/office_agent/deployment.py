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
INTRANET_CIDRS_ENV = "OFFICE_AGENT_INTRANET_CIDRS"
INTRANET_CIDRS_FILENAME = "intranet-cidrs"

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


def _packaged_resource_candidates(name: str) -> list[Path]:
    """Candidate paths for a file next to resources/deployment-profile."""
    candidates: list[Path] = []
    exe = Path(sys.executable).resolve()
    # Packaged layout: {install}/resources/runtime/office-agent-runtime.exe
    candidates.append(exe.parent.parent / name)
    candidates.append(exe.parent / name)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        root = Path(meipass).resolve()
        candidates.append(root.parent / name)
        candidates.append(root / name)
    bundled = os.environ.get("OFFICE_AGENT_BUNDLED", "").strip()
    if bundled:
        candidates.append(Path(bundled).resolve().parent / name)
    return candidates


def read_packaged_deployment_profile() -> str | None:
    """Read resources/deployment-profile next to the packaged runtime.

    The file is the source of truth for a shipped build. Environment variables
    cannot downgrade it.
    """
    for path in _packaged_resource_candidates("deployment-profile"):
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


def _parse_cidr_token(raw: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
    token = raw.strip()
    if not token or token.startswith("#"):
        return None
    try:
        return ipaddress.ip_network(token, strict=False)
    except ValueError:
        return None


def _cidrs_from_text(text: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for line in text.splitlines():
        net = _parse_cidr_token(line)
        if net is not None:
            networks.append(net)
    return networks


def read_packaged_intranet_cidrs() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    for path in _packaged_resource_candidates(INTRANET_CIDRS_FILENAME):
        try:
            if not path.is_file():
                continue
            networks = _cidrs_from_text(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if networks:
            return networks
    return []


def extra_intranet_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Site-specific non-RFC1918 ranges: env first, then packaged intranet-cidrs."""
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    seen: set[str] = set()

    def _add(net: ipaddress.IPv4Network | ipaddress.IPv6Network) -> None:
        key = str(net)
        if key in seen:
            return
        seen.add(key)
        networks.append(net)

    env_raw = os.environ.get(INTRANET_CIDRS_ENV, "")
    for token in env_raw.replace(";", ",").split(","):
        net = _parse_cidr_token(token)
        if net is not None:
            _add(net)
    for net in read_packaged_intranet_cidrs():
        _add(net)
    return networks


def _ip_allowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if _ip_ok(ip):
        return True
    return any(ip in net for net in extra_intranet_networks())


def is_known_public_ai_host(host: str) -> bool:
    h = host.strip().lower().rstrip(".")
    for suffix in PUBLIC_AI_HOST_SUFFIXES:
        if h == suffix or h.endswith("." + suffix):
            return True
    return False


def is_intranet_model_host(host: str, *, resolve: bool = True) -> bool:
    """True when the model host is loopback, private, link-local, or allowlisted.

    Public AI API hostnames are always rejected. Named hosts are resolved so a
    public DNS name cannot be used in the local profile. IP literals must pass
    the same private/loopback/link-local check; non-RFC1918 专网号段 require
    OFFICE_AGENT_INTRANET_CIDRS or a packaged intranet-cidrs file.
    """
    h = (host or "").strip().lower().rstrip(".")
    if not h:
        return False
    if h in {"localhost", "localhost."}:
        return True
    if is_known_public_ai_host(h):
        return False
    try:
        ip = ipaddress.ip_address(h)
        return _ip_allowed(ip)
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
        if not _ip_allowed(ip):
            return False
    return True


def model_host_from_api_base(api_base: str) -> str:
    return (urlparse(api_base or "").hostname or "").strip()
