#!/usr/bin/env bash
# Regenerate desktop packaging icons from the locked branding source.
# Source of truth: apps/desktop/branding/app-icon.png
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DESKTOP="${ROOT}/apps/desktop"
SRC="${DESKTOP}/branding/app-icon.png"
OUT="${DESKTOP}/src-tauri/icons"

if [[ ! -f "${SRC}" ]]; then
  echo "Missing icon source: ${SRC}" >&2
  exit 1
fi

cd "${DESKTOP}"
npx tauri icon "${SRC}" -o "${OUT}"
echo "Icons written to ${OUT}"
echo "Rebuild the desktop app (dev or build-windows.ps1) for Dock / EXE / shortcuts to update."
