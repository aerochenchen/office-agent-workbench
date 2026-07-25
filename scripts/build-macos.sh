#!/usr/bin/env bash
# Build the macOS internal-test DMG (文书通.app inside a .dmg).
# Icons: apps/desktop/src-tauri/icons (from branding/app-icon.png).
#
# Steps:
#   1. packaging/.venv + PyInstaller onedir -> packaging/dist/office-agent-runtime
#   2. Stage into apps/desktop/src-tauri/resources/{runtime,bundled}
#   3. npm + tauri build --bundles dmg
#
# Usage (repo root):
#   ./scripts/build-macos.sh
#   ./scripts/build-macos.sh --clean
#   ./scripts/build-macos.sh --skip-sidecar
#   ./scripts/build-macos.sh --skip-tauri
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGING="${ROOT}/packaging"
RUNTIME="${ROOT}/runtime"
DESKTOP="${ROOT}/apps/desktop"
SRC_TAURI="${DESKTOP}/src-tauri"
RESOURCES="${SRC_TAURI}/resources"
VENV="${PACKAGING}/.venv"
DIST_RUNTIME="${PACKAGING}/dist/office-agent-runtime"
STAGED_RUNTIME="${RESOURCES}/runtime"
STAGED_BUNDLED="${RESOURCES}/bundled"
BUNDLED_SRC="${ROOT}/bundled"
SIDECAR_NAME="office-agent-runtime"

SKIP_SIDECAR=0
SKIP_TAURI=0
CLEAN=0

for arg in "$@"; do
  case "${arg}" in
    --skip-sidecar) SKIP_SIDECAR=1 ;;
    --skip-tauri) SKIP_TAURI=1 ;;
    --clean) CLEAN=1 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: ${arg}" >&2
      exit 1
      ;;
  esac
done

step() { printf '\n==> %s\n' "$*"; }

pick_python() {
  local candidates=(
    "${PYTHON:-}"
    python3.12
    python3.11
    python3
  )
  local c
  for c in "${candidates[@]}"; do
    [[ -z "${c}" ]] && continue
    if command -v "${c}" >/dev/null 2>&1; then
      if "${c}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
        echo "${c}"
        return 0
      fi
    fi
  done
  echo "Python 3.11+ required (set PYTHON=... if needed)." >&2
  exit 1
}

ensure_venv() {
  local py
  py="$(pick_python)"
  if [[ "${CLEAN}" -eq 1 && -d "${VENV}" ]]; then
    step "Removing packaging/.venv"
    rm -rf "${VENV}"
  fi
  if [[ ! -x "${VENV}/bin/python" ]]; then
    step "Creating packaging/.venv with ${py}"
    "${py}" -m venv "${VENV}"
  fi
  # shellcheck disable=SC1091
  source "${VENV}/bin/activate"
  python -m pip install --upgrade pip
  python -m pip install -e "${RUNTIME}[packaging]"
  if [[ -f "${RUNTIME}/requirements.txt" ]]; then
    python -m pip install -r "${RUNTIME}/requirements.txt"
  fi
}

build_sidecar() {
  step "PyInstaller onedir (${SIDECAR_NAME})"
  if [[ "${CLEAN}" -eq 1 ]]; then
    rm -rf "${PACKAGING}/build" "${PACKAGING}/dist"
  fi
  (
    cd "${PACKAGING}"
    python -m PyInstaller "${PACKAGING}/runtime.spec" --noconfirm --clean
  )
  if [[ ! -x "${DIST_RUNTIME}/${SIDECAR_NAME}" ]]; then
    echo "Sidecar missing: ${DIST_RUNTIME}/${SIDECAR_NAME}" >&2
    exit 1
  fi
  chmod +x "${DIST_RUNTIME}/${SIDECAR_NAME}"
}

stage_resources() {
  step "Staging Tauri resources"
  rm -rf "${STAGED_RUNTIME}" "${STAGED_BUNDLED}"
  mkdir -p "${STAGED_RUNTIME}" "${STAGED_BUNDLED}"
  cp -R "${DIST_RUNTIME}/." "${STAGED_RUNTIME}/"
  if [[ ! -d "${BUNDLED_SRC}" ]]; then
    echo "bundled/ missing at ${BUNDLED_SRC}" >&2
    exit 1
  fi
  cp -R "${BUNDLED_SRC}/." "${STAGED_BUNDLED}/"
  if [[ ! -x "${STAGED_RUNTIME}/${SIDECAR_NAME}" ]]; then
    echo "Staged sidecar missing: ${STAGED_RUNTIME}/${SIDECAR_NAME}" >&2
    exit 1
  fi
  chmod +x "${STAGED_RUNTIME}/${SIDECAR_NAME}"
  echo "Staged runtime -> ${STAGED_RUNTIME}"
  echo "Staged bundled -> ${STAGED_BUNDLED}"
}

build_tauri() {
  step "npm install + tauri build (dmg)"
  # Keep artifacts under the repo (ignore inherited CI/sandbox CARGO_TARGET_DIR).
  export CARGO_TARGET_DIR="${SRC_TAURI}/target"
  (
    cd "${DESKTOP}"
    if [[ ! -d node_modules/@tauri-apps/cli ]]; then
      npm install
    fi
    # Override conf targets (nsis) so Mac builds only produce DMG.
    npx --yes tauri build --bundles dmg
  )

  local dmg_dir="${CARGO_TARGET_DIR}/release/bundle/dmg"
  local dist_dir="${PACKAGING}/dist/mac"
  mkdir -p "${dist_dir}"

  step "Done"
  local found=0
  local f
  if [[ -d "${dmg_dir}" ]]; then
    while IFS= read -r f; do
      found=1
      cp -f "${f}" "${dist_dir}/"
      echo "Installer: ${f}"
      echo "Copy:      ${dist_dir}/$(basename "${f}")"
    done < <(find "${dmg_dir}" -maxdepth 1 -name '*.dmg' -print)
  fi
  if [[ "${found}" -eq 0 ]]; then
    echo "DMG not found under ${dmg_dir}" >&2
    exit 1
  fi
  cat <<'EOF'

内测说明：
  - 未做 Apple 公证；首次打开可在 Finder 中右键「打开」，或在「系统设置 → 隐私与安全性」允许。
  - 将「文书通.app」拖到「应用程序」即可使用。
  - 便捷副本也在 packaging/dist/mac/
EOF
}

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "build-macos.sh must run on macOS." >&2
  exit 1
fi

if [[ "${SKIP_SIDECAR}" -eq 0 ]]; then
  ensure_venv
  build_sidecar
  stage_resources
else
  if [[ ! -x "${STAGED_RUNTIME}/${SIDECAR_NAME}" ]]; then
    echo "--skip-sidecar set but staged runtime missing. Run without it first." >&2
    exit 1
  fi
fi

if [[ "${SKIP_TAURI}" -eq 0 ]]; then
  build_tauri
else
  step "Skip tauri: resources staged only"
  echo "Staged at ${RESOURCES}"
fi
