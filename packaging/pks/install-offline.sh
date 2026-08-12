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

shopt -s nullglob
deps=( "${DEPS_DIR}"/*.deb )
if ((${#deps[@]} > 0)); then
  echo "==> Installing offline deps (${#deps[@]} packages)"
  sudo dpkg -i "${deps[@]}" || sudo dpkg --configure -a
fi

mains=( "${ROOT}"/文书通_*.deb "${ROOT}"/wenshutong_*.deb )
main=""
for c in "${mains[@]}"; do
  [[ -f "${c}" ]] || continue
  main="${c}"
  break
done
if [[ -z "${main}" ]]; then
  echo "ERROR: no 文书通_*.deb in ${ROOT}" >&2
  exit 1
fi

echo "==> Installing ${main}"
sudo dpkg -i "${main}" || sudo dpkg --configure -a

echo "==> Done. Start 文书通 from the application menu, then configure intranet model."
