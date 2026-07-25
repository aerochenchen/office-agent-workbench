#!/usr/bin/env bash
# Generate repo-root NOTICE from Python (pip-licenses) and npm (license-checker) summaries.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/runtime/.venv"
DESKTOP="${ROOT}/apps/desktop"
NOTICE="${ROOT}/NOTICE"
GENERATED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

if [[ ! -d "${VENV}" ]]; then
  echo "error: ${VENV} not found — create venv and install runtime first" >&2
  exit 1
fi

if [[ ! -f "${DESKTOP}/package.json" ]]; then
  echo "error: ${DESKTOP}/package.json not found" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "${VENV}/bin/activate"

if ! command -v pip-licenses >/dev/null 2>&1; then
  echo "Installing pip-licenses into runtime venv…"
  python -m pip install -q pip-licenses
fi

cd "${DESKTOP}"
if [[ ! -d node_modules ]]; then
  echo "Installing npm dependencies for NOTICE…"
  npm install --no-audit --no-fund
fi
if ! npx --no-install license-checker --version >/dev/null 2>&1; then
  npm install --no-audit --no-fund
fi

tmp_py="$(mktemp)"
tmp_npm="$(mktemp)"
trap 'rm -f "${tmp_py}" "${tmp_npm}"' EXIT

pip-licenses --format=markdown > "${tmp_py}"
npx license-checker --production --csv > "${tmp_npm}"

{
  cat <<EOF
文书通 (Office Agent) — Third-Party Software NOTICE
===================================================

This file lists open-source components shipped with or used to build the
文书通 desktop application and its Python runtime sidecar.

Generated: ${GENERATED_AT}
Regenerate before release: ./scripts/generate_notice.sh

LGPL dependencies are permitted; GPL/AGPL are blocked by ./scripts/check_licenses.sh.

---

## Python runtime dependencies (runtime/.venv)

EOF
  cat "${tmp_py}"
  cat <<EOF

---

## Desktop frontend dependencies (apps/desktop, production)

The table below is CSV from license-checker (module, license, repository).

EOF
  cat "${tmp_npm}"
  cat <<EOF

---

End of NOTICE.
EOF
} > "${NOTICE}"

echo "Wrote ${NOTICE}"
wc -l "${NOTICE}"
