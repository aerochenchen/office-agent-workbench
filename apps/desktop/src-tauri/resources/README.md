# Tauri resources (staged at build time)

This folder is filled by [`scripts/build-windows.ps1`](../../../../scripts/build-windows.ps1):

- `runtime/` — PyInstaller onedir sidecar (`office-agent-runtime.exe` + `_internal/`)
- `bundled/` — copy of repo `bundled/` (light skills + shared scripts)

Do not commit built binaries. Run the Windows build script before `tauri build`.

Placeholder files below keep the directory layout in git so Tauri resource globs resolve during incomplete local builds.
