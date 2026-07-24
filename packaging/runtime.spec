# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec for the Office Agent Runtime sidecar.

Build (from repo root, after activating a packaging venv)::

    pyinstaller packaging/runtime.spec --noconfirm --clean

Output: packaging/dist/office-agent-runtime/
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

SPECDIR = Path(SPECPATH).resolve()
ROOT = SPECDIR.parent
RUNTIME_SRC = ROOT / "runtime" / "src"
ENTRY = SPECDIR / "run_runtime.py"

sys.path.insert(0, str(RUNTIME_SRC))

datas: list = []
binaries: list = []
hiddenimports: list = list(
    collect_submodules("office_agent")
    + [
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "email.mime.text",
        "docx",
        "pptx",
    ]
)

for pkg in (
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
    "pydantic_settings",
    "openai",
    "httpx",
    "anyio",
    "sniffio",
    "yaml",
    "multipart",
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # noqa: BLE001 — best-effort collect
        print(f"[runtime.spec] skip collect_all({pkg}): {exc}", file=sys.stderr)

a = Analysis(
    [str(ENTRY)],
    pathex=[str(RUNTIME_SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "transformers", "sentence_transformers", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="office-agent-runtime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="office-agent-runtime",
)
