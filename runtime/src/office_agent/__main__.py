"""CLI entry: ``python -m office_agent`` or the packaged sidecar exe."""

from __future__ import annotations

import argparse
import os
import runpy
import sys


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _run_script(script: str, script_args: list[str]) -> None:
    """Execute a workspace/skill script using the frozen interpreter's stdlib."""
    path = os.path.abspath(script)
    if not os.path.isfile(path):
        print(f"script not found: {script}", file=sys.stderr)
        raise SystemExit(2)
    # Mimic ``python script.py args...`` so scripts see the expected argv.
    sys.argv = [path, *script_args]
    runpy.run_path(path, run_name="__main__")


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Packaged sidecar: ToolExecutor invokes
    #   office-agent-runtime.exe --run-script path.py [args...]
    # because sys.executable is the sidecar itself, not CPython.
    if argv and argv[0] == "--run-script":
        if len(argv) < 2:
            print("usage: --run-script SCRIPT [ARGS...]", file=sys.stderr)
            raise SystemExit(2)
        _run_script(argv[1], argv[2:])
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

    # Import after argparse so ``--help`` works without pulling the full stack.
    import uvicorn

    from office_agent.app import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main(sys.argv[1:])
