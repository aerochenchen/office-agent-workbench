#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/src}"
PACKAGING="${ROOT}/packaging"
DESKTOP="${ROOT}/apps/desktop"
SRC_TAURI="${DESKTOP}/src-tauri"
RESOURCES="${SRC_TAURI}/resources"
VENV="${PACKAGING}/.venv-pks"
DIST_RUNTIME="${PACKAGING}/dist/office-agent-runtime"
STAGED_RUNTIME="${RESOURCES}/runtime"
STAGED_BUNDLED="${RESOURCES}/bundled"
OUT="${PACKAGING}/dist/pks/out"
mkdir -p "${OUT}" "${PACKAGING}/dist"

echo "==> Python venv + runtime deps"
PYTHON="${PYTHON:-python3.11}"
"${PYTHON}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "Python 3.11+ required (set PYTHON=... if needed)." >&2; exit 1; }
"${PYTHON}" -m venv "${VENV}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
pip install -U pip wheel
pip install -e "${ROOT}/runtime[packaging]"

echo "==> PyInstaller onedir"
rm -rf "${DIST_RUNTIME}"
(
  cd "${PACKAGING}"
  python -m PyInstaller "${PACKAGING}/runtime.spec" --noconfirm --clean
)
test -x "${DIST_RUNTIME}/office-agent-runtime"

echo "==> Stage resources"
rm -rf "${STAGED_RUNTIME}" "${STAGED_BUNDLED}"
mkdir -p "${RESOURCES}"
cp -a "${DIST_RUNTIME}" "${STAGED_RUNTIME}"
cp -a "${ROOT}/bundled/." "${STAGED_BUNDLED}/"
bash "${ROOT}/scripts/stage_notice.sh"

echo "==> npm + tauri deb"
cd "${DESKTOP}"
npm ci
npm run build
npx tauri build --bundles deb --config src-tauri/tauri.kylin.conf.json

DEB="$(find "${SRC_TAURI}/target/release/bundle/deb" -name '*.deb' | head -n1)"
test -n "${DEB}"
cp -f "${DEB}" "${OUT}/"
# smoke: binary exists inside package listing
dpkg-deb -c "${OUT}/"*.deb | grep -E 'office-agent-runtime|文书通' | head

echo "==> build-inside done: ${OUT}"
