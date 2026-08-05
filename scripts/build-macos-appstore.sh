#!/usr/bin/env bash
# Build a Mac App Store .app (+ optional .pkg) for 文书通.
# Prerequisites: see docs/文书通-Mac-App-Store构建.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DESKTOP="${ROOT}/apps/desktop"
SRC_TAURI="${DESKTOP}/src-tauri"
ENTITLEMENTS="${SRC_TAURI}/Entitlements.appstore.plist"
SIDECAR_ENTITLEMENTS="${SRC_TAURI}/Entitlements.sidecar.plist"
PROFILE="${SRC_TAURI}/embed/MacAppStore.provisionprofile"
OUT_DIR="${ROOT}/packaging/dist/mac-appstore"

step() { printf '\n==> %s\n' "$*"; }

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Must run on macOS." >&2
  exit 1
fi

step "Check code signing identities"
IDENTITIES="$(security find-identity -v -p codesigning | grep -E 'Apple Distribution|3rd Party Mac Developer Distribution' || true)"
if [[ -z "${IDENTITIES}" ]]; then
  cat <<'EOF' >&2
未找到 Apple Distribution 签名证书。

请先：
  1. 用 packaging/apple/CertificateSigningRequest.certSigningRequest 在
     https://developer.apple.com/account/resources/certificates/add
     创建「Apple Distribution」证书并下载安装；
  2. 运行: security find-identity -v -p codesigning
     应能看到 Apple Distribution: …

说明见 docs/文书通-Mac-App-Store构建.md
EOF
  exit 1
fi
echo "${IDENTITIES}"

SIGN_IDENTITY="$(echo "${IDENTITIES}" | head -1 | sed -E 's/.*"(.+)".*/\1/')"
echo "Using identity: ${SIGN_IDENTITY}"

if grep -q 'TEAM_ID' "${ENTITLEMENTS}"; then
  echo "Entitlements still contain TEAM_ID placeholder: ${ENTITLEMENTS}" >&2
  echo "Set your Team ID (Membership page) and replace TEAM_ID in that file." >&2
  exit 1
fi

if [[ ! -f "${PROFILE}" ]]; then
  echo "Missing provisioning profile: ${PROFILE}" >&2
  echo "Download Mac App Store Connect profile and save it there." >&2
  exit 1
fi

step "verify signing certificate is present in provisioning profile"
PROFILE_TMP="$(mktemp -d)"
trap 'rm -rf "${PROFILE_TMP}"' EXIT
security cms -D -i "${PROFILE}" -o "${PROFILE_TMP}/profile.plist"
SIGN_SHA1="$(security find-certificate -c "${SIGN_IDENTITY}" -Z 2>/dev/null | awk '/SHA-1 hash/ {print $3; exit}')"
PROFILE_SHA1S=""
for i in 0 1 2 3 4; do
  if plutil -extract "DeveloperCertificates.${i}" raw -o - "${PROFILE_TMP}/profile.plist" 2>/dev/null \
      | base64 -d > "${PROFILE_TMP}/cert.der" 2>/dev/null && [[ -s "${PROFILE_TMP}/cert.der" ]]; then
    PROFILE_SHA1S+=" $(openssl x509 -inform DER -in "${PROFILE_TMP}/cert.der" -noout -fingerprint -sha1 \
      | sed -E 's/.*=//; s/://g')"
  fi
done
if [[ " ${PROFILE_SHA1S} " != *" ${SIGN_SHA1} "* ]]; then
  echo "Signing certificate is not contained in the provisioning profile." >&2
  echo "  keychain cert SHA1 : ${SIGN_SHA1}" >&2
  echo "  profile cert SHA1s :${PROFILE_SHA1S}" >&2
  echo "Regenerate the Mac App Store profile with this certificate selected, then re-download it to:" >&2
  echo "  ${PROFILE}" >&2
  exit 1
fi
echo "OK: ${SIGN_SHA1}"

if [[ ! -x "${SRC_TAURI}/resources/runtime/office-agent-runtime" ]]; then
  step "Sidecar not staged — running build-macos.sh --skip-tauri"
  "${ROOT}/scripts/build-macos.sh" --skip-tauri
fi

step "tauri build (app bundle, appstore config)"
export CARGO_TARGET_DIR="${SRC_TAURI}/target"
# Prefer the Distribution identity from the keychain
export APPLE_SIGNING_IDENTITY="${SIGN_IDENTITY}"
(
  cd "${DESKTOP}"
  if [[ ! -d node_modules/@tauri-apps/cli ]]; then
    npm install
  fi
  # Apple Silicon first; universal can be added later when x86_64 target is installed.
  npx --yes tauri build --bundles app --target aarch64-apple-darwin \
    --config src-tauri/tauri.appstore.conf.json
)

APP_PATH="$(find "${CARGO_TARGET_DIR}/aarch64-apple-darwin/release/bundle/macos" -maxdepth 1 -name '*.app' -print | head -1)"
if [[ -z "${APP_PATH}" ]]; then
  # fallback non-cross path
  APP_PATH="$(find "${CARGO_TARGET_DIR}/release/bundle/macos" -maxdepth 1 -name '*.app' -print | head -1 || true)"
fi
if [[ -z "${APP_PATH}" || ! -d "${APP_PATH}" ]]; then
  echo ".app not found under ${CARGO_TARGET_DIR}" >&2
  exit 1
fi
echo "App: ${APP_PATH}"

step "Embed provisioning profile"
# Downloads from browser/Chrome carry com.apple.quarantine; Apple rejects that.
xattr -c "${PROFILE}" 2>/dev/null || true
cp "${PROFILE}" "${APP_PATH}/Contents/embedded.provisionprofile"
xattr -c "${APP_PATH}/Contents/embedded.provisionprofile" 2>/dev/null || true

# Root-only files inside the bundle make Apple reject the package, because the
# installed app's signature can no longer be verified by a normal user.
step "Normalize bundle permissions and strip quarantine xattrs"
find "${APP_PATH}" -type d -exec chmod a+rx {} +
find "${APP_PATH}" -type f -exec chmod a+r {} +
xattr -cr "${APP_PATH}"
UNREADABLE="$(find "${APP_PATH}" \! -perm -o=r)"
if [[ -n "${UNREADABLE}" ]]; then
  echo "Still not world-readable:" >&2
  echo "${UNREADABLE}" >&2
  exit 1
fi
if xattr -lr "${APP_PATH}" 2>/dev/null | grep -qi quarantine; then
  echo "com.apple.quarantine still present after xattr -cr:" >&2
  xattr -lr "${APP_PATH}" 2>/dev/null | grep -i quarantine >&2
  exit 1
fi

# Signing must go inside-out: --deep would overwrite the sidecar's own
# entitlements, and the store rejects nested executables without app-sandbox.
step "Sign sidecar libraries"
RUNTIME_DIR="${APP_PATH}/Contents/Resources/resources/runtime"
find "${RUNTIME_DIR}" -type f \( -name '*.dylib' -o -name '*.so' \) -print0 \
  | xargs -0 codesign --force --options runtime --timestamp=none --sign "${SIGN_IDENTITY}"

step "Sign sidecar executable"
codesign --force --options runtime --timestamp=none \
  --entitlements "${SIDECAR_ENTITLEMENTS}" \
  --sign "${SIGN_IDENTITY}" \
  "${RUNTIME_DIR}/office-agent-runtime"

step "Re-sign app with App Store entitlements"
codesign --force --options runtime \
  --entitlements "${ENTITLEMENTS}" \
  --sign "${SIGN_IDENTITY}" \
  "${APP_PATH}"

step "productbuild .pkg"
mkdir -p "${OUT_DIR}"
PKG_NAME="文书通-mac-appstore.pkg"
PKG_PATH="${OUT_DIR}/${PKG_NAME}"
UNSIGNED_PKG="${OUT_DIR}/文书通-mac-appstore-unsigned.pkg"

INSTALLER_IDENTITY="$(security find-identity -v | grep -E 'Mac Installer Distribution|3rd Party Mac Developer Installer' | head -1 | sed -E 's/.*"(.+)".*/\1/' || true)"

xcrun productbuild --component "${APP_PATH}" /Applications "${UNSIGNED_PKG}"

if [[ -n "${INSTALLER_IDENTITY}" ]]; then
  echo "Using installer identity: ${INSTALLER_IDENTITY}"
  xcrun productsign --sign "${INSTALLER_IDENTITY}" "${UNSIGNED_PKG}" "${PKG_PATH}"
else
  cat <<'EOF' >&2

未找到 Mac Installer Distribution 证书，无法给 .pkg 签名。

请：
  1. 打开 https://developer.apple.com/account/resources/certificates/add
  2. 选择「Mac Installer Distribution」
  3. 上传 packaging/apple/CertificateSigningRequest.certSigningRequest
  4. 下载 .cer 后告诉我，我帮你导入并完成 productsign

已生成未签名包（暂勿上传）：
EOF
  echo "  ${UNSIGNED_PKG}" >&2
  exit 1
fi

step "Done"
cat <<EOF
PKG: ${PKG_PATH}

下一步：
  1. 打开 Transporter（Mac App Store 搜 Transporter）登录 Apple ID
  2. 拖入上述 .pkg 并投送
  3. 到 App Store Connect 等待构建处理完成后，在版本页选择该构建
EOF
