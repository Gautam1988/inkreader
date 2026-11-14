# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 GautamMohan
"""Draws the InkReader icon (a page with text lines and a folded corner).

`python make_icon.py` writes inkreader.ico; `draw(size)` is reused for the Store tiles.
"""
import os
from PIL import Image, ImageDraw


def draw(size=256, supersample=4):
    """The icon as an RGBA image of `size` x `size` (drawn large, then downsampled)."""
    s = size * supersample
    k = s / 256.0
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = lambda pts: [(x * k, y * k) for x, y in pts]
    d.polygon(p([(40, 16), (172, 16), (216, 60), (216, 240), (40, 240)]), fill="white", outline="black",
              width=max(1, round(12 * k)))
    d.polygon(p([(172, 16), (172, 60), (216, 60)]), fill="black")
    for i, y in enumerate(range(92, 220, 30)):
        d.rectangle([70 * k, y * k, (186 if i % 2 == 0 else 150) * k, (y + 12) * k], fill="black")
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inkreader.ico")
    draw(256).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", out)
