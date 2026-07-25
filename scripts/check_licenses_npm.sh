#!/usr/bin/env bash
# Scan apps/desktop npm dependency licenses; exit non-zero if GPL/AGPL detected.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP="${ROOT}/apps/desktop"

if [[ ! -f "${DESKTOP}/package.json" ]]; then
  echo "error: ${DESKTOP}/package.json not found" >&2
  exit 1
fi

cd "${DESKTOP}"

if [[ ! -d node_modules ]]; then
  echo "Installing npm dependencies for license scan…"
  npm install --no-audit --no-fund
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "error: npx not found — install Node.js/npm" >&2
  exit 1
fi

# Ensure license-checker is available (devDependency in package.json).
if ! npx --no-install license-checker --version >/dev/null 2>&1; then
  echo "Installing license-checker…"
  npm install --no-audit --no-fund
fi

echo "License scan: ${DESKTOP} (npm, production)"
echo "---"

# failOn matches license strings; LGPL is not listed so it passes.
npx license-checker --production --summary \
  --failOn "GPL;AGPL;GNU General Public License;GNU Affero General Public License;GNU General Public License v2;GNU General Public License v3;GNU Affero General Public License v3"

echo "OK: no GPL/AGPL (license-checker --failOn)."
exit 0
