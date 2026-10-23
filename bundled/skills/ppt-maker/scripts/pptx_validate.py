#!/usr/bin/env python3
"""Validate a semantic deck.json before pptx_create.py.

Usage:
  python pptx_validate.py .office-agent/work/ppt-maker/deck.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from office_agent.script_policy import confine_to_workspace

from pptx_engine import validate_deck


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Validate semantic PPT deck JSON")
    parser.add_argument("spec", help="path to deck.json")
    args = parser.parse_args(argv)
    try:
        spec_path = confine_to_workspace(Path(args.spec), Path.cwd())
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 1
    report = validate_deck(spec)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
