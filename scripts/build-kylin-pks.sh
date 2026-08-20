#!/usr/bin/env bash
# Build PKS (Kylin aarch64) offline bundle via Docker linux/arm64.
# Usage (repo root, networked Mac with Docker):
#   ./scripts/build-kylin-pks.sh
#   ./scripts/build-kylin-pks.sh --clean
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKS="${ROOT}/packaging/pks"
DIST_PKS="${ROOT}/packaging/dist/pks"
OUT_RAW="${DIST_PKS}/out"
IMAGE="wenshutong-pks-builder:ubuntu20-arm64"
CLEAN=0
SKIP_IMAGE=0
REBUILD_IMAGE=0
for arg in "$@"; do
  case "${arg}" in
    --clean) CLEAN=1 ;;
    --skip-image-build) SKIP_IMAGE=1 ;;
    --rebuild-image) REBUILD_IMAGE=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
  esac
done

command -v docker >/dev/null || { echo "docker required" >&2; exit 1; }

VERSION="$(python3 -c "import json;print(json.load(open('${ROOT}/apps/desktop/src-tauri/tauri.conf.json'))['version'])")"
BUNDLE_DIR="${DIST_PKS}/wenshutong-pks-${VERSION}-aarch64"

if [[ "${CLEAN}" -eq 1 ]]; then
  rm -rf "${DIST_PKS}" "${ROOT}/packaging/.venv-pks"
fi
mkdir -p "${OUT_RAW}"

echo "==> docker build image (${IMAGE})"
# Bypass local HTTP proxy (Clash 198.18.x) which breaks Ubuntu Ports fetches.
BUILD_PROXY=(--build-arg HTTP_PROXY= --build-arg HTTPS_PROXY= --build-arg http_proxy= --build-arg https_proxy= --build-arg NO_PROXY='*' --build-arg no_proxy='*')
if [[ "${REBUILD_IMAGE}" -eq 1 ]]; then
  docker build --platform=linux/arm64 "${BUILD_PROXY[@]}" -t "${IMAGE}" -f "${PKS}/Dockerfile" "${PKS}"
elif [[ "${SKIP_IMAGE}" -eq 1 ]]; then
  echo "    (skipped: --skip-image-build)"
elif docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "    (skipped: image already exists; pass --rebuild-image to force)"
else
  docker build --platform=linux/arm64 "${BUILD_PROXY[@]}" -t "${IMAGE}" -f "${PKS}/Dockerfile" "${PKS}"
fi

# Optional: refresh offline WebKit 4.0 deps for the USB bundle
if [[ -x "${PKS}/fetch-kylin-deps.sh" ]]; then
  if ! compgen -G "${PKS}/deps/*.deb" > /dev/null; then
    echo "==> fetching Kylin offline deps (WebKit 4.0)"
    bash "${PKS}/fetch-kylin-deps.sh" || echo "WARN: deps fetch failed; bundle may rely on target-system WebKit" >&2
  fi
fi

echo "==> docker run build-inside"
docker run --rm --platform=linux/arm64 \
  -v "${ROOT}:/src" \
  -v "${OUT_RAW}:/src/packaging/dist/pks/out" \
  "${IMAGE}" bash /src/packaging/pks/build-inside.sh

echo "==> assemble USB bundle ${BUNDLE_DIR}"
rm -rf "${BUNDLE_DIR}"
mkdir -p "${BUNDLE_DIR}/deps"
cp -f "${OUT_RAW}"/*.deb "${BUNDLE_DIR}/"
cp -f "${PKS}/install-offline.sh" "${BUNDLE_DIR}/"
cp -f "${PKS}/deps.manifest" "${BUNDLE_DIR}/"
# copy any pre-downloaded debs if present
if compgen -G "${PKS}/deps/*.deb" > /dev/null; then
  cp -f "${PKS}/deps/"*.deb "${BUNDLE_DIR}/deps/"
fi
# copy acceptance fixtures if present
if [[ -d "${PKS}/fixtures" ]]; then
  rm -rf "${BUNDLE_DIR}/fixtures"
  cp -R "${PKS}/fixtures" "${BUNDLE_DIR}/fixtures"
fi
cp -f "${ROOT}/packaging/文书通-银河麒麟安装说明.md" "${BUNDLE_DIR}/银河麒麟安装说明.md"
cp -f "${ROOT}/packaging/验收清单-PKS-给非开发人员.md" "${BUNDLE_DIR}/验收清单.md"
cat > "${BUNDLE_DIR}/README-安装说明.txt" <<EOF
文书通 PKS 离线包 (${VERSION}, aarch64)
=====================================
快速步骤：
  1. 将整个文件夹拷到 U 盘
  2. 在银河麒麟 V10 SP1 (aarch64) 上复制到本机
  3. 断网后在该目录执行: bash install-offline.sh
  4. 从开始菜单启动「文书通」，配置内网模型

详细说明请阅读: 银河麒麟安装说明.md
验收勾选表: 验收清单.md
EOF
chmod +x "${BUNDLE_DIR}/install-offline.sh"

ARCHIVE="${DIST_PKS}/wenshutong-pks-${VERSION}-aarch64.tar.gz"
tar -czf "${ARCHIVE}" -C "${DIST_PKS}" "wenshutong-pks-${VERSION}-aarch64"

echo "USB bundle ready: ${BUNDLE_DIR}"
echo "Archive ready: ${ARCHIVE}"
ls -la "${BUNDLE_DIR}"
ls -lh "${ARCHIVE}"
