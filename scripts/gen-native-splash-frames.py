#!/usr/bin/env python3
"""Regenerate Windows native splash frames to match Option E HTML preview proportions.

Reference: docs/superpowers/evals/fixtures/native-splash-option-e-preview.html
  - 420×280, flex column centered, gap 0.85rem, padding 1.5/1.25/1.75rem
  - logo 56×56 from apps/desktop/public/logo-mark.png (transparent, no white tile)
  - brand 1.75rem / 600, whole-string draw (anchor ma), no letter-spacing
  - status 1rem muted, no ellipsis
  - spinner 36×36, r=14, stroke 2.5, dash ~28 (short arc), 12 frames
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "apps/desktop/src-tauri/icons/splash"
LOGO_SRC = ROOT / "apps/desktop/public/logo-mark.png"

PAPER = (243, 244, 241, 255)
INK = (26, 26, 26, 255)
MUTED = (75, 85, 99, 255)  # #4b5563
ACCENT = (47, 111, 106, 255)  # #2f6f6a
RING = (213, 216, 211, 255)  # #d5d8d3

W, H = 420, 280
FRAMES = 12
REM = 16
GAP = round(0.85 * REM)  # 14
SPIN_MT = round(0.35 * REM)  # 6
LOGO_SIZE = 56
SPIN = 36
BRAND_PX = round(1.75 * REM)  # 28
STATUS_PX = REM  # 16


def find_font() -> str:
    for p in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
    ):
        if Path(p).exists():
            return p
    raise SystemExit("No Chinese UI font found")


def load_font(path: str, size: int, *, prefer_bold: bool = False) -> ImageFont.FreeTypeFont:
    # PingFang.ttc: try a few face indices for medium/semibold look
    indices = (1, 2, 0, 3, 4, 5) if prefer_bold else (0, 1, 2)
    if path.endswith(".ttc"):
        last_err: OSError | None = None
        for idx in indices:
            try:
                return ImageFont.truetype(path, size=size, index=idx)
            except OSError as e:
                last_err = e
        if last_err:
            raise last_err
    return ImageFont.truetype(path, size=size)


def text_height(font: ImageFont.ImageFont, text: str) -> int:
    box = font.getbbox(text)
    return box[3] - box[1]


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    fill,
    cx: int,
    y: int,
) -> int:
    """Draw whole string once, horizontally centered at top y; return height."""
    h = text_height(font, text)
    draw.text((cx, y), text, font=font, fill=fill, anchor="ma")
    return h


def draw_spinner(angle_deg: float) -> Image.Image:
    """Match preview SVG: viewBox 36, r=14, stroke 2.5, dasharray 28 100."""
    s = 4
    size = SPIN * s
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    r = 14 * s
    width = 2.5 * s
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=RING, width=max(1, int(round(width))))

    # SVG stroke-dasharray 28 on circumference 2πr → sweep degrees
    circ = 2 * math.pi * 14
    sweep = (28 / circ) * 360.0  # ~114°
    # SVG circle default start is 3 o'clock; preview rotates the arc
    start = angle_deg
    steps = 48
    pts = [
        (
            cx + r * math.cos(math.radians(start + sweep * i / steps)),
            cy + r * math.sin(math.radians(start + sweep * i / steps)),
        )
        for i in range(steps + 1)
    ]
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    line_w = max(1, int(round(width)))
    for i in range(len(pts) - 1):
        md.line([pts[i], pts[i + 1]], fill=255, width=line_w)
    cap_r = width / 2
    for p in (pts[0], pts[-1]):
        md.ellipse([p[0] - cap_r, p[1] - cap_r, p[0] + cap_r, p[1] + cap_r], fill=255)
    accent_layer = Image.new("RGBA", (size, size), ACCENT)
    img.paste(accent_layer, (0, 0), mask)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.35))
    return img.resize((SPIN, SPIN), Image.Resampling.LANCZOS)


def prepare_logo() -> Image.Image:
    logo = Image.open(LOGO_SRC).convert("RGBA")
    # Keep transparency; scale into 56×56 like CSS object-fit: contain
    logo.thumbnail((LOGO_SIZE, LOGO_SIZE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (LOGO_SIZE, LOGO_SIZE), (0, 0, 0, 0))
    canvas.paste(
        logo,
        ((LOGO_SIZE - logo.width) // 2, (LOGO_SIZE - logo.height) // 2),
        logo,
    )
    canvas.save(OUT / "logo.png")
    return canvas


def write_bgra(path: Path, frame: Image.Image) -> None:
    rgba = frame.convert("RGBA")
    w, h = rgba.size
    blob = bytearray(struct.pack("<II", w, h))
    px = rgba.tobytes()
    for o in range(0, len(px), 4):
        r, g, b, a = px[o], px[o + 1], px[o + 2], px[o + 3]
        blob.extend((b, g, r, a))
    path.write_bytes(blob)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    font_path = find_font()
    brand_font = load_font(font_path, BRAND_PX, prefer_bold=True)
    status_font = load_font(font_path, STATUS_PX, prefer_bold=False)
    logo_canvas = prepare_logo()

    brand = "文书通"
    status = "正在启动本地运行组件"
    brand_h = text_height(brand_font, brand)
    status_h = text_height(status_font, status)

    # flex column + gap; spinner also has margin-top
    stack_h = LOGO_SIZE + brand_h + status_h + SPIN + 3 * GAP + SPIN_MT
    y = (H - stack_h) // 2
    cx = W // 2

    for i in range(FRAMES):
        # steps(12) rotation like the preview keyframes
        angle = i * (360 / FRAMES)
        frame = Image.new("RGBA", (W, H), PAPER)
        d = ImageDraw.Draw(frame)

        yy = y
        frame.paste(logo_canvas, (cx - LOGO_SIZE // 2, yy), logo_canvas)
        yy += LOGO_SIZE + GAP

        draw_centered_text(d, brand, brand_font, INK, cx, yy)
        yy += brand_h + GAP

        draw_centered_text(d, status, status_font, MUTED, cx, yy)
        yy += status_h + GAP + SPIN_MT

        spin = draw_spinner(angle)
        frame.paste(spin, (cx - SPIN // 2, yy), spin)

        frame.convert("RGB").save(OUT / f"frame_{i:02d}.png", optimize=True)
        write_bgra(OUT / f"frame_{i:02d}.bgra", frame)
        print("wrote", f"frame_{i:02d}.png/.bgra")

    print(
        f"layout: logo={LOGO_SIZE} brand={BRAND_PX}px status={STATUS_PX}px "
        f"spin={SPIN} gap={GAP} stack_h={stack_h} y0={y}"
    )


if __name__ == "__main__":
    main()
