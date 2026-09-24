#!/usr/bin/env python3
"""Fail if a release artifact still contains the NSIS template token."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOKEN = "{{product_name}}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reject leftover installer placeholders")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    bad: list[Path] = []
    for path in args.paths:
        if not path.is_file():
            continue
        data = path.read_bytes()
        if TOKEN.encode("utf-8") in data or TOKEN.encode("utf-16le") in data:
            bad.append(path)
    if bad:
        print("installer placeholder still present:", file=sys.stderr)
        for path in bad:
            print(f"  {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
