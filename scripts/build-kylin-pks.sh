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
IMAGE="wenshutong-pks-builder:ubuntu22-arm64"
CLEAN=0
for arg in "$@"; do
  case "${arg}" in
    --clean) CLEAN=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
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
docker build --platform=linux/arm64 -t "${IMAGE}" -f "${PKS}/Dockerfile" "${PKS}"

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
cat > "${BUNDLE_DIR}/README-安装说明.txt" <<EOF
文书通 PKS 离线安装（银河麒麟 V10 SP1 aarch64）

1. 将本目录完整拷贝到目标机（U 盘）
2. 在目录内执行: bash install-offline.sh
3. 从应用菜单启动「文书通」
4. 设置中配置单位内网模型地址
5. 按 packaging/VERIFY-kylin-pks.md 做 B 档验收
EOF
chmod +x "${BUNDLE_DIR}/install-offline.sh"

echo "USB bundle ready: ${BUNDLE_DIR}"
ls -la "${BUNDLE_DIR}"
