#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-/src}"
PACKAGING="${ROOT}/packaging"
# python-build-standalone expects prefix /install
if [[ -d /opt/python && ! -e /install ]]; then
  ln -sfn /opt/python /install
fi
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
rm -rf "${VENV}"
if ! "${PYTHON}" -m venv "${VENV}" 2>/dev/null; then
  "${PYTHON}" -m venv "${VENV}" --without-pip
  # shellcheck disable=SC1091
  source "${VENV}/bin/activate"
  curl -fsSL https://bootstrap.pypa.io/get-pip.py | python
else
  # shellcheck disable=SC1091
  source "${VENV}/bin/activate"
fi
if ! command -v pip >/dev/null 2>&1; then
  curl -fsSL https://bootstrap.pypa.io/get-pip.py | python
fi
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

echo "==> npm + tauri deb (WebKitGTK 4.0 / glibc 2.31 baseline)"
cd "${DESKTOP}"
npm ci
npm run build

# Inject crates.io patches for WebKit 4.0 (PKS-only; removed on EXIT).
CARGO_TOML="${SRC_TAURI}/Cargo.toml"
PATCH_FILE="${PACKAGING}/pks/Cargo.webkit40.patch.toml"
MARKER_BEGIN='# PKS-WEBKIT40-PATCH-BEGIN'
MARKER_END='# PKS-WEBKIT40-PATCH-END'
python3 - "${CARGO_TOML}" "${PATCH_FILE}" "${MARKER_BEGIN}" "${MARKER_END}" <<'PY'
from pathlib import Path
import sys
cargo = Path(sys.argv[1])
patch = Path(sys.argv[2])
begin, end = sys.argv[3], sys.argv[4]
text = cargo.read_text(encoding="utf-8")
if begin in text:
    start = text.index(begin)
    stop = text.index(end, start) + len(end) if end in text[start:] else len(text)
    text = (text[:start] + text[stop:]).rstrip() + "\n"
block = f"\n{begin}\n{patch.read_text(encoding='utf-8').rstrip()}\n{end}\n"
cargo.write_text(text.rstrip() + block, encoding="utf-8")
PY
cleanup_pks_patch() {
  python3 - "${CARGO_TOML}" "${MARKER_BEGIN}" "${MARKER_END}" <<'PY'
from pathlib import Path
import sys
cargo, begin, end = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
text = cargo.read_text(encoding="utf-8")
if begin not in text:
    raise SystemExit(0)
start = text.index(begin)
stop = text.index(end, start) + len(end) if end in text[start:] else len(text)
cargo.write_text((text[:start] + text[stop:]).rstrip() + "\n", encoding="utf-8")
PY
}
trap cleanup_pks_patch EXIT

echo "==> cargo lock (keep existing lock if already patched)"
(
  cd "${SRC_TAURI}"
  if ! grep -q 'webkit40-vendor/soup2-sys' Cargo.lock 2>/dev/null; then
    rm -f Cargo.lock
    cargo generate-lockfile
  fi
)

npx tauri build --bundles deb --config src-tauri/tauri.release.conf.json --config src-tauri/tauri.kylin.conf.json

# Fresh out dir so leftover debs cannot confuse find/mv.
rm -f "${OUT}"/*.deb
DEB="$(find "${SRC_TAURI}/target/release/bundle/deb" -name '*.deb' -print | head -n1)"
test -n "${DEB}"
STAGED_DEB="${OUT}/tauri-built.deb"
cp -f "${DEB}" "${STAGED_DEB}"
# Tauri names the Package field after productName (文书通); dpkg rejects it.
# rewrite-deb-package-name.sh rewrites in place when out path omitted / same as in.
bash "${PACKAGING}/pks/rewrite-deb-package-name.sh" "${STAGED_DEB}"
VERSION="$(dpkg-deb -f "${STAGED_DEB}" Version)"
DEST="${OUT}/wenshutong_${VERSION}_arm64.deb"
mv -f "${STAGED_DEB}" "${DEST}"
# smoke: binary exists inside package listing
dpkg-deb -c "${DEST}" | grep -E 'office-agent-runtime|文书通|wenshutong' | head
dpkg-deb -I "${DEST}" | grep -E '^ Package: wenshutong$'
# Prefer WebKit 4.0 in Depends metadata (belt-and-suspenders).
dpkg-deb -I "${DEST}" | grep -i webkit || true

echo "==> build-inside done: ${OUT}"
