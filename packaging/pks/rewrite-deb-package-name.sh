#!/usr/bin/env bash
# Rewrite Debian Package: field to ASCII "wenshutong".
# Tauri uses productName (文书通) which dpkg rejects.
set -euo pipefail

IN="${1:?usage: rewrite-deb-package-name.sh <in.deb> [out.deb]}"
OUT="${2:-$IN}"
NAME="${DEB_PACKAGE_NAME:-wenshutong}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT
dpkg-deb -R "${IN}" "${WORKDIR}/unpack"
python3 - "${WORKDIR}/unpack" "${NAME}" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
name = sys.argv[2]
if not name[:1].isalnum() or name.lower() != name or any(
    c != "-" and not c.isalnum() for c in name
):
    raise SystemExit(f"invalid debian package name: {name}")

control = root / "DEBIAN" / "control"
lines = []
for line in control.read_text(encoding="utf-8").splitlines():
    if line.startswith("Package:"):
        lines.append(f"Package: {name}")
    else:
        lines.append(line)
control.write_text("\n".join(lines) + "\n", encoding="utf-8")

# Icon=desktop collides with GNOME's generic "desktop" icon.
for desktop in root.glob("usr/share/applications/*.desktop"):
    text = desktop.read_text(encoding="utf-8")
    text = text.replace("Icon=desktop", f"Icon={name}")
    if "Comment=A Tauri App" in text:
        text = text.replace("Comment=A Tauri App", "Comment=办公文书 · 智能通办")
    desktop.write_text(text, encoding="utf-8")

for png in root.glob("usr/share/icons/hicolor/*/apps/desktop.png"):
    png.rename(png.with_name(f"{name}.png"))

# Kylin V10 SP1 ships WebKitGTK 4.0, not 4.1.
control_text = control.read_text(encoding="utf-8")
control_text = control_text.replace("libwebkit2gtk-4.1-0", "libwebkit2gtk-4.0-37")
control_text = control_text.replace("libjavascriptcoregtk-4.1-0", "libjavascriptcoregtk-4.0-18")
control_text = control_text.replace("libsoup-3.0-0", "libsoup2.4-1")
control.write_text(control_text, encoding="utf-8")
PY
TMP_OUT="${WORKDIR}/out.deb"
dpkg-deb -b "${WORKDIR}/unpack" "${TMP_OUT}"
mv -f "${TMP_OUT}" "${OUT}"
echo "Rewrote Package: ${NAME} -> ${OUT}"
