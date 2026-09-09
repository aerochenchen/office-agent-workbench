#!/usr/bin/env bash
# Pack a source snapshot for on-site security review.
# Output (gitignored): packaging/dist/security-review/
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="1.6.0"
STAMP="$(date +%Y%m%d)"
BUNDLE_DIR="文书通-${VERSION}-源代码复测快照"
OUT_ROOT="${ROOT}/packaging/dist/security-review"
STAGE="${OUT_ROOT}/.stage/${BUNDLE_DIR}"
ZIP_PATH="${OUT_ROOT}/${BUNDLE_DIR}.zip"

rm -rf "${OUT_ROOT}/.stage"
mkdir -p "${STAGE}" "${OUT_ROOT}"

copy_tree() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "${dest}")"
  rsync -a \
    --exclude '.DS_Store' \
    --exclude '__pycache__' \
    --exclude '*.py[cod]' \
    --exclude '.venv/' \
    --exclude 'node_modules/' \
    --exclude 'dist/' \
    --exclude 'target/' \
    --exclude 'gen/schemas/' \
    --exclude '.env' \
    --exclude '.env.*' \
    --exclude '*.pfx' \
    --exclude '.git/' \
    --exclude '.vscode/' \
    --exclude '.idea/' \
    --exclude '.cursor/' \
    --exclude 'icons/ios/' \
    --exclude 'icons/android/' \
    --exclude '.pytest_cache/' \
    --exclude 'embed/' \
    --exclude 'resources/runtime/' \
    --exclude 'resources/bundled/' \
    --exclude '*.provisionprofile' \
    --exclude '*.pfx' \
    "${src}" "${dest}"
}

# Runtime application source + lockfiles (not the whole runtime tree / venv)
mkdir -p "${STAGE}/runtime/src"
copy_tree "${ROOT}/runtime/src/office_agent/" "${STAGE}/runtime/src/office_agent/"
cp -f "${ROOT}/runtime/pyproject.toml" "${STAGE}/runtime/pyproject.toml"
cp -f "${ROOT}/runtime/requirements.txt" "${STAGE}/runtime/requirements.txt"

# Desktop app without node_modules / Rust build artifacts
copy_tree "${ROOT}/apps/desktop/" "${STAGE}/apps/desktop/"
rm -rf \
  "${STAGE}/apps/desktop/node_modules" \
  "${STAGE}/apps/desktop/dist" \
  "${STAGE}/apps/desktop/.pytest_cache" \
  "${STAGE}/apps/desktop/src-tauri/target" \
  "${STAGE}/apps/desktop/src-tauri/gen" \
  "${STAGE}/apps/desktop/src-tauri/embed" \
  "${STAGE}/apps/desktop/src-tauri/resources/runtime" \
  "${STAGE}/apps/desktop/src-tauri/resources/bundled"

# Bundled skills shipped with the product
copy_tree "${ROOT}/bundled/skills/" "${STAGE}/bundled/skills/"

# Local-intranet packaging profile (created to close the audit findings)
mkdir -p "${STAGE}/packaging"
copy_tree "${ROOT}/packaging/本地部署版本/" "${STAGE}/packaging/本地部署版本/"
if [[ -f "${ROOT}/packaging/README-standard.md" ]]; then
  cp -f "${ROOT}/packaging/README-standard.md" "${STAGE}/packaging/README-standard.md"
fi

# Tests that lock the three medium findings (no venv / caches)
mkdir -p "${STAGE}/runtime/tests"
copy_tree "${ROOT}/runtime/tests/" "${STAGE}/runtime/tests/"

cp -f "${ROOT}/NOTICE" "${STAGE}/NOTICE"

cat > "${STAGE}/SECURITY_REVIEW_WATERMARK.txt" <<EOF
文书通源代码安全复测快照
========================

产品: 文书通
版本: ${VERSION}
批次: ${STAMP}（对照 2026-09-01 代码审计报告三项中危整改后复测）
生成机脚本: scripts/pack-security-review-snapshot.sh

本副本仅供本单位网络信息安全部门开展本次源代码安全复测使用。
请同时使用同目录《文书通安全改造结果报告.docx》对照原 4.1.1 / 4.1.2 / 4.1.3。
禁止外传、再分发或用于复制产品。检测结束后应销毁本副本。
本文件为批次标识，不改变程序行为。
EOF

# Manifest of staged files (relative paths)
(
  cd "${STAGE}"
  find . -type f | sed 's|^\./||' | LC_ALL=C sort
) > "${STAGE}/MANIFEST.txt"
cp -f "${STAGE}/MANIFEST.txt" "${OUT_ROOT}/MANIFEST.txt"

rm -f "${ZIP_PATH}"
(
  cd "${OUT_ROOT}/.stage"
  zip -r -q "${ZIP_PATH}" "${BUNDLE_DIR}"
)

if command -v shasum >/dev/null 2>&1; then
  HASH="$(shasum -a 256 "${ZIP_PATH}" | awk '{print $1}')"
elif command -v sha256sum >/dev/null 2>&1; then
  HASH="$(sha256sum "${ZIP_PATH}" | awk '{print $1}')"
else
  echo "error: need shasum or sha256sum" >&2
  exit 1
fi
printf '%s\n' "${HASH}" > "${OUT_ROOT}/SHA256.txt"
printf '%s  %s\n' "${HASH}" "${BUNDLE_DIR}.zip" > "${OUT_ROOT}/SHA256.asc"

# Fail closed if excluded trees leaked into the zip
leak_pat='(^|/)(node_modules|\.venv|target|\.git|resources/runtime|embed|\.pytest_cache)/'
if unzip -Z1 "${ZIP_PATH}" | grep -E "${leak_pat}" >/dev/null; then
  echo "error: snapshot contains excluded dependency, build, or credential paths" >&2
  unzip -Z1 "${ZIP_PATH}" | grep -E "${leak_pat}" | head
  exit 1
fi
if unzip -Z1 "${ZIP_PATH}" | grep -E '(^|/)\.env($|\.)|\.provisionprofile$|\.pfx$' >/dev/null; then
  echo "error: snapshot contains secrets or env files" >&2
  exit 1
fi

echo "snapshot: ${ZIP_PATH}"
echo "sha256:   ${HASH}"
echo "manifest: ${OUT_ROOT}/MANIFEST.txt"
echo "files:    $(wc -l < "${OUT_ROOT}/MANIFEST.txt" | tr -d ' ')"
