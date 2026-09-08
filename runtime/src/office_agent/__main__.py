"""CLI entry: ``python -m office_agent`` or the packaged sidecar exe."""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

_LOOPBACK_NAMES = frozenset({"localhost", "localhost."})


def _is_loopback_host(host: str) -> bool:
    """判断绑定地址是否仅本机回环。无法解析为 IP 的（如域名）按非回环处理。"""
    h = host.strip().lower()
    if h in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def assert_bind_safety(host: str, token: str | None) -> None:
    """M11 硬校验：绑非回环地址且未配置 API token 时拒绝启动。

    否则该进程会成为对网络开放的远程调用服务（/chat 可驱动写文件、跑脚本）。
    """
    if _is_loopback_host(host) or token:
        return
    from office_agent.auth import API_TOKEN_ENV

    print(
        f"refuse to start: binding to non-loopback address {host!r} without "
        f"{API_TOKEN_ENV} would expose the API (workspace write / script "
        f"execution) to the network. Set {API_TOKEN_ENV} or bind to 127.0.0.1.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Packaged sidecar: ToolExecutor invokes
    #   office-agent-runtime.exe --run-script path.py [args...]
    # because sys.executable is the sidecar itself, not CPython.
    if argv and argv[0] == "--run-script":
        from office_agent.script_jail_main import main as jail_main

        jail_main(argv[1:])
        return

    parser = argparse.ArgumentParser(description="Office Agent Runtime (local FastAPI)")
    parser.add_argument(
        "--host",
        default=os.environ.get("OFFICE_AGENT_HOST", DEFAULT_HOST),
        help=f"bind address (default {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("OFFICE_AGENT_PORT", str(DEFAULT_PORT))),
        help=f"listen port (default {DEFAULT_PORT})",
    )
    args = parser.parse_args(argv)

    # M11：非回环绑定必须已配置 API token，否则拒绝启动。
    from office_agent.auth import configured_api_token

    assert_bind_safety(args.host, configured_api_token())

    # Import after argparse so ``--help`` works without pulling the full stack.
    import uvicorn

    from office_agent.app import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main(sys.argv[1:])
