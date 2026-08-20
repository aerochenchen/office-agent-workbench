#!/usr/bin/env bash
# Download Ubuntu 20.04 (focal) arm64 runtime debs for Kylin V10 SP1 offline deps/.
# Run on a networked Mac/Linux host (not on the airgapped Kylin machine).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEPS="${ROOT}/deps"
MIRROR="${PKS_DEB_MIRROR:-http://ports.ubuntu.com/ubuntu-ports}"
SUITE="${PKS_DEB_SUITE:-focal-updates}"
ARCH=arm64

mkdir -p "${DEPS}"
cd "${DEPS}"

PACKAGES=(
  libwebkit2gtk-4.0-37
  libjavascriptcoregtk-4.0-18
  libsoup2.4-1
)

TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT

echo "==> Fetching package index ${SUITE}/${ARCH}"
curl -fsSL "${MIRROR}/dists/${SUITE}/main/binary-${ARCH}/Packages.gz" | gzip -dc > "${TMP}"

echo "==> Fetching ${#PACKAGES[@]} packages from ${MIRROR}"
for pkg in "${PACKAGES[@]}"; do
  echo "--> ${pkg}"
  file="$(awk -v p="${pkg}" '
    $1=="Package:" && $2==p {inpkg=1}
    inpkg && $1=="Filename:" {print $2; exit}
    inpkg && $1=="Package:" && $2!=p {inpkg=0}
  ' "${TMP}")"
  if [[ -z "${file}" ]]; then
    echo "WARN: could not resolve ${pkg} in ${SUITE}; skip" >&2
    continue
  fi
  base="$(basename "${file}")"
  curl -fL --retry 3 -o "${base}.partial" "${MIRROR}/${file}"
  mv -f "${base}.partial" "${base}"
done

cat > "${ROOT}/deps.manifest" <<EOF
# Offline system .deb packages for 银河麒麟 V10 SP1 aarch64
# Source: Ubuntu ${SUITE} ${ARCH} (${MIRROR})
# Fetched by packaging/pks/fetch-kylin-deps.sh
#
# Runtime target: WebKitGTK 4.0 >= 2.36 (matches Ubuntu 20.04 builder 2.38.x).
# Do NOT ship 2.28 — the binary needs webkit_uri_scheme_response_set_http_headers.
libwebkit2gtk-4.0-37
libjavascriptcoregtk-4.0-18
libsoup2.4-1
EOF

echo "==> deps ready:"
ls -lh "${DEPS}"/*.deb 2>/dev/null || echo "(no debs downloaded)"
