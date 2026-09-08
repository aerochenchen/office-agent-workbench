"""Child-process entry: install the filesystem jail then run a .py script."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

from office_agent.script_jail import install_fs_jail


def main(argv: list[str] | None = None) -> None:
    raw = list(sys.argv[1:] if argv is None else argv)
    roots: list[Path] = []
    while raw:
        if raw[0] == "--jail-root" and len(raw) >= 2:
            roots.append(Path(raw[1]))
            raw = raw[2:]
            continue
        if raw[0] == "--":
            raw = raw[1:]
            break
        break
    if not raw:
        print("usage: python -m office_agent.script_jail_main [--jail-root DIR] ... -- SCRIPT [ARGS...]", file=sys.stderr)
        raise SystemExit(2)
    script = Path(raw[0]).resolve()
    script_args = raw[1:]
    if not script.is_file():
        print(f"script not found: {script}", file=sys.stderr)
        raise SystemExit(2)
    roots.append(script.parent)
    install_fs_jail(roots)
    sys.argv = [str(script), *script_args]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
