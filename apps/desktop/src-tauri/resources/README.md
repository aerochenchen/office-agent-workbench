# Tauri resources (staged at build time)

This folder is filled at build time by:

- **Windows:** [`scripts/build-windows.ps1`](../../../../scripts/build-windows.ps1)
- **macOS:** [`scripts/build-macos.sh`](../../../../scripts/build-macos.sh) — internal-test DMG only; **not notarized**

Staged contents:

- `runtime/` — PyInstaller onedir sidecar (`office-agent-runtime` + `_internal/`)
- `bundled/` — copy of repo `bundled/` (light skills + shared scripts)

Do not commit built binaries. Run the platform build script before `tauri build`.

Placeholder files below keep the directory layout in git so Tauri resource globs resolve during incomplete local builds.
