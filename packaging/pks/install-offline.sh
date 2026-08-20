#!/usr/bin/env bash
# Offline installer for 文书通 PKS bundle on 银河麒麟 V10 (aarch64).
# Run from the extracted wenshutong-pks-*-aarch64 directory. NO NETWORK.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEPS_DIR="${ROOT}/deps"
cd "${ROOT}"

if [[ "$(uname -m)" != "aarch64" && "$(uname -m)" != "arm64" ]]; then
  echo "ERROR: expected aarch64 host, got $(uname -m)" >&2
  exit 1
fi

# Install a dep when missing, or when bundled version is newer than installed.
# Never downgrade (avoids overwriting Kylin patches with older Ubuntu debs).
should_install_deb() {
  local deb="$1" pkg ver status installed
  pkg="$(dpkg-deb -f "${deb}" Package)"
  ver="$(dpkg-deb -f "${deb}" Version)"
  status="$(dpkg-query -W -f='${Status}' "${pkg}" 2>/dev/null || true)"
  if [[ "${status}" != *"install ok installed"* ]]; then
    echo "install"
    return 0
  fi
  installed="$(dpkg-query -W -f='${Version}' "${pkg}" 2>/dev/null || true)"
  if dpkg --compare-versions "${ver}" gt "${installed}"; then
    echo "upgrade ${installed} -> ${ver}"
    return 0
  fi
  echo "skip ${pkg} (${installed})"
  return 1
}

install_deps() {
  local deb action
  local -a todo=()
  for deb in "$@"; do
    action="$(should_install_deb "${deb}" || true)"
    case "${action}" in
      install|upgrade*)
        echo "    ${action}: $(basename "${deb}")"
        todo+=("${deb}")
        ;;
      skip*)
        echo "    ${action}"
        ;;
    esac
  done
  if ((${#todo[@]} > 0)); then
    echo "==> Installing/upgrading deps (${#todo[@]} packages)"
    sudo dpkg -i "${todo[@]}" || sudo dpkg --configure -a
  else
    echo "==> Offline deps: nothing to install"
  fi
}

shopt -s nullglob
deps=( "${DEPS_DIR}"/*.deb )
if ((${#deps[@]} > 0)); then
  echo "==> Checking offline deps (${#deps[@]} packages in deps/)"
  install_deps "${deps[@]}"
fi

mains=( "${ROOT}"/文书通_*.deb "${ROOT}"/wenshutong_*.deb )
main=""
for c in "${mains[@]}"; do
  [[ -f "${c}" ]] || continue
  main="${c}"
  break
done
if [[ -z "${main}" ]]; then
  echo "ERROR: no wenshutong_*.deb or 文书通_*.deb in ${ROOT}" >&2
  exit 1
fi

echo "==> Installing ${main}"
if ! sudo dpkg -i "${main}"; then
  echo "==> dpkg -i failed; retry after dpkg --configure -a" >&2
  sudo dpkg --configure -a || true
  sudo dpkg -i "${main}"
fi

echo "==> Done. Start 文书通 from the application menu, then configure intranet model."
echo "    If no window appears, try: GDK_BACKEND=x11 WEBKIT_DISABLE_COMPOSITING_MODE=1 wenshutong"
