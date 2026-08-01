from __future__ import annotations

import os
import re
from pathlib import Path

from office_agent.workspace import DELIVERABLE_SUFFIXES

_PATH_LIKE_SUFFIXES = frozenset({".py", ".txt", ".md", ".json", ".csv", ".yaml", ".yml"}) | DELIVERABLE_SUFFIXES

# 名字匹配此模式的 env 视为敏感凭据，一律不透传给 Skill/工作区脚本，
# 防止恶意或被污染的脚本窃取父进程持有的 token / API key / 密码等。
_SENSITIVE_ENV_RE = re.compile(
    r"(?:^|_)(TOKEN|KEY|SECRET|PASSWORD|PASSWD|CREDENTIAL|CREDENTIALS|AUTH|APIKEY|API_KEY)(?:$|_)",
    re.IGNORECASE,
)
# 即使匹配敏感词也必须保留的业务 env（白名单优先）。
_SENSITIVE_ENV_ALLOWLIST = frozenset({
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
})


def build_script_env(base: dict | None = None) -> dict[str, str]:
    """构建脚本子进程 env：强制 HF/TRANSFORMERS 离线、清代理、剥离敏感凭据。

    安全说明：
    - 代理类 env (HTTP_PROXY/HTTPS_PROXY) 被清除，但这只是「建议性」约束，
      Python socket / urllib 仍可直连。真正的网络硬隔离需在 OS 层
      （Linux unshare -n / Windows 防火墙出站规则 / macOS sandbox-exec）配置。
    - 父进程 env 中名字含 TOKEN/KEY/SECRET/PASSWORD/CREDENTIAL/AUTH 的变量
      一律不透传，防止脚本窃取 OFFICE_AGENT_API_TOKEN 等凭据。
    """
    env = dict(os.environ if base is None else base)
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["NO_PROXY"] = "*"
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        env.pop(key, None)
    # 剥离敏感凭据 env（白名单优先）
    for key in list(env.keys()):
        if key in _SENSITIVE_ENV_ALLOWLIST:
            continue
        if _SENSITIVE_ENV_RE.search(key):
            env.pop(key, None)
    return env


def _looks_like_path(arg: str) -> bool:
    if not arg or arg.startswith("-"):
        return False
    raw = Path(arg)
    if raw.exists():
        return True
    if "/" in arg or "\\" in arg:
        return True
    return raw.suffix.lower() in _PATH_LIKE_SUFFIXES


def _resolve_under_roots(arg: str, roots: list[Path]) -> Path:
    raw = Path(arg).expanduser()
    resolved_roots = [root.resolve() for root in roots]
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw.resolve())
    else:
        for root in resolved_roots:
            candidates.append((root / raw).resolve())
    for candidate in candidates:
        for root in resolved_roots:
            try:
                candidate.relative_to(root)
                return candidate
            except ValueError:
                continue
    raise _tool_error(f"path argument outside allowed roots: {arg}")


def _tool_error(message: str) -> Exception:
    from office_agent.tools import ToolError

    return ToolError(message)


def assert_argv_within_roots(argv: list[str], roots: list[Path]) -> None:
    """
    For each arg that looks like a filesystem path (exists or has path sep
    or suffix .py/.docx/...), resolve and require relative_to one of roots.
    Raise ToolError otherwise.
    """
    if not roots:
        raise _tool_error("no allowed roots configured for script argv")
    for arg in argv:
        if not _looks_like_path(arg):
            continue
        _resolve_under_roots(arg, roots)
