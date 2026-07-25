#!/usr/bin/env bash
# Scan runtime/.venv dependency licenses; exit non-zero if GPL/AGPL detected.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/runtime/.venv"

if [[ ! -d "${VENV}" ]]; then
  echo "error: ${VENV} not found — create venv and install runtime first" >&2
  exit 1
fi

# shellcheck source=/dev/null
source "${VENV}/bin/activate"

if ! command -v pip-licenses >/dev/null 2>&1; then
  echo "Installing pip-licenses into runtime venv…"
  python -m pip install -q pip-licenses
fi

echo "License scan: ${VENV}"
echo "---"

if pip-licenses --help 2>&1 | grep -q -- '--fail-on'; then
  pip-licenses --fail-on "GNU General Public License;GNU General Public License v2 (GPLv2);GNU General Public License v3 (GPLv3);GNU Affero General Public License;GNU Affero General Public License v3"
  echo "OK: no GPL/AGPL (pip-licenses --fail-on)."
  echo ""
  "${ROOT}/scripts/check_licenses_npm.sh"
  exit 0
fi

bad=""
while IFS= read -r line; do
  lic="${line#*|}"
  name_ver="${line%|*}"
  if echo "${lic}" | grep -qiE 'Affero General Public|\bAGPL\b|General Public License'; then
    if ! echo "${lic}" | grep -qi 'Lesser General Public'; then
      bad+="${name_ver}: ${lic}"$'\n'
    fi
  fi
done < <(pip-licenses --format=json 2>/dev/null | python -c "
import json, sys
for p in json.load(sys.stdin):
    print(f\"{p.get('Name','?')} {p.get('Version','?')}|{p.get('License','')}\")
")

if [[ -n "${bad}" ]]; then
  echo "FAIL: GPL/AGPL dependencies:" >&2
  printf '%s' "${bad}" >&2
  exit 1
fi

echo "OK: no GPL/AGPL packages reported."

echo ""
"${ROOT}/scripts/check_licenses_npm.sh"
exit 0
