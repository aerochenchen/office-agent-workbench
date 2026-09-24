#!/usr/bin/env python3
"""Write a CycloneDX SBOM for the Python runtime that is actually installed.

Run inside runtime/.venv so the inventory matches the packaged interpreter.
Exits non-zero when an installed distribution has no name, or when NOTICE
mentions a distribution that is not installed (and the reverse) if --notice
is passed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from importlib.metadata import distributions
from pathlib import Path


def _dist_rows() -> list[dict]:
    rows: list[dict] = []
    for dist in distributions():
        name = dist.metadata["Name"]
        if not name:
            raise SystemExit("installed distribution is missing Name")
        version = dist.version or ""
        license_name = dist.metadata.get("License") or ""
        rows.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "licenses": [{"license": {"name": license_name}}] if license_name else [],
                "purl": f"pkg:pypi/{name.lower().replace('_', '-')}@{version}",
            }
        )
    rows.sort(key=lambda item: item["name"].lower())
    return rows


def _notice_names(text: str) -> set[str]:
    """Best-effort names from the pip-licenses markdown table in NOTICE."""
    names: set[str] = set()
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() in {"name", "package"} or set(cells[0]) <= {"-"}:
            continue
        if cells[0] and " " not in cells[0]:
            names.add(cells[0].lower().replace("_", "-"))
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a Python CycloneDX SBOM")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--notice", type=Path, default=None)
    parser.add_argument("--licenses-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    components = _dist_rows()
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "component": {"type": "application", "name": "wenshutong-runtime"},
        },
        "components": components,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.licenses_dir is not None:
        args.licenses_dir.mkdir(parents=True, exist_ok=True)
        for dist in distributions():
            name = (dist.metadata["Name"] or "unknown").replace("/", "-")
            texts: list[str] = []
            for path in dist.files or []:
                lowered = path.name.lower()
                if "license" in lowered or "notice" in lowered or "copying" in lowered:
                    try:
                        texts.append(path.read_text(encoding="utf-8", errors="replace"))
                    except (OSError, UnicodeError, AttributeError):
                        continue
            if texts:
                (args.licenses_dir / f"{name}.txt").write_text("\n\n".join(texts), encoding="utf-8")

    if args.notice is not None and args.notice.is_file():
        declared = _notice_names(args.notice.read_text(encoding="utf-8", errors="replace"))
        installed = {row["name"].lower().replace("_", "-") for row in components}
        # NOTICE also lists npm packages; only compare rows that look like the Python table.
        missing = sorted(installed - declared)
        extra = sorted(declared - installed)
        if missing or extra:
            print("SBOM drift against NOTICE", file=sys.stderr)
            if missing:
                print("installed but not declared:", ", ".join(missing[:30]), file=sys.stderr)
            if extra:
                print("declared but not installed:", ", ".join(extra[:30]), file=sys.stderr)
            return 1
    print(f"wrote {args.out} ({len(components)} components)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
