# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Gautam1988
"""Draws inkreader.ico (a page with text lines and a folded corner)."""
import os
from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.polygon([(40, 16), (172, 16), (216, 60), (216, 240), (40, 240)], fill="white", outline="black", width=12)
d.polygon([(172, 16), (172, 60), (216, 60)], fill="black")
for i, y in enumerate(range(92, 220, 30)):
    d.rectangle((70, y, 186 if i % 2 == 0 else 150, y + 12), fill="black")
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inkreader.ico")
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", out)
