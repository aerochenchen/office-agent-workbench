#!/usr/bin/env bash
# Copy repo-root NOTICE into Tauri resources so tauri.conf.json bundle path resolves.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/NOTICE"
DEST="${ROOT}/apps/desktop/src-tauri/resources/NOTICE"

if [[ ! -f "${SRC}" ]]; then
  echo "error: ${SRC} missing — run scripts/generate_notice.sh first" >&2
  exit 1
fi

cp -f "${SRC}" "${DEST}"
echo "Staged NOTICE → ${DEST}"
