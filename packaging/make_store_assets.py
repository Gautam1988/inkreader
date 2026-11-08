# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Gautam1988
"""Generates the MSIX tile and logo images (with scale / target-size variants) into a folder.

Usage: python make_store_assets.py <out_dir>
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from PIL import Image  # noqa: E402
from make_icon import draw  # noqa: E402

# name -> (width, height) at scale-100, and how much of the tile height the icon fills
TILES = {
    "Square44x44Logo": ((44, 44), 1.0),
    "Square150x150Logo": ((150, 150), 0.62),
    "Wide310x150Logo": ((310, 150), 0.62),
    "Square71x71Logo": ((71, 71), 0.75),
    "Square310x310Logo": ((310, 310), 0.55),
    "StoreLogo": ((50, 50), 1.0),
}
SCALES = (100, 125, 150, 200, 400)
TARGET_SIZES = (16, 24, 32, 48, 256)   # taskbar / Start / Explorer icons


def tile(w, h, fill):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    icon_px = max(8, int(round(min(w, h) * fill)))
    icon = draw(icon_px)
    img.alpha_composite(icon, ((w - icon_px) // 2, (h - icon_px) // 2))
    return img


def main(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    count = 0
    for name, ((w, h), fill) in TILES.items():
        for scale in SCALES:
            sw, sh = round(w * scale / 100), round(h * scale / 100)
            tile(sw, sh, fill).save(os.path.join(out_dir, f"{name}.scale-{scale}.png"))
            count += 1
    for size in TARGET_SIZES:   # plain icons for the taskbar, Start list and file associations
        for suffix in ("", "_altform-unplated", "_altform-lightunplated"):
            draw(size).save(os.path.join(out_dir, f"Square44x44Logo.targetsize-{size}{suffix}.png"))
            count += 1
    print(f"wrote {count} images to {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Assets")
