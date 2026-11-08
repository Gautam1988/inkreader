#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# InkReader - a calm PDF and e-book reader for e-ink monitors and tired eyes.
# Copyright (C) 2026 Gautam1988
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along
# with this program. If not, see <https://www.gnu.org/licenses/>.
"""InkReader - a calm, high-contrast document reader for e-ink monitors on Windows.

Design rules for e-ink:
  * whole-page (or whole-screen) turns only - no smooth scrolling or animation
  * grayscale rendering with contrast / gamma / bold-text controls
  * optional 16-level, black & white or dithered output
  * optional full-refresh flash (black -> white) to clear ghosting
  * automatic margin cropping so text is as large as possible
  * big click zones: right side = next, left side = previous
"""

import ctypes
import json
import os
import re
import sys
import time
import webbrowser
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog

import pymupdf
from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageTk

APP_NAME = "InkReader"
VERSION = "1.5.2"
COPYRIGHT = "Copyright (C) 2026 Gautam1988"
SOURCE_URL = "https://github.com/Gautam1988/inkreader"
LICENSE_NOTICE = (
    "InkReader is free software under the GNU Affero General Public License v3 or later.\n"
    "It comes with ABSOLUTELY NO WARRANTY. You may redistribute and modify it under\n"
    "the terms of that licence. The complete source code is available at the link below.\n"
    "Built with PyMuPDF / MuPDF (AGPL-3.0, Artifex), Pillow, Python and Tcl/Tk.")

FILETYPES = [
    ("Documents", "*.pdf *.epub *.mobi *.fb2 *.xps *.oxps *.cbz"),
    ("PDF files", "*.pdf"),
    ("E-books", "*.epub *.mobi *.fb2"),
    ("All files", "*.*"),
]

MODES = [
    ("gray", "Grayscale"),
    ("gray16", "16 gray levels (e-ink)"),
    ("bw", "Black & white (sharpest text)"),
    ("dither", "Dithered B&W (photos)"),
]
MODE_SHORT = {"gray": "Gray", "gray16": "16-gray", "bw": "B&W", "dither": "Dither"}
VIEWS = [("page", "Fit page"), ("width", "Fit width"), ("two", "Two pages")]
VIEW_LABEL = dict(VIEWS)

DEFAULTS = {
    "view": "page",
    "crop": True,
    "rotation": 0,
    "schema": 2,
    "mode": "gray",            # gray16 / bw suit e-ink panels; gray is smoothest on LCDs
    "subpixel": "rgb",         # LCD subpixel text: rgb / bgr / off (off for e-ink)
    "width_pct": 100,          # page width in Fit width, % of the screen
    "darkness": 1.6,
    "black_point": 20,
    "white_point": 225,
    "threshold": 170,
    "bold": 1,
    "theme": "night",          # app frame: night (dark) / day
    "page": "warm",            # reading-pane paper style, see PAPERS
    "paper_brightness": 100,
    "quality": 2,
    "keep_photos": True,
    "sharpen": 1,
    "flash_every": 0,
    "overlap": 10,
    "tap_prev": 33,
    "font_size": 12,
    "ui_size": 12,
    "show_toolbar": True,
    "show_status": True,
    "reading_mode": False,     # restore full-screen reading on next launch
    "reading_view": "width",   # layout used in reading mode: fill the screen width
    "reading_info": True,      # small page counter in reading mode
    "geometry": "",
    "maximized": False,
    "recent": [],
    "positions": {},
}
DISPLAY_KEYS = ["page", "paper_brightness", "mode", "darkness", "black_point", "white_point", "threshold", "bold",
                "quality", "keep_photos", "sharpen", "flash_every", "overlap", "tap_prev", "font_size"]
# Reading-pane styles: (label, paper colour, text colour). Off-white, slightly warm paper
# avoids the glare of pure #FFFFFF while keeping near-black text for full contrast.
PAPERS = {
    "warm": ("Warm paper (easiest on the eyes)", "#F1EAD8", "#141414"),
    "soft": ("Soft white", "#ECEBE6", "#111111"),
    "sepia": ("Sepia", "#E8D9BC", "#24190F"),
    "gray": ("Low-glare gray", "#D8D8D4", "#000000"),
    "white": ("Pure white (best on e-ink)", "#FFFFFF", "#000000"),
    "night": ("Night (white text on black)", "#000000", "#ECECEC"),
}


def _hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def page_colors(page, brightness):
    """(paper_rgb, ink_rgb) for a paper style, with the paper dimmed to brightness %."""
    _label, paper, ink = PAPERS.get(page, PAPERS["warm"])
    k = max(50, min(100, brightness)) / 100.0
    paper_rgb = tuple(int(round(c * k)) for c in _hex_rgb(paper))
    return paper_rgb, _hex_rgb(ink)


QUALITIES = [(1, "Standard (fastest)"), (2, "High - 2x supersampled"), (3, "Maximum - 3x supersampled")]
MAX_RENDER_PIXELS = 45_000_000

# Welcome screen (shown while no document is open): always light and quiet.
WELCOME = {"bg": "#ffffff", "fg": "#1a1a1a", "muted": "#6f6f6f", "faint": "#a6a6a6", "line": "#ececec",
           "hover": "#f4f4f4", "btn": "#1a1a1a", "btn_hover": "#3d3d3d", "badge": "#d9d9d9"}

# Palettes. Pure black / near-white keeps e-ink ghosting low; nothing animates.
PALETTES = {
    "night": {"bg": "#000000", "fg": "#ececec", "dim": "#8c8c8c", "trough": "#3c3c3c"},
    "day": {"bg": "#ffffff", "fg": "#000000", "dim": "#555555", "trough": "#ffffff"},
}

CACHE_SIZE = 8
GAP = 12

HELP_TEXT = """\
TURNING PAGES
  Click right side, Right, Down, PgDn, Space, J   next page / screen
  Click left side, Left, Up, PgUp, Backspace, K   previous page / screen
  Mouse wheel                                     one page / screen per notch
  Home / End                                      first / last page
  Ctrl+G                                          go to page number
  Click a link                                    follow it

VIEW
  W            cycle Fit page / Fit width / Two pages
  C            crop white margins on/off
  R            rotate 90 degrees
  F or F11     reading mode (full screen, no bars, pointer hides)
  Esc          leave reading mode / hide toolbar / clear search
  T            show / hide toolbar (or click the top-center of the page;
               in reading mode, also move the mouse to the top edge)
  H            page number in reading mode on / off
  + / -        zoom: Fit page -> wider -> full width  (e-books: font size)
  Ctrl+wheel   zoom                Ctrl+0  full screen width

E-INK
  M            cycle Gray / 16-gray / Black & white / Dithered
  B            cycle bold text 0-3
  [ / ]        lighter / darker text
  I            paper: warm / soft white / sepia / gray / pure white / night
  U            dark / light app frame (toolbar and surround)
  Q            resolution: standard / high (2x) / maximum (3x)
  F5           full screen refresh (clears ghosting)
  Ctrl+D       display settings

OTHER
  Ctrl+O       open          Ctrl+F  find        F3  find next
  Ctrl+T       contents      Right-click        menu with everything
  Ctrl+Q       quit
"""


# ----------------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------------

def config_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


class Settings(dict):
    def __init__(self):
        super().__init__(json.loads(json.dumps(DEFAULTS)))
        self.path = os.path.join(config_dir(), "settings.json")
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for key, default in DEFAULTS.items():
                if key not in data:
                    continue
                v = data[key]
                if isinstance(default, bool):
                    ok = isinstance(v, bool)
                elif isinstance(default, (int, float)):
                    ok = isinstance(v, (int, float)) and not isinstance(v, bool)
                else:
                    ok = isinstance(v, type(default))
                if ok:
                    self[key] = v
            if int(data.get("schema", 1)) < 2:   # v1.4: wide reading mode, LCD-smooth text
                if self["reading_view"] in ("", "page"):
                    self["reading_view"] = "width"
                if self["mode"] == "gray16":
                    self["mode"] = "gray"
                self["schema"] = 2
        except (OSError, ValueError):
            pass

    def save(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self, fh, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass


# ----------------------------------------------------------------------------
# Image processing for e-ink
# ----------------------------------------------------------------------------

@lru_cache(maxsize=32)
def levels_lut(black, white, darkness):
    span = max(1, white - black)
    lut = []
    for v in range(256):
        x = (v - black) / span
        x = 0.0 if x < 0 else 1.0 if x > 1 else x
        lut.append(int(round((x ** darkness) * 255)))
    return tuple(lut)


@lru_cache(maxsize=8)
def threshold_lut(threshold):
    return tuple(255 if v >= threshold else 0 for v in range(256))


GRAY16_LUT = tuple(min(255, int(round(v / 17.0)) * 17) for v in range(256))


BOLD_PX = {0: 0.0, 1: 0.5, 2: 1.0, 3: 1.6}   # stroke growth per side, in screen pixels


def _erode(img, steps):
    for _ in range(steps):
        img = img.filter(ImageFilter.MinFilter(3))
    return img


def embolden(img, bold, ss):
    """Thicken dark strokes. Working at ss-times resolution gives sub-pixel control."""
    radius = BOLD_PX.get(bold, 1.6) * ss
    whole = int(radius)
    frac = radius - whole
    base = _erode(img, whole)
    if frac > 0.05:
        base = Image.blend(base, _erode(base, 1), frac)
    return base


# ----------------------------------------------------------------------------
# LCD subpixel text (ClearType-style): each screen pixel has separate red, green
# and blue stripes, so rendering 3 samples per pixel triples horizontal detail.
# ----------------------------------------------------------------------------

MAX_SUBPIXEL_PIXELS = 32_000_000


def _shift(img, dx, dy):
    return ImageChops.offset(img, dx, dy)


def _erode_dir(img, radius, dx, dy):
    """Grow dark strokes by `radius` pixels along one axis (fractional radius blends)."""
    def step(im):
        return ImageChops.darker(ImageChops.darker(im, _shift(im, dx, dy)), _shift(im, -dx, -dy))
    whole = int(radius)
    frac = radius - whole
    for _ in range(whole):
        img = step(img)
    if frac > 0.05:
        img = Image.blend(img, step(img), frac)
    return img


def _lcd_filter(img):
    """FreeType's default LCD filter [8, 77, 86, 77, 8]/256 along rows: tames colour fringes."""
    near = Image.blend(_shift(img, 1, 0), _shift(img, -1, 0), 0.5)
    far = Image.blend(_shift(img, 2, 0), _shift(img, -2, 0), 0.5)
    mid = Image.blend(img, near, 154 / 240)       # (86 : 154) of the inner 240/256
    return Image.blend(mid, far, 16 / 256)


@lru_cache(maxsize=32)
def _tint_lut(paper, ink):
    lut = []
    for c in range(3):
        lut += [int(round(ink[c] + (paper[c] - ink[c]) * v / 255.0)) for v in range(256)]
    return lut


def subpixel_post(gray, proc, ss, order):
    """gray was rasterized at 3*ss x horizontal and ss x vertical resolution.
    Returns an RGB ink-on-paper image with one sample per R/G/B stripe. Pillow only (thread-safe)."""
    black, white, darkness, bold = proc[0], proc[1], proc[2], proc[3]
    wn, hn = max(1, gray.width // (3 * ss)), max(1, gray.height // ss)
    g = gray.point(levels_lut(black, white, darkness))     # 255 = paper, 0 = ink
    grow = BOLD_PX.get(bold, 1.6)
    if grow:
        g = _erode_dir(g, grow * 3 * ss, 1, 0)
        g = _erode_dir(g, grow * ss, 0, 1)
    g = g.crop((0, 0, wn * 3 * ss, hn * ss))
    if ss > 1:      # area-average supersampled rows / columns down to subpixel resolution
        g = g.reduce(ss)
    g = _lcd_filter(g)
    # consecutive samples in a row are exactly the R, G, B stripes of one screen pixel
    rgb = Image.frombytes("RGB", (wn, hn), g.tobytes())
    if order == "bgr":
        r, gg, b = rgb.split()
        rgb = Image.merge("RGB", (b, gg, r))
    paper, ink = page_colors(proc[10], proc[11])
    return rgb.point(_tint_lut(paper, ink))


def finish_render(job):
    """Second render stage: pure Pillow image processing, safe to run on the worker thread."""
    pno, gray, mat, ox, oy, proc, ss, kind, photo_boxes = job
    if kind in ("rgb", "bgr"):
        img = subpixel_post(gray, proc, ss, kind)
    else:
        img = process_image(gray, proc, ss)
        if not proc[6]:  # tint black-on-white into ink-on-paper
            paper_rgb, ink_rgb = page_colors(proc[10], proc[11])
            if paper_rgb != (255, 255, 255) or ink_rgb != (0, 0, 0):
                img = ImageOps.colorize(img, black=ink_rgb, white=paper_rgb)
    for x0, y0, x1, y1 in photo_boxes:  # night page: show photos un-inverted
        box = (x0, y0, min(img.width, x1), min(img.height, y1))
        if box[2] - box[0] >= 24 and box[3] - box[1] >= 24:
            img.paste(ImageOps.invert(img.crop(box)), box)
    return Rendered(pno, img, mat, ox, oy)


# One background thread for image processing. MuPDF itself only ever runs on the UI thread.
WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inkreader-render")


def process_image(img, proc, ss=1):
    """img is rendered at ss times the screen size; returns a screen-sized image."""
    black, white, darkness, bold, mode, threshold, invert, _quality, sharpen = proc[:9]
    img = img.point(levels_lut(black, white, darkness))
    if bold:
        img = embolden(img, bold, ss)
    if ss > 1:
        img = img.resize((max(1, round(img.width / ss)), max(1, round(img.height / ss))),
                         Image.LANCZOS, reducing_gap=2.0)
    if sharpen:
        img = img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=45 * sharpen, threshold=1))
    if mode == "gray16":
        img = img.point(GRAY16_LUT)
    elif mode == "bw":
        img = img.point(threshold_lut(threshold))
    elif mode == "dither":
        img = img.convert("1").convert("L")  # Floyd-Steinberg
    if invert:
        img = ImageOps.invert(img)
    return img


# ----------------------------------------------------------------------------
# Document + render cache
# ----------------------------------------------------------------------------

class Rendered:
    __slots__ = ("pno", "img", "mat", "ox", "oy", "photo")

    def __init__(self, pno, img, mat, ox, oy):
        self.pno, self.img, self.mat, self.ox, self.oy = pno, img, mat, ox, oy
        self.photo = None

    def get_photo(self):
        if self.photo is None:
            self.photo = ImageTk.PhotoImage(self.img)
        return self.photo


def _gray_image(pix):
    return Image.frombytes("L", (pix.width, pix.height), pix.samples, "raw", "L", pix.stride)


class Document:
    def __init__(self, path):
        self.path = path
        self.doc = pymupdf.open(path)
        self.reflowable = bool(self.doc.is_reflowable)
        self.layout_key = None
        self.cache = OrderedDict()
        self.pending = {}           # key -> Future of a background render
        self.page_bbox = {}
        self.doc_margins = None

    @property
    def page_count(self):
        return self.doc.page_count

    def close(self):
        self.cache.clear()
        self.pending.clear()
        try:
            self.doc.close()
        except Exception:
            pass

    def relayout(self, w_pt, h_pt, fontsize, keep_page):
        """Re-flow e-books to the screen shape. Returns the page that keeps the reading spot."""
        if not self.reflowable:
            return keep_page
        key = (max(100, int(w_pt)), max(100, int(h_pt)), int(fontsize))
        if key == self.layout_key:
            return keep_page
        bookmark = None
        if self.layout_key is not None:
            try:
                bookmark = self.doc.make_bookmark(self.doc.location_from_page_number(keep_page))
            except Exception:
                bookmark = None
        self.doc.layout(width=key[0], height=key[1], fontsize=key[2])
        self.layout_key = key
        self.cache.clear()
        self.pending.clear()
        self.page_bbox.clear()
        self.doc_margins = None
        if bookmark is not None:
            try:
                keep_page = self.doc.page_number_from_location(self.doc.find_bookmark(bookmark))
            except Exception:
                pass
        return max(0, min(self.page_count - 1, keep_page))

    # -- margin cropping ------------------------------------------------------

    def _content_bbox(self, page):
        """Content box as fractions (l, t, r, b) of the page, or None if blank."""
        r = page.rect
        s = 400.0 / max(r.width, r.height, 1)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(s, s), colorspace=pymupdf.csGRAY, alpha=False)
        mask = _gray_image(pix).point(lambda v: 255 if v < 215 else 0)
        box = mask.getbbox()
        if not box:
            return None
        return (box[0] / pix.width, box[1] / pix.height, box[2] / pix.width, box[3] / pix.height)

    def _bbox_for(self, pno, page=None):
        if pno not in self.page_bbox:
            try:
                self.page_bbox[pno] = self._content_bbox(page or self.doc[pno])
            except Exception:
                self.page_bbox[pno] = None
        return self.page_bbox[pno]

    def _document_margins(self):
        """Typical margins across the document so pages keep a consistent size."""
        if self.doc_margins is None:
            n = self.page_count
            count = min(n, 16)
            samples = sorted({int(i * (n - 1) / max(1, count - 1)) for i in range(count)})
            boxes = [b for b in (self._bbox_for(p) for p in samples) if b]
            if not boxes:
                self.doc_margins = (0.0, 0.0, 1.0, 1.0)
            else:
                q = int(len(boxes) * 0.25)
                lefts = sorted(b[0] for b in boxes)
                tops = sorted(b[1] for b in boxes)
                rights = sorted((b[2] for b in boxes), reverse=True)
                bottoms = sorted((b[3] for b in boxes), reverse=True)
                self.doc_margins = (lefts[q], tops[q], rights[q], bottoms[q])
        return self.doc_margins

    def clip_for(self, page, pno, crop):
        r = page.rect
        if not crop:
            return r
        dl, dt, dr, db = self._document_margins()
        own = self._bbox_for(pno, page)
        if own:  # never cut this page's own content
            dl, dt, dr, db = min(dl, own[0]), min(dt, own[1]), max(dr, own[2]), max(db, own[3])
        pad = 0.012
        dl, dt = max(0.0, dl - pad), max(0.0, dt - pad)
        dr, db = min(1.0, dr + pad), min(1.0, db + pad)
        if dr - dl < 0.25 or db - dt < 0.25:
            return r
        return pymupdf.Rect(r.x0 + dl * r.width, r.y0 + dt * r.height,
                            r.x0 + dr * r.width, r.y0 + db * r.height)

    # -- rendering ------------------------------------------------------------

    def _store(self, key, res):
        self.cache[key] = res
        self.cache.move_to_end(key)
        while len(self.cache) > CACHE_SIZE:
            self.cache.popitem(last=False)

    def render(self, pno, fit, box_w, box_h, crop, rotation, proc):
        key = (pno, fit, box_w, box_h, crop, rotation, proc, self.layout_key)
        hit = self.cache.get(key)
        if hit is not None:
            self.cache.move_to_end(key)
            return hit
        res = None
        fut = self.pending.pop(key, None)
        if fut is not None:          # already being prepared in the background
            try:
                res = fut.result()
            except Exception:
                res = None
        if res is None:
            res = finish_render(self._rasterize(pno, fit, box_w, box_h, crop, rotation, proc))
        self._store(key, res)
        return res

    def prefetch(self, pno, fit, box_w, box_h, crop, rotation, proc):
        """Rasterize now (fast, UI thread) and finish the image on the worker thread."""
        key = (pno, fit, box_w, box_h, crop, rotation, proc, self.layout_key)
        if key in self.cache or key in self.pending:
            return
        self.pending[key] = WORKER.submit(finish_render,
                                          self._rasterize(pno, fit, box_w, box_h, crop, rotation, proc))
        while len(self.pending) > CACHE_SIZE:
            self.pending.pop(next(iter(self.pending))).cancel()

    def collect(self):
        """Move finished background renders into the cache; returns them (UI thread)."""
        done = []
        for key in [k for k, f in self.pending.items() if f.done()]:
            try:
                res = self.pending.pop(key).result()
            except Exception:
                continue
            self._store(key, res)
            done.append(res)
        return done

    def _rasterize(self, pno, fit, box_w, box_h, crop, rotation, proc):
        """First render stage: everything that touches MuPDF. UI thread only."""
        page = self.doc[pno]
        clip = self.clip_for(page, pno, crop)
        w, h = clip.width, clip.height
        if rotation % 180:
            w, h = h, w
        if fit == "width":
            scale = box_w / max(w, 1)
        else:
            scale = min(box_w / max(w, 1), box_h / max(h, 1))
        scale = max(0.05, min(scale, 25.0))
        mat = pymupdf.Matrix(scale, scale).prerotate(rotation)
        kind = proc[12] if proc[4] == "gray" else "off"
        ss = max(1, int(proc[7]))
        if kind in ("rgb", "bgr") and (w * scale * 3) * (h * scale) <= MAX_SUBPIXEL_PIXELS:
            while ss > 1 and (w * scale * 3 * ss) * (h * scale * ss) > MAX_SUBPIXEL_PIXELS:
                ss -= 1
            xs = 3 * ss          # 3 horizontal samples per pixel: one per R/G/B stripe
        else:
            kind = "classic"     # supersample, then downscale with Lanczos
            while ss > 1 and (w * scale * ss) * (h * scale * ss) > MAX_RENDER_PIXELS:
                ss -= 1
            xs = ss
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale * xs, scale * ss).prerotate(rotation),
                              clip=clip, colorspace=pymupdf.csGRAY, alpha=False)
        ox, oy = pix.x / xs, pix.y / ss
        boxes = self._photo_boxes(page, clip, mat, ox, oy) if proc[6] and proc[9] else []
        return (pno, _gray_image(pix), mat, ox, oy, proc, ss, kind, boxes)

    @staticmethod
    def _photo_boxes(page, clip, mat, ox, oy):
        """Screen boxes of embedded photos, re-inverted in night mode so they look natural.
        Page-sized images (scanned books) are skipped so scans get the night look too."""
        try:
            infos = page.get_image_info()
        except Exception:
            return []
        page_area = abs(page.rect)
        boxes = []
        for info in infos:
            bbox = pymupdf.Rect(info.get("bbox", (0, 0, 0, 0))) & clip
            if bbox.is_empty or abs(bbox) > 0.6 * page_area:
                continue
            q = bbox * mat
            boxes.append((max(0, int(q.x0 - ox)), max(0, int(q.y0 - oy)), int(q.x1 - ox + 1), int(q.y1 - oy + 1)))
        return boxes


# ----------------------------------------------------------------------------
# Windows helpers
# ----------------------------------------------------------------------------

def enable_dpi_awareness():
    """Render at true device pixels (never let Windows bitmap-stretch the window)."""
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # per-monitor v2
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def set_dark_titlebar(win, dark):
    """Windows 10/11 dark title bar."""
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


def geometry_on_screen(geom):
    """True if the saved window position is on a currently connected monitor."""
    try:
        x, y = (int(v) for v in re.findall(r"[+](-?\d+)", geom)[:2])
        gsm = ctypes.windll.user32.GetSystemMetrics
        vx, vy, vw, vh = gsm(76), gsm(77), gsm(78), gsm(79)
        return vx - 50 <= x < vx + vw - 100 and vy - 50 <= y < vy + vh - 100
    except Exception:
        return False


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


# ----------------------------------------------------------------------------
# Application
# ----------------------------------------------------------------------------

class App:
    def __init__(self, root, path=None):
        self.root = root
        self.s = Settings()
        self.doc = None
        self.page = 0
        self.offset = 0.0
        self.pending_offset = None   # None | ("frac", f) | ("end",)
        self.placed = []             # [Rendered, x, y]
        self.render_args = None
        self.turns = 0
        self.busy = False
        self.last_wheel = 0.0
        self.search = None
        self.prefetch_queue = []
        self.jobs = {}
        self.fullscreen = False      # reading mode
        self.overlay = False         # toolbar floating over the page in reading mode
        self.normal_view = None
        self.hint_until = 0.0
        self.toast_text, self.toast_until = "", 0.0
        self.display_win = None
        self.find_win = None

        self.font = tkfont.Font(family="Segoe UI", size=self.s["ui_size"], weight="bold")
        self.font_small = tkfont.Font(family="Segoe UI", size=max(8, self.s["ui_size"] - 2))

        root.title(APP_NAME)
        root.configure(bg="white")
        root.minsize(480, 360)
        geom = self.s["geometry"]
        if geom and geometry_on_screen(geom):
            root.geometry(geom)
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{int(sw * 0.6)}x{int(sh * 0.85)}+{int(sw * 0.2)}+{int(sh * 0.04)}")
        if self.s["maximized"]:
            root.state("zoomed")

        self._build_ui()
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", lambda: (log("window closed (close button / Alt+F4)"), self.quit()))
        root.after(60, self._update_titlebar)
        if self.s["reading_mode"]:
            root.after(150, lambda: self.set_reading_mode(True))
        if path:
            root.after(80, lambda: self.open(path))

    # -- small utilities ------------------------------------------------------

    def _later(self, name, ms, fn):
        job = self.jobs.pop(name, None)
        if job:
            self.root.after_cancel(job)

        def run():
            self.jobs.pop(name, None)
            fn()
        self.jobs[name] = self.root.after(ms, run)

    @staticmethod
    def _bordered(parent, text, cmd, font, padx, pady):
        """Flat button inside a 1px frame - the frame is the border (works in both themes)."""
        frame = tk.Frame(parent)
        frame._is_border = True
        b = tk.Button(frame, text=text, command=cmd, font=font, relief="flat", bd=0,
                      highlightthickness=0, padx=padx, pady=pady, takefocus=0)
        b.pack(padx=1, pady=1)
        return frame, b

    def _btn(self, parent, text, cmd):
        frame, b = self._bordered(parent, text, cmd, self.font, 10, 1)
        frame.pack(side="left", padx=(0, 5), pady=5)
        return b

    def _set_toggle(self, btn, on):
        p = self.pal()
        btn._is_toggle = True
        btn.config(bg=p["fg"] if on else p["bg"], fg=p["bg"] if on else p["fg"])

    def _canvas_size(self):
        return max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())

    @property
    def night(self):
        return self.s["theme"] == "night"

    @property
    def page_night(self):
        return self.s["page"] == "night"

    def pal(self):
        return PALETTES["night" if self.night else "day"]

    def ink(self):      # app-frame foreground (around the page)
        return self.pal()["fg"]

    def paper(self):    # app-frame background (around the page)
        return self.pal()["bg"]

    def page_ink(self):
        return "#%02x%02x%02x" % page_colors(self.s["page"], self.s["paper_brightness"])[1]

    def theme_widget(self, w):
        """Recolor a widget tree with the current palette."""
        p = self.pal()
        bg, fg = p["bg"], p["fg"]
        cls = w.winfo_class()
        border = dict(bd=0, highlightthickness=1, highlightbackground=fg, highlightcolor=fg)
        try:
            if getattr(w, "_is_border", False):
                w.config(bg=fg)
            elif cls in ("Frame", "Toplevel", "Tk"):
                w.config(bg=bg)
            elif cls == "Button":
                if not getattr(w, "_is_toggle", False):
                    w.config(bg=bg, fg=fg)
                w.config(activebackground=fg, activeforeground=bg)
            elif cls == "Label":
                w.config(bg=bg, fg=fg)
            elif cls == "Entry":
                w.config(bg=bg, fg=fg, insertbackground=fg, selectbackground=fg, selectforeground=bg, **border)
            elif cls == "Listbox":
                w.config(bg=bg, fg=fg, selectbackground=fg, selectforeground=bg, **border)
            elif cls == "Scale":
                w.config(bg=bg, fg=fg, troughcolor=p["trough"], activebackground=fg,
                         highlightthickness=0, bd=1, sliderrelief="raised")
            elif cls in ("Radiobutton", "Checkbutton"):
                w.config(bg=bg, fg=fg, activebackground=bg, activeforeground=fg, selectcolor=bg)
            elif cls == "Canvas":
                w.config(bg=self.paper() if self.doc else WELCOME["bg"])
        except tk.TclError:
            pass
        for child in w.winfo_children():
            self.theme_widget(child)

    def finish_window(self, win):
        self.theme_widget(win)
        set_dark_titlebar(win, self.night)

    def _update_titlebar(self):
        """Dark title bar only while reading in the dark frame; the welcome screen stays light."""
        set_dark_titlebar(self.root, self.night and self.doc is not None)

    def apply_theme(self):
        self.finish_window(self.root)
        self._update_titlebar()
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel):
                self.finish_window(w)
        self._set_toggle(self.b_crop, self.s["crop"])

    # -- UI construction ------------------------------------------------------

    def _build_ui(self):
        self.toolbar = tb = tk.Frame(self.root, bg="white")
        self.b_open = self._btn(tb, "Open", self.open_menu)
        self._btn(tb, "Contents", self.show_toc)
        self._btn(tb, "◀", self.prev_screen)
        self.page_var = tk.StringVar()
        self.page_entry = tk.Entry(tb, textvariable=self.page_var, width=6, font=self.font,
                                   justify="center", relief="solid", bd=1, bg="white", fg="black",
                                   insertbackground="black", highlightthickness=0)
        self.page_entry.pack(side="left", padx=(0, 5), ipady=2)
        self.page_entry.bind("<Return>", self._entry_go)
        self.page_entry.bind("<Escape>", lambda e: (self.canvas.focus_set(), self.update_status()))
        self.total_label = tk.Label(tb, text="", font=self.font, bg="white", fg="black")
        self.total_label.pack(side="left", padx=(0, 5))
        self._btn(tb, "▶", self.next_screen)
        self.b_view = self._btn(tb, VIEW_LABEL[self.s["view"]], self.cycle_view)
        self.b_crop = self._btn(tb, "Crop", self.toggle_crop)
        self._btn(tb, "Rotate", self.rotate)
        self._btn(tb, "Find", self.show_find)
        self._btn(tb, "Paper", self.cycle_paper)
        self._btn(tb, "Display", self.show_display)
        self._btn(tb, "Refresh", self.flash_refresh)
        self.b_full = self._btn(tb, "Reading mode", self.toggle_fullscreen)
        self._btn(tb, "?", self.show_help)
        self.rule = tk.Frame(self.root, bg="black", height=2)

        self.canvas = tk.Canvas(self.root, bg="white", highlightthickness=0, bd=0, takefocus=1)
        self.status_rule = tk.Frame(self.root, bg="black", height=1)
        self.status = tk.Label(self.root, font=self.font_small, bg="white", fg="black",
                               anchor="w", padx=10, pady=2)
        self._layout_chrome()

        c = self.canvas
        c.bind("<Button-1>", self.on_click)
        c.bind("<MouseWheel>", self.on_wheel)
        c.bind("<Control-MouseWheel>", self.on_ctrl_wheel)
        c.bind("<Button-3>", self.on_context)
        c.bind("<Motion>", self.on_motion)
        c.bind("<Configure>", lambda e: self._later("resize", 250, self.refresh_view))
        self.rule._is_border = self.status_rule._is_border = True
        self.apply_theme()
        c.focus_set()

    def _layout_chrome(self):
        for w in (self.toolbar, self.rule, self.canvas, self.status, self.status_rule):
            w.pack_forget()
            w.place_forget()
        self.overlay = False
        if self.fullscreen or not self.doc:   # reading mode / welcome screen: nothing but the canvas
            self.canvas.pack(side="top", fill="both", expand=True)
            return
        if self.s["show_toolbar"]:
            self.toolbar.pack(side="top", fill="x", padx=6)
            self.rule.pack(side="top", fill="x")
        if self.s["show_status"]:
            self.status.pack(side="bottom", fill="x")
            self.status_rule.pack(side="bottom", fill="x")
        self.canvas.pack(side="top", fill="both", expand=True)

    def _bind_keys(self):
        r = self.root

        def key(seq, fn):
            def handler(e):
                if isinstance(e.widget, (tk.Entry, tk.Listbox)):
                    return None
                fn()
                return "break"
            r.bind(seq, handler)

        def ctrl(letter, fn):
            r.bind(f"<Control-{letter}>", lambda e: (fn(), "break")[1])
            r.bind(f"<Control-{letter.upper()}>", lambda e: (fn(), "break")[1])

        for seq in ("<Right>", "<Down>", "<Next>", "<space>", "j", "n"):
            key(seq, self.next_screen)
        for seq in ("<Left>", "<Up>", "<Prior>", "<BackSpace>", "<Shift-space>", "k", "p"):
            key(seq, self.prev_screen)
        key("<Home>", lambda: self.goto(0))
        key("<End>", lambda: self.goto(self.doc.page_count - 1) if self.doc else None)
        key("w", self.cycle_view)
        key("c", self.toggle_crop)
        key("r", self.rotate)
        key("i", self.cycle_paper)
        key("u", self.toggle_theme)
        key("q", self.cycle_quality)
        key("b", self.cycle_bold)
        key("m", self.cycle_mode)
        key("f", self.toggle_fullscreen)
        key("t", self.toggle_toolbar)
        key("h", self.toggle_reading_info)
        key("<question>", self.show_help)
        key("<plus>", lambda: self.zoom(+1))
        key("<equal>", lambda: self.zoom(+1))
        key("<minus>", lambda: self.zoom(-1))
        key("<KP_Add>", lambda: self.zoom(+1))
        key("<KP_Subtract>", lambda: self.zoom(-1))
        for seq in ("<Control-plus>", "<Control-equal>", "<Control-KP_Add>"):
            r.bind(seq, lambda e: (self.zoom(+1), "break")[1])
        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            r.bind(seq, lambda e: (self.zoom(-1), "break")[1])
        r.bind("<Control-0>", lambda e: (self.zoom_full_width(), "break")[1])
        key("<bracketright>", lambda: self.change_darkness(+0.2))
        key("<bracketleft>", lambda: self.change_darkness(-0.2))
        key("<Escape>", self.escape)
        r.bind("<F1>", lambda e: self.show_help())
        r.bind("<F3>", lambda e: self.find_next())
        r.bind("<F5>", lambda e: self.flash_refresh())
        r.bind("<F11>", lambda e: self.toggle_fullscreen())
        ctrl("o", self.open_dialog)
        ctrl("f", self.show_find)
        ctrl("g", self.focus_page_entry)
        ctrl("t", self.show_toc)
        ctrl("d", self.show_display)
        ctrl("q", lambda: (log("Ctrl+Q"), self.quit()))

    # -- opening / closing ----------------------------------------------------

    def open_dialog(self):
        recent = [p for p in self.s["recent"] if os.path.exists(p)]
        initial = os.path.dirname(recent[0]) if recent else os.path.expanduser("~")
        path = filedialog.askopenfilename(parent=self.root, title="Open document",
                                          filetypes=FILETYPES, initialdir=initial)
        if path:
            self.open(path)

    def open_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Open file...        Ctrl+O", command=self.open_dialog)
        recent = [p for p in self.s["recent"] if os.path.exists(p)][:10]
        if recent:
            m.add_separator()
            for p in recent:
                m.add_command(label=os.path.basename(p), command=lambda p=p: self.open(p))
        if self.doc:
            m.add_separator()
            m.add_command(label="Close document", command=self.close_doc)
        m.tk_popup(self.b_open.winfo_rootx(), self.b_open.winfo_rooty() + self.b_open.winfo_height())

    def open(self, path):
        path = os.path.abspath(path)
        try:
            new = Document(path)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not open:\n{path}\n\n{exc}", parent=self.root)
            return
        if new.doc.needs_pass:
            ok = False
            for _ in range(3):
                pw = simpledialog.askstring(APP_NAME, "This document is password protected.\nPassword:",
                                            show="*", parent=self.root)
                if pw is None:
                    break
                if new.doc.authenticate(pw):
                    ok = True
                    break
            if not ok:
                new.close()
                return
        if new.page_count == 0:
            new.close()
            messagebox.showerror(APP_NAME, "This document has no pages.", parent=self.root)
            return
        self.close_doc(repaint=False)
        self.doc = new
        pos = self.s["positions"].get(path)
        self.page = max(0, min(new.page_count - 1, int(pos[0]))) if pos else 0
        self.pending_offset = ("frac", float(pos[1])) if pos else None
        self.offset = 0.0
        self.turns = 0
        recent = [p for p in self.s["recent"] if os.path.normcase(p) != os.path.normcase(path)]
        self.s["recent"] = [path] + recent[:14]
        self.root.title(f"{os.path.basename(path)} - {APP_NAME}")
        self.s.save()
        self.canvas.config(bg=self.paper(), cursor="")
        self._layout_chrome()          # toolbar + status bar come back with a document
        self._update_titlebar()
        self.root.update_idletasks()   # settle the canvas size before the first render
        self.show()
        self.canvas.focus_set()

    def close_doc(self, repaint=True):
        if self.doc:
            self.save_position()
            self.doc.close()
        self.doc = None
        self.placed = []
        self.search = None
        self.prefetch_queue = []
        self.root.title(APP_NAME)
        if repaint:
            self._layout_chrome()
            self._update_titlebar()
            self.root.update_idletasks()
            self.paint_empty()
            self.update_status()

    def save_position(self):
        if not self.doc:
            return
        frac = 0.0
        if self.s["view"] == "width" and self.placed:
            frac = self.offset / max(1, self.placed[0][0].img.height)
        pos = self.s["positions"]
        pos.pop(self.doc.path, None)
        pos[self.doc.path] = [self.page, round(frac, 4)]
        while len(pos) > 300:
            pos.pop(next(iter(pos)))
        self._later("save", 3000, self.s.save)

    def quit(self):
        self.save_position()
        self.s["reading_mode"] = self.fullscreen
        if self.fullscreen:   # store the reading layout, restore the window layout
            self.s["reading_view"] = self.s["view"]
            self.s["view"] = self.normal_view or self.s["view"]
        else:
            self.s["maximized"] = self.root.state() == "zoomed"
            if not self.s["maximized"]:
                self.s["geometry"] = self.root.geometry()
        self.s.save()
        for job in list(self.jobs.values()):
            self.root.after_cancel(job)
        self.jobs.clear()
        if self.doc:
            self.doc.close()
        self.root.destroy()

    # -- layout + painting ----------------------------------------------------

    def proc(self):
        s = self.s
        return (int(s["black_point"]), int(s["white_point"]), round(float(s["darkness"]), 2),
                int(s["bold"]), s["mode"], int(s["threshold"]), self.page_night,
                int(s["quality"]), int(s["sharpen"]), bool(s["keep_photos"]),
                s["page"], int(s["paper_brightness"]), s["subpixel"])

    def pages_per_view(self):
        return 2 if self.s["view"] == "two" else 1

    def refresh_view(self):
        """Re-render keeping the reading position (after resize / settings change)."""
        if self.doc and self.s["view"] == "width" and self.placed and self.pending_offset is None:
            self.pending_offset = ("frac", self.offset / max(1, self.placed[0][0].img.height))
        self.show()

    def show(self, flash_ok=False, focus=None):
        if not self.doc:
            self.paint_empty()
            self.update_status()
            return
        cw, ch = self._canvas_size()
        if cw < 40 or ch < 40:
            return
        s = self.s
        view = s["view"]
        if view == "two":
            box_w, box_h, fit = (cw - GAP) // 2, ch, "page"
        elif view == "width":
            box_w, box_h, fit = max(200, int(cw * s["width_pct"] / 100)), ch, "width"
        else:
            box_w, box_h, fit = cw, ch, "page"

        if self.doc.reflowable:
            dpi = self.root.winfo_fpixels("1i") or 96
            lw, lh = box_w * 72 / dpi, box_h * 72 / dpi
            if s["rotation"] % 180:
                lw, lh = lh, lw
            self.page = self.doc.relayout(lw, lh, s["font_size"], self.page)

        n = self.doc.page_count
        self.page = max(0, min(n - 1, self.page))
        crop = bool(s["crop"]) and not self.doc.reflowable  # e-books are already laid out to fit
        self.render_args = (fit, box_w, box_h, crop, int(s["rotation"]), self.proc())
        pnos = [self.page]
        if view == "two" and self.page + 1 < n:
            pnos.append(self.page + 1)
        try:
            rendered = [self.doc.render(p, *self.render_args) for p in pnos]
        except Exception as exc:
            self.canvas.delete("all")
            self.canvas.create_text(cw // 2, ch // 2, text=f"Could not render page {self.page + 1}\n{exc}",
                                    font=self.font, fill=self.ink(), justify="center")
            return

        self.placed = []
        if view == "two":
            total = sum(r.img.width for r in rendered) + GAP * (len(rendered) - 1)
            x = (cw - total) // 2
            for r in rendered:
                self.placed.append([r, x, (ch - r.img.height) // 2])
                x += r.img.width + GAP
        else:
            r = rendered[0]
            y = (ch - r.img.height) // 2 if r.img.height <= ch else 0
            self.placed.append([r, (cw - r.img.width) // 2, y])

        height = rendered[0].img.height
        if view == "width" and height > ch:
            po = self.pending_offset
            if po and po[0] == "end":
                self.offset = height - ch
            elif po and po[0] == "frac":
                self.offset = po[1] * height
            if focus is not None:
                fr = self._to_canvas_rect(rendered[0], focus)
                if fr and not (self.offset <= fr[1] and fr[3] <= self.offset + ch):
                    self.offset = fr[1] - ch * 0.3
            self.offset = max(0.0, min(float(height - ch), self.offset))
        else:
            self.offset = 0.0
        self.pending_offset = None
        self.paint(flash_ok)
        self.schedule_prefetch()
        self.save_position()

    def paint(self, flash_ok=False):
        every = int(self.s["flash_every"])
        if flash_ok and every > 0 and self.turns > 0 and self.turns % every == 0:
            self._flash(self._draw)
        else:
            self._draw()

    def _flash(self, then):
        self.busy = True
        c = self.canvas
        c.delete("all")
        c.config(bg=self.ink())   # flash to the opposite color, then back to paper
        c.update_idletasks()

        def to_white():
            c.config(bg=self.paper())
            c.update_idletasks()
            self.root.after(90, done)

        def done():
            self.busy = False
            then()
        self.root.after(170, to_white)

    def flash_refresh(self):
        if self.busy:
            return
        self._flash(self._draw if self.doc else self.paint_empty)

    def _draw(self):
        c = self.canvas
        c.delete("all")
        c.config(bg=self.paper())
        scroll = self.offset if self.s["view"] == "width" else 0
        for r, x, y in self.placed:
            c.create_image(x, y - scroll, image=r.get_photo(), anchor="nw")
        self._draw_search_hits(scroll)
        # static position marker for fit-width (no animation, just a bar)
        if self.s["view"] == "width" and self.placed:
            cw, ch = self._canvas_size()
            height = self.placed[0][0].img.height
            if height > ch:
                top = ch * self.offset / height
                bar = max(20, ch * ch / height)
                c.create_rectangle(cw - 6, top, cw, min(ch, top + bar), fill=self.ink(), outline="")
        if self.fullscreen:
            self._draw_reading_info()
        self.update_status()

    # -- welcome screen (no document open) --------------------------------------

    def _welcome_fonts(self):
        if not hasattr(self, "_wf"):
            F = tkfont.Font
            self._wf = {
                "title": F(family="Segoe UI Semibold", size=26),
                "tagline": F(family="Segoe UI", size=12),
                "button": F(family="Segoe UI Semibold", size=12),
                "label": F(family="Segoe UI Semibold", size=9),
                "name": F(family="Segoe UI Semibold", size=11),
                "small": F(family="Segoe UI", size=9),
                "link": F(family="Segoe UI", size=9, underline=True),
            }
        return self._wf

    def _welcome_icon(self, size):
        if getattr(self, "_wicon_size", None) != size:
            try:
                img = Image.open(resource("inkreader.ico")).convert("RGBA")
                self._wicon = ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))
            except Exception:
                self._wicon = None
            self._wicon_size = size
        return self._wicon

    def _round_rect(self, x0, y0, x1, y1, r, **kw):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    @staticmethod
    def _elide(font, text, width, middle=False):
        if font.measure(text) <= width:
            return text
        dots = "…"
        lo, hi = 0, len(text)
        while lo < hi:   # longest prefix (or prefix+suffix) that fits
            mid = (lo + hi + 1) // 2
            cand = (text[:mid // 2] + dots + text[len(text) - mid // 2:]) if middle else text[:mid] + dots
            if font.measure(cand) <= width:
                lo = mid
            else:
                hi = mid - 1
        return (text[:lo // 2] + dots + text[len(text) - lo // 2:]) if middle else text[:lo] + dots

    def paint_empty(self):
        """White welcome page: icon, title, Open button, recent documents, tips."""
        c = self.canvas
        c.delete("all")
        W = WELCOME
        c.config(bg=W["bg"], cursor="")
        cw, ch = self._canvas_size()
        if cw < 240 or ch < 240:
            return
        f = self._welcome_fonts()
        ls = {k: v.metrics("linespace") for k, v in f.items()}
        col = min(660, cw - 64)
        left, right, cx = (cw - col) // 2, (cw + col) // 2, cw // 2
        icon_px = 72 if ch > 640 else 48
        row_h = ls["name"] + ls["small"] + 26
        header_h = icon_px + 18 + ls["title"] + 6 + ls["tagline"] + 30 + 50 + 14 + ls["small"]
        footer_h = 2 * ls["small"] + 46
        recent = [p for p in self.s["recent"] if os.path.exists(p)]
        room = ch - header_h - footer_h - 60 - (ls["label"] + 14)
        recent = recent[:max(0, min(6, room // row_h))]
        self._empty_recent = recent
        total = header_h + ((44 + ls["label"] + 10 + len(recent) * row_h) if recent else 0)
        y = max(24, (ch - footer_h - total) // 2)

        icon = self._welcome_icon(icon_px)
        if icon:
            c.create_image(cx, y, image=icon, anchor="n")
        y += icon_px + 18
        c.create_text(cx, y, text=APP_NAME, font=f["title"], fill=W["fg"], anchor="n")
        y += ls["title"] + 6
        c.create_text(cx, y, text="Calm reading for e-ink screens and tired eyes",
                      font=f["tagline"], fill=W["muted"], anchor="n")
        y += ls["tagline"] + 30

        bw, bh = 280, 50
        self._round_rect(cx - bw // 2, y, cx + bw // 2, y + bh, 14, fill=W["btn"], outline="",
                         tags=("open_btn", "open_btn_bg"))
        c.create_text(cx, y + bh // 2, text="Open a document", font=f["button"], fill="#ffffff", tags="open_btn")
        y += bh + 14
        c.create_text(cx, y, text="Ctrl+O     ·     PDF, EPUB, MOBI, FB2, XPS, CBZ",
                      font=f["small"], fill=W["faint"], anchor="n")
        y += ls["small"]

        if recent:
            y += 44
            c.create_text(left + 12, y, text="RECENT", font=f["label"], fill=W["muted"], anchor="nw")
            y += ls["label"] + 10
            c.create_line(left + 12, y, right - 12, y, fill=W["line"])
            positions = self.s["positions"]
            for i, path in enumerate(recent):
                tags = (f"recent:{i}", f"row{i}")
                c.create_rectangle(left, y + 1, right, y + row_h, fill=W["bg"], outline="",
                                   tags=tags + (f"rowbg{i}",))
                mid = y + row_h // 2
                ext = (os.path.splitext(path)[1][1:].upper() or "FILE")[:4]
                self._round_rect(left + 12, mid - 13, left + 60, mid + 13, 7, fill=W["bg"], outline=W["badge"],
                                 tags=tags + (f"badge{i}",))
                c.create_text(left + 36, mid, text=ext, font=f["label"], fill=W["muted"], tags=tags)
                tx = left + 78
                pos = positions.get(path)
                page_txt = f"Page {int(pos[0]) + 1}" if pos else ""
                text_w = right - tx - 110
                c.create_text(tx, mid - 1, text=self._elide(f["name"], os.path.basename(path), text_w),
                              font=f["name"], fill=W["fg"], anchor="sw", tags=tags)
                c.create_text(tx, mid + 1, text=self._elide(f["small"], os.path.dirname(path), text_w, True),
                              font=f["small"], fill=W["muted"], anchor="nw", tags=tags)
                c.create_text(right - 44, mid, text=page_txt, font=f["small"], fill=W["muted"], anchor="e",
                              tags=tags)
                c.create_text(right - 16, mid, text="✕", font=f["small"], fill=W["muted"], state="hidden",
                              tags=tags + (f"remove:{i}", f"x{i}"))
                y += row_h
                c.create_line(left + 12, y, right - 12, y, fill=W["line"])

        fy = ch - 22
        c.create_text(cx, fy - ls["small"] - 10,
                      text="F11  reading mode     ·     I  paper style     ·     ?  all shortcuts",
                      font=f["small"], fill=W["faint"], anchor="s")
        sep = "   ·   "
        parts = [(f"Version {VERSION}{sep}Free and open source (AGPL){sep}", None),
                 ("Source on GitHub", "link_src")]
        x = cx - sum(f["small"].measure(t) for t, _ in parts) // 2
        for text, tag in parts:
            c.create_text(x, fy, text=text, font=f["small"], anchor="sw",
                          fill=W["muted"] if tag else W["faint"], tags=(tag,) if tag else ())
            x += f["small"].measure(text)
        self._bind_welcome_hover(len(recent))

    def _bind_welcome_hover(self, rows):
        c, W = self.canvas, WELCOME

        def hand(on):
            c.config(cursor="hand2" if on else "")
        c.tag_bind("open_btn", "<Enter>", lambda e: (c.itemconfig("open_btn_bg", fill=W["btn_hover"]), hand(True)))
        c.tag_bind("open_btn", "<Leave>", lambda e: (c.itemconfig("open_btn_bg", fill=W["btn"]), hand(False)))
        c.tag_bind("link_src", "<Enter>", lambda e: (c.itemconfig("link_src", font=self._wf["link"], fill=W["fg"]),
                                                     hand(True)))
        c.tag_bind("link_src", "<Leave>", lambda e: (c.itemconfig("link_src", font=self._wf["small"],
                                                                  fill=W["muted"]), hand(False)))
        for i in range(rows):
            def enter(e, i=i):
                c.itemconfig(f"rowbg{i}", fill=W["hover"])
                c.itemconfig(f"badge{i}", fill=W["hover"])
                c.itemconfig(f"x{i}", state="normal")
                hand(True)

            def leave(e, i=i):
                c.itemconfig(f"rowbg{i}", fill=W["bg"])
                c.itemconfig(f"badge{i}", fill=W["bg"])
                c.itemconfig(f"x{i}", state="hidden", fill=W["muted"])
                hand(False)
            c.tag_bind(f"row{i}", "<Enter>", enter)
            c.tag_bind(f"row{i}", "<Leave>", leave)
            c.tag_bind(f"x{i}", "<Enter>", lambda e, i=i: c.itemconfig(f"x{i}", fill=W["fg"]))

    def _welcome_click(self):
        tags = set()
        for item in self.canvas.find_withtag("current"):
            tags.update(self.canvas.gettags(item))
        for t in tags:
            if t.startswith("remove:"):
                path = self._empty_recent[int(t.split(":")[1])]
                self.s["recent"] = [p for p in self.s["recent"] if p != path]
                self.s.save()
                self.paint_empty()
                return
        for t in tags:
            if t.startswith("recent:"):
                self.open(self._empty_recent[int(t.split(":")[1])])
                return
        if "open_btn" in tags:
            self.open_dialog()
        elif "link_src" in tags:
            webbrowser.open(SOURCE_URL)

    def update_status(self):
        if not self.doc:
            self.page_var.set("")
            self.total_label.config(text="")
            self.status.config(text="  No document open")
            return
        n = self.doc.page_count
        shown = [r.pno for r, _, _ in self.placed] or [self.page]
        label = f"{shown[0] + 1}" if len(shown) == 1 else f"{shown[0] + 1}-{shown[-1] + 1}"
        if self.root.focus_get() is not self.page_entry:
            self.page_var.set(label)
        self.total_label.config(text=f"/ {n}")
        self.b_view.config(text=self.view_label())
        self._set_toggle(self.b_crop, self.s["crop"])
        pct = int(round(100 * (shown[-1] + 1) / n))
        parts = [os.path.basename(self.doc.path), f"Page {label} of {n}", f"{pct}%",
                 self.view_label(), MODE_SHORT.get(self.s["mode"], ""), f"Bold {self.s['bold']}"]
        if self.s["subpixel"] != "off" and self.s["mode"] == "gray":
            parts.append("Sharp LCD text")
        if self.s["crop"]:
            parts.append("Cropped")
        if self.s["rotation"]:
            parts.append(f"Rotated {self.s['rotation']}")
        parts.append(PAPERS.get(self.s["page"], PAPERS["warm"])[0].split(" (")[0])
        parts.append(f"Quality {self.s['quality']}x")
        if self.doc.reflowable:
            parts.append(f"Font {self.s['font_size']}")
        self.status.config(text="   ·   ".join(parts))

    def view_label(self):
        if self.s["view"] == "width" and self.s["width_pct"] < 100:
            return f"Width {self.s['width_pct']}%"
        return VIEW_LABEL[self.s["view"]]

    def note(self, text):
        """Show a short message for a few seconds (status bar, or on the page in reading mode)."""
        self.status.config(text="   " + text)
        self._later("note", 2500, self.update_status)
        if self.fullscreen:
            self._toast(text)

    def _toast(self, text, keep_time=False):
        c = self.canvas
        c.delete("toast")
        if not keep_time:
            self.toast_text, self.toast_until = text, time.monotonic() + 2.5
            self._later("toast", 2600, lambda: c.delete("toast"))
        cw, ch = self._canvas_size()
        pal = self.pal()
        t = c.create_text(cw // 2, ch - 50, text=text, font=self.font_small, fill=pal["fg"], tags="toast")
        x0, y0, x1, y1 = c.bbox(t)
        c.tag_lower(c.create_rectangle(x0 - 14, y0 - 7, x1 + 14, y1 + 7, fill=pal["bg"], outline=pal["fg"],
                                       tags="toast"), t)

    # -- prefetch -------------------------------------------------------------

    def schedule_prefetch(self):
        if not self.doc:
            return
        n, step = self.doc.page_count, self.pages_per_view()
        nxt = [p for p in range(self.page + step, self.page + 2 * step) if p < n]
        prv = [p for p in range(self.page - step, self.page) if p >= 0]
        self.prefetch_queue = nxt + prv
        self._later("prefetch", 80, self._prefetch_step)

    def _prefetch_step(self):
        """Rasterize upcoming pages one at a time (fast); the worker thread does the heavy
        image processing while the UI stays responsive. Finished pages get their Tk image here."""
        if not self.doc or not self.render_args:
            return
        if self.prefetch_queue:
            p = self.prefetch_queue.pop(0)
            try:
                self.doc.prefetch(p, *self.render_args)
            except Exception:
                pass
        for res in self.doc.collect():
            res.get_photo()
        if self.prefetch_queue or self.doc.pending:
            self._later("prefetch", 40, self._prefetch_step)

    # -- navigation -----------------------------------------------------------

    def goto(self, pno, at_end=False, focus=None):
        if not self.doc or self.busy:
            return
        pno = max(0, min(self.doc.page_count - 1, int(pno)))
        self.page = pno
        self.offset = 0.0
        self.pending_offset = ("end",) if at_end else None
        self.turns += 1
        self.show(flash_ok=True, focus=focus)

    def _can_scroll(self, direction):
        if self.s["view"] != "width" or not self.placed:
            return False
        height = self.placed[0][0].img.height
        ch = self._canvas_size()[1]
        if height <= ch:
            return False
        return self.offset < height - ch - 0.5 if direction > 0 else self.offset > 0.5

    def _scroll(self, direction):
        height = self.placed[0][0].img.height
        ch = self._canvas_size()[1]
        step = ch * (1 - self.s["overlap"] / 100.0)
        self.offset = max(0.0, min(float(height - ch), self.offset + direction * step))
        self.turns += 1
        self.paint(flash_ok=True)
        self.save_position()

    def next_screen(self):
        if not self.doc or self.busy:
            return
        if self._can_scroll(+1):
            self._scroll(+1)
            return
        nxt = self.page + self.pages_per_view()
        if nxt < self.doc.page_count:
            self.goto(nxt)
        else:
            self.note("End of document")

    def prev_screen(self):
        if not self.doc or self.busy:
            return
        if self._can_scroll(-1):
            self._scroll(-1)
            return
        if self.page > 0:
            self.goto(self.page - self.pages_per_view(), at_end=True)
        else:
            self.note("Start of document")

    def focus_page_entry(self):
        if not self.doc:
            return
        if not self.s["show_toolbar"]:
            p = simpledialog.askinteger(APP_NAME, f"Go to page (1-{self.doc.page_count}):",
                                        parent=self.root, minvalue=1, maxvalue=self.doc.page_count)
            if p:
                self.goto(p - 1)
            return
        self.page_entry.focus_set()
        self.page_entry.select_range(0, "end")

    def _entry_go(self, _event=None):
        txt = self.page_var.get().strip().split("-")[0]
        self.canvas.focus_set()
        try:
            self.goto(int(txt) - 1)
        except ValueError:
            self.update_status()

    # -- mouse ----------------------------------------------------------------

    def _hit(self, x, y):
        scroll = self.offset if self.s["view"] == "width" else 0
        for r, px, py in self.placed:
            py -= scroll
            if px <= x < px + r.img.width and py <= y < py + r.img.height:
                return r.pno, pymupdf.Point(x - px + r.ox, y - py + r.oy) * ~r.mat
        return None, None

    def _follow_link(self, x, y):
        pno, pt = self._hit(x, y)
        if pno is None:
            return False
        try:
            links = self.doc.doc[pno].get_links()
        except Exception:
            return False
        for ln in links:
            if pt not in pymupdf.Rect(ln.get("from", (0, 0, 0, 0))):
                continue
            kind = ln.get("kind")
            if kind in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED) and ln.get("page", -1) >= 0:
                self.goto(ln["page"])
                return True
            if kind == pymupdf.LINK_URI and ln.get("uri"):
                if messagebox.askyesno(APP_NAME, f"Open this link in your web browser?\n\n{ln['uri']}",
                                       parent=self.root):
                    webbrowser.open(ln["uri"])
                return True
        return False

    def on_click(self, e):
        self.canvas.focus_set()
        if not self.doc:
            self._welcome_click()
            return
        if self.overlay:   # first click on the page just tucks the toolbar away
            self._hide_overlay()
            return
        if self.busy or self._follow_link(e.x, e.y):
            return
        cw, ch = self._canvas_size()
        if e.y < ch * 0.07 and cw * 0.3 < e.x < cw * 0.7:
            self.toggle_toolbar()
        elif e.x < cw * self.s["tap_prev"] / 100.0:
            self.prev_screen()
        else:
            self.next_screen()

    def on_wheel(self, e):
        now = time.monotonic()
        if now - self.last_wheel < 0.25:
            return
        self.last_wheel = now
        if e.delta < 0:
            self.next_screen()
        else:
            self.prev_screen()

    def on_context(self, e):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Open...", command=self.open_dialog)
        if self.doc:
            m.add_command(label="Contents", command=self.show_toc)
            m.add_command(label="Go to page...", command=self.focus_page_entry)
            m.add_command(label="Find...", command=self.show_find)
            m.add_separator()
            self._menu_view = tk.StringVar(value=self.s["view"])
            for val, label in VIEWS:
                m.add_radiobutton(label=label, value=val, variable=self._menu_view,
                                  command=lambda v=val: self.set_view(v))
            self._menu_crop = tk.BooleanVar(value=self.s["crop"])
            m.add_checkbutton(label="Crop margins", variable=self._menu_crop, command=self.toggle_crop)
            m.add_command(label="Zoom in   +", command=lambda: self.zoom(+1))
            m.add_command(label="Zoom out   -", command=lambda: self.zoom(-1))
            m.add_command(label="Full width   Ctrl+0", command=self.zoom_full_width)
            m.add_command(label="Rotate 90°", command=self.rotate)
            paper_menu = tk.Menu(m, tearoff=0)
            self._menu_paper = tk.StringVar(value=self.s["page"])
            for val, (label, _p, _i) in PAPERS.items():
                paper_menu.add_radiobutton(label=label, value=val, variable=self._menu_paper,
                                           command=lambda v=val: self._set_setting("page", v))
            m.add_cascade(label="Paper", menu=paper_menu)
            self._menu_inv = tk.BooleanVar(value=self.night)
            m.add_checkbutton(label="Dark app frame", variable=self._menu_inv, command=self.toggle_theme)
        m.add_separator()
        m.add_command(label="Display settings...", command=self.show_display)
        m.add_command(label="Refresh screen   F5", command=self.flash_refresh)
        m.add_command(label="Hide toolbar" if self.s["show_toolbar"] else "Show toolbar",
                      command=self.toggle_toolbar)
        m.add_command(label="Exit reading mode   Esc" if self.fullscreen else "Reading mode   F11",
                      command=self.toggle_fullscreen)
        if self.fullscreen:
            m.add_command(label=("Hide" if self.s["reading_info"] else "Show") + " page number   H",
                          command=self.toggle_reading_info)
        m.add_separator()
        m.add_command(label="Keyboard shortcuts and About", command=self.show_help)
        m.tk_popup(e.x_root, e.y_root)

    # -- view commands --------------------------------------------------------

    def set_view(self, view):
        self.s["view"] = view
        self.offset = 0.0
        self.pending_offset = None
        self.show()

    def cycle_view(self):
        order = [v for v, _ in VIEWS]
        self.set_view(order[(order.index(self.s["view"]) + 1) % len(order)])
        self.note(VIEW_LABEL[self.s["view"]])

    def toggle_crop(self):
        self.s["crop"] = not self.s["crop"]
        self.refresh_view()
        self.note("Margins cropped" if self.s["crop"] else "Full page")

    def rotate(self):
        self.s["rotation"] = (self.s["rotation"] + 90) % 360
        self.offset = 0.0
        self.show()

    def toggle_theme(self):
        self._set_setting("theme", "day" if self.night else "night")
        self.note("Dark app frame" if self.night else "Light app frame")

    def cycle_paper(self):
        order = list(PAPERS)
        cur = self.s["page"] if self.s["page"] in order else order[0]
        self._set_setting("page", order[(order.index(cur) + 1) % len(order)])
        self.note("Paper: " + PAPERS[self.s["page"]][0])

    def cycle_quality(self):
        self._set_setting("quality", int(self.s["quality"]) % 3 + 1)
        self.note("Quality: " + dict(QUALITIES)[self.s["quality"]])

    def cycle_bold(self):
        self.s["bold"] = (int(self.s["bold"]) + 1) % 4
        self.refresh_view()
        self.note(f"Bold text: {self.s['bold']}")

    def cycle_mode(self):
        order = [m for m, _ in MODES]
        cur = self.s["mode"] if self.s["mode"] in order else order[0]
        self.s["mode"] = order[(order.index(cur) + 1) % len(order)]
        self.refresh_view()
        self.note(dict(MODES)[self.s["mode"]])

    def change_darkness(self, delta):
        self.s["darkness"] = round(max(1.0, min(3.0, self.s["darkness"] + delta)), 1)
        self.refresh_view()
        self.note(f"Text darkness: {self.s['darkness']}")

    def on_ctrl_wheel(self, e):
        now = time.monotonic()
        if now - self.last_wheel < 0.2:
            return "break"
        self.last_wheel = now
        self.zoom(+1 if e.delta > 0 else -1)
        return "break"

    def zoom(self, direction):
        """Acrobat-style zoom: Fit page -> wider Fit width steps (10% of screen) -> full width."""
        if not self.doc:
            return
        if self.doc.reflowable:
            self.change_font(direction)
            return
        cw, ch = self._canvas_size()
        s = self.s
        if s["view"] in ("page", "two"):
            if direction < 0:
                self.note("Whole page already shown")
                return
            cur = self.placed[0][0].img.width * 100.0 / cw if self.placed else 40
            s["view"], s["width_pct"] = "width", min(100, (int(cur) // 10 + 1) * 10)
        else:
            pct = s["width_pct"] + 10 * direction
            if pct > 100:
                self.note("Full width")
                return
            if direction < 0 and self.placed:
                r = self.placed[0][0]
                fit_page_pct = min(cw, ch * r.img.width / max(1, r.img.height)) * 100.0 / cw
                if pct <= fit_page_pct:
                    self.set_view("page")
                    self.note("Fit page")
                    return
            s["width_pct"] = max(20, pct)
        self.refresh_view()
        self.note(f"Width {s['width_pct']}%")

    def zoom_full_width(self):
        if not self.doc:
            return
        self.s["view"], self.s["width_pct"] = "width", 100
        self.refresh_view()
        self.note("Full width")

    def change_font(self, delta):
        if not self.doc:
            return
        if not self.doc.reflowable:
            self.note("Font size applies to e-books. For PDFs use Crop or Fit width (W).")
            return
        self.s["font_size"] = max(6, min(40, int(self.s["font_size"]) + delta))
        self.show()
        self.note(f"Font size: {self.s['font_size']}")

    def toggle_toolbar(self):
        if self.fullscreen:
            if self.overlay:
                self._hide_overlay()
            else:
                self._show_overlay()
            return
        self.s["show_toolbar"] = not self.s["show_toolbar"]
        self._layout_chrome()
        self.canvas.focus_set()

    # -- reading mode ---------------------------------------------------------

    def toggle_fullscreen(self):
        self.set_reading_mode(not self.fullscreen)

    def set_reading_mode(self, on):
        if on == self.fullscreen:
            return
        self.fullscreen = on
        if on:   # reading mode keeps its own layout (e.g. two pages on a wide screen)
            self.normal_view = self.s["view"]
            if self.s["reading_view"] in VIEW_LABEL:
                self.s["view"] = self.s["reading_view"]
            self.hint_until = time.monotonic() + 3.5
            self._later("hint", 3600, lambda: self.doc and not self.busy and self._draw())
        else:
            self.s["reading_view"] = self.s["view"]
            if self.normal_view:
                self.s["view"] = self.normal_view
            self.canvas.config(cursor="")
        self.root.attributes("-fullscreen", on)
        self.b_full.config(text="Exit reading mode" if on else "Reading mode")
        self._layout_chrome()
        self.canvas.focus_set()
        self._arm_cursor_hide()
        self.refresh_view()

    def _show_overlay(self):
        """Float the toolbar over the top of the page (no relayout, no re-render)."""
        if not self.fullscreen or self.overlay:
            return
        self.overlay = True
        self.toolbar.place(x=0, y=0, relwidth=1)
        self.toolbar.lift()
        self.toolbar.update_idletasks()
        self.rule.place(x=0, y=self.toolbar.winfo_reqheight(), relwidth=1)
        self.rule.lift()
        self.canvas.config(cursor="")
        self.update_status()

    def _hide_overlay(self):
        if not self.overlay:
            return
        self.overlay = False
        self.toolbar.place_forget()
        self.rule.place_forget()
        self.canvas.focus_set()
        self._arm_cursor_hide()

    def _arm_cursor_hide(self):
        def hide():
            if self.fullscreen and not self.overlay:
                self.canvas.config(cursor="none")
        if self.fullscreen:
            self._later("cursor", 1800, hide)

    def on_motion(self, e):
        if not self.fullscreen:
            return
        if self.canvas.cget("cursor"):
            self.canvas.config(cursor="")
        self._arm_cursor_hide()
        if e.y <= 6:
            self._show_overlay()
        elif self.overlay and e.y > self.toolbar.winfo_height() + 60:
            self._hide_overlay()

    def toggle_reading_info(self):
        self.s["reading_info"] = not self.s["reading_info"]
        if self.doc:
            self._draw()

    def _draw_reading_info(self):
        c = self.canvas
        cw, ch = self._canvas_size()
        pal = self.pal()
        if self.s["reading_info"] and self.doc:
            n = self.doc.page_count
            shown = [r.pno for r, _, _ in self.placed] or [self.page]
            label = f"{shown[0] + 1}" if len(shown) == 1 else f"{shown[0] + 1}-{shown[-1] + 1}"
            text = f"{label} / {n}   {int(round(100 * (shown[-1] + 1) / n))}%"
            t = c.create_text(cw - 14, ch - 10, text=text, anchor="se", font=self.font_small, fill=pal["dim"])
            x0, y0, x1, y1 = c.bbox(t)
            c.tag_lower(c.create_rectangle(x0 - 8, y0 - 3, x1 + 8, y1 + 3, fill=pal["bg"], outline=""), t)
        if time.monotonic() < self.toast_until:
            self._toast(self.toast_text, keep_time=True)
        if time.monotonic() < self.hint_until:
            t = c.create_text(cw // 2, 40, font=self.font_small, fill=pal["fg"], justify="center",
                              text="Reading mode   ·   Esc to exit   ·   move the mouse to the top "
                                   "(or press T) for the toolbar   ·   W changes layout")
            x0, y0, x1, y1 = c.bbox(t)
            c.tag_lower(c.create_rectangle(x0 - 16, y0 - 10, x1 + 16, y1 + 10, fill=pal["bg"],
                                           outline=pal["fg"]), t)

    def escape(self):
        if self.overlay:
            self._hide_overlay()
        elif self.search:
            self.search = None
            self._draw()
        elif self.fullscreen:
            self.set_reading_mode(False)

    # -- dialogs --------------------------------------------------------------

    def _dialog(self, title):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg="white")
        win.transient(self.root)
        win.geometry(f"+{self.root.winfo_rootx() + 60}+{self.root.winfo_rooty() + 60}")
        win.bind("<Escape>", lambda e: win.destroy())
        return win

    def _dialog_btn(self, parent, text, cmd, side="left"):
        frame, b = self._bordered(parent, text, cmd, self.font_small, 12, 2)
        frame.pack(side=side, padx=4, pady=4)
        return b

    def show_toc(self):
        if not self.doc:
            return
        toc = self.doc.doc.get_toc(simple=True)
        if not toc:
            messagebox.showinfo(APP_NAME, "This document has no table of contents.", parent=self.root)
            return
        win = self._dialog("Contents")
        frame = tk.Frame(win, bg="white")
        frame.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        sb = tk.Scrollbar(frame)
        lb = tk.Listbox(frame, font=self.font_small, bg="white", fg="black", selectbackground="black",
                        selectforeground="white", activestyle="none", relief="solid", bd=1,
                        highlightthickness=0, width=60, height=24, yscrollcommand=sb.set)
        sb.config(command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        current = 0
        for i, (lvl, title, pg) in enumerate(toc):
            lb.insert("end", "      " * (lvl - 1) + f"{title}    {pg if pg > 0 else ''}")
            if 0 < pg <= self.page + 1:
                current = i
        lb.selection_set(current)
        lb.see(min(len(toc) - 1, current + 8))
        lb.see(current)

        def go(_e=None):
            sel = lb.curselection()
            if sel and toc[sel[0]][2] > 0:
                win.destroy()
                self.goto(toc[sel[0]][2] - 1)
        lb.bind("<ButtonRelease-1>", go)
        lb.bind("<Return>", go)
        bar = tk.Frame(win, bg="white")
        bar.pack(fill="x", padx=6, pady=6)
        self._dialog_btn(bar, "Close", win.destroy, side="right")
        self.finish_window(win)
        lb.focus_set()

    def show_help(self):
        win = self._dialog("Keyboard shortcuts")
        tk.Label(win, text=f"{APP_NAME} {VERSION}", font=self.font, bg="white", fg="black").pack(
            anchor="w", padx=16, pady=(12, 0))
        tk.Label(win, text=HELP_TEXT, font=("Consolas", max(9, self.s["ui_size"] - 2)), bg="white",
                 fg="black", justify="left").pack(padx=16, pady=8)
        tk.Label(win, text=f"{COPYRIGHT}\n{LICENSE_NOTICE}", font=self.font_small, bg="white", fg="black",
                 justify="left").pack(anchor="w", padx=16, pady=(0, 6))
        bar = tk.Frame(win, bg="white")
        bar.pack(fill="x", padx=12, pady=(0, 10))
        self._dialog_btn(bar, "Source code", lambda: webbrowser.open(SOURCE_URL))
        self._dialog_btn(bar, "Licence", self.open_license)
        self._dialog_btn(bar, "Third-party notices", lambda: self.open_license("THIRD_PARTY_NOTICES.md"))
        self._dialog_btn(bar, "Close", win.destroy, side="right")
        self.finish_window(win)

    def open_license(self, name="LICENSE"):
        path = resource(name)
        if os.path.exists(path):
            try:
                self._show_text_file(path, "Licence" if name == "LICENSE" else "Third-party notices")
                return
            except OSError:
                pass
        webbrowser.open(f"{SOURCE_URL}/blob/main/{name}")

    def _show_text_file(self, path, title):
        win = self._dialog(title)
        frame = tk.Frame(win, bg="white")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        sb = tk.Scrollbar(frame)
        txt = tk.Text(frame, width=82, height=34, font=("Consolas", 10), wrap="word", yscrollcommand=sb.set,
                      relief="flat", bd=0, padx=8, pady=6)
        sb.config(command=txt.yview)
        sb.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        with open(path, encoding="utf-8") as fh:
            txt.insert("1.0", fh.read())
        txt.config(state="disabled")
        self._dialog_btn(win, "Close", win.destroy, side="bottom")
        self.finish_window(win)
        p = self.pal()
        txt.config(bg=p["bg"], fg=p["fg"])

    # display settings ---------------------------------------------------------

    def _set_setting(self, key, val):
        if self.s.get(key) == val:
            return
        self.s[key] = val
        if key == "ui_size":
            self.font.configure(size=val)
            self.font_small.configure(size=max(8, val - 2))
        elif key == "show_status":
            self._layout_chrome()
        elif key == "theme":
            self.apply_theme()
            if not self.doc:
                self.paint_empty()
            self._later("apply", 50, self.refresh_view)
        elif key in ("flash_every", "overlap", "tap_prev"):
            pass
        else:
            self._later("apply", 300, self.refresh_view)

    def show_display(self):
        if self.display_win is not None and self.display_win.winfo_exists():
            self.display_win.lift()
            return
        win = self.display_win = self._dialog("Display settings")
        body = tk.Frame(win, bg="white", padx=16, pady=10)
        body.pack(fill="both", expand=True)
        left = tk.Frame(body, bg="white")
        mid = tk.Frame(body, bg="white")
        right = tk.Frame(body, bg="white")
        left.grid(row=0, column=0, sticky="n", padx=(0, 28))
        mid.grid(row=0, column=1, sticky="n", padx=(0, 28))
        right.grid(row=0, column=2, sticky="n")

        def scale(parent, key, label, lo, hi, res=1, cast=int):
            var = tk.DoubleVar(value=self.s[key])
            tk.Scale(parent, label=label, from_=lo, to=hi, resolution=res, orient="horizontal",
                     variable=var, length=330, font=self.font_small, bg="white", fg="black",
                     troughcolor="white", highlightthickness=0, bd=1, relief="flat",
                     sliderrelief="solid", activebackground="black",
                     command=lambda v, k=key: self._set_setting(k, cast(float(v)))).pack(anchor="w", pady=(4, 2))
            return var

        def check(parent, key, label):
            var = tk.BooleanVar(value=self.s[key])
            tk.Checkbutton(parent, text=label, variable=var, font=self.font_small, bg="white", fg="black",
                           activebackground="white", selectcolor="white", highlightthickness=0,
                           command=lambda: self._set_setting(key, var.get())).pack(anchor="w", pady=2)
            return var

        def radios(parent, key, title, options, cast=str):
            tk.Label(parent, text=title, font=self.font, bg="white", fg="black").pack(anchor="w", pady=(8, 0))
            var = tk.StringVar(value=str(self.s[key]))
            for val, label in options:
                tk.Radiobutton(parent, text=label, value=str(val), variable=var, font=self.font_small,
                               highlightthickness=0,
                               command=lambda: self._set_setting(key, cast(var.get()))).pack(anchor="w")
            return var

        radios(left, "page", "Paper (reading pane)", [(k, v[0]) for k, v in PAPERS.items()])
        scale(left, "paper_brightness", "Paper brightness (%) - lower if it feels bright", 60, 100)
        check(left, "keep_photos", "Night paper: keep photos in natural colors")
        radios(left, "theme", "App frame", [("night", "Dark (toolbar and surround)"), ("day", "Light")])

        radios(mid, "quality", "Resolution", QUALITIES, int)
        radios(mid, "subpixel", "Sharp LCD text (subpixel)",
               [("rgb", "On - RGB (most monitors)"), ("bgr", "On - BGR panels"),
                ("off", "Off (e-ink, rotated screens)")])
        scale(mid, "sharpen", "Sharpen (when subpixel is off)", 0, 3)
        scale(mid, "width_pct", "Fit width: page width (% of screen)", 30, 100, 10)
        radios(mid, "mode", "Rendering", MODES)
        tk.Label(mid, text="Subpixel text is used with Grayscale.", font=self.font_small,
                 bg="white", fg="black").pack(anchor="w", pady=(4, 0))

        tk.Label(right, text="Text", font=self.font, bg="white", fg="black").pack(anchor="w")
        scale(right, "darkness", "Text darkness", 1.0, 3.0, 0.1, float)
        scale(right, "bold", "Bolder text (0 = off)", 0, 3)
        tk.Label(right, text="Contrast", font=self.font, bg="white", fg="black").pack(anchor="w", pady=(10, 0))
        scale(right, "threshold", "Black & white threshold", 40, 250)
        if self.doc and self.doc.reflowable:
            scale(right, "font_size", "E-book font size", 6, 40)
        scale(right, "white_point", "Clean background (lower = whiter paper)", 150, 255)
        scale(right, "black_point", "Deepen blacks", 0, 120)
        tk.Label(right, text="Behaviour", font=self.font, bg="white", fg="black").pack(anchor="w", pady=(10, 0))
        scale(right, "flash_every", "Full refresh flash every N turns (0 = off)", 0, 20)
        scale(right, "overlap", "Fit-width overlap between screens (%)", 0, 40)
        scale(right, "tap_prev", "Left click zone for 'previous' (% width)", 10, 50)
        scale(right, "ui_size", "Toolbar text size", 9, 24)
        check(right, "show_status", "Show status bar")

        bar = tk.Frame(win, bg="white")
        bar.pack(fill="x", padx=10, pady=(0, 10))

        def reset():
            for k in DISPLAY_KEYS:
                self.s[k] = DEFAULTS[k]
            win.destroy()
            self.refresh_view()
            self.show_display()
        self._dialog_btn(bar, "Reset to defaults", reset)
        self._dialog_btn(bar, "Close", win.destroy, side="right")
        self.finish_window(win)

    # find ---------------------------------------------------------------------

    def show_find(self):
        if not self.doc:
            return
        if self.find_win is not None and self.find_win.winfo_exists():
            self.find_win.lift()
            self._find_entry.focus_set()
            self._find_entry.select_range(0, "end")
            return
        win = self.find_win = self._dialog("Find")
        row = tk.Frame(win, bg="white")
        row.pack(padx=10, pady=(10, 4))
        var = tk.StringVar(value=self.search["term"] if self.search else "")
        e = self._find_entry = tk.Entry(row, textvariable=var, font=self.font, width=26, relief="solid",
                                        bd=1, bg="white", fg="black", insertbackground="black",
                                        highlightthickness=0)
        e.pack(side="left", ipady=3, padx=(0, 6))
        self._dialog_btn(row, "Find next", lambda: self.find_next(var.get()))
        self._find_msg = tk.Label(win, text="Enter / F3 = next match, Esc = close", font=self.font_small,
                                  bg="white", fg="black")
        self._find_msg.pack(anchor="w", padx=12, pady=(0, 10))
        e.bind("<Return>", lambda _e: self.find_next(var.get()))
        win.bind("<F3>", lambda _e: self.find_next(var.get()))
        self.finish_window(win)
        x = self.root.winfo_rootx() + self.root.winfo_width() - win.winfo_reqwidth() - 30
        win.geometry(f"+{max(0, x)}+{self.root.winfo_rooty() + 60}")
        e.focus_set()
        e.select_range(0, "end")

    def _find_note(self, text):
        if self.find_win is not None and self.find_win.winfo_exists():
            self._find_msg.config(text=text)
        self.note(text)

    def _hits(self, pno):
        hits = self.search["hits"]
        if pno not in hits:
            try:
                hits[pno] = list(self.doc.doc[pno].search_for(self.search["term"]))
            except Exception:
                hits[pno] = []
        return hits[pno]

    def find_next(self, term=None):
        if not self.doc:
            return
        if term is None:
            term = self.search["term"] if self.search else ""
        term = term.strip()
        if not term:
            return
        if not self.search or self.search["term"] != term:
            self.search = {"term": term, "hits": {}, "cur": (self.page, -1)}
        cur_p, cur_i = self.search["cur"]
        visible = [r.pno for r, _, _ in self.placed]
        if cur_p not in visible:
            cur_p, cur_i = self.page, -1
        n = self.doc.page_count
        for k in range(n + 1):
            p = (cur_p + k) % n
            hits = self._hits(p)
            start = cur_i + 1 if k == 0 else 0
            if len(hits) > start:
                self.search["cur"] = (p, start)
                if p in visible:
                    self.show(focus=hits[start])
                else:
                    self.goto(p, focus=hits[start])
                self._find_note(f"Match on page {p + 1}")
                return
            if k and k % 40 == 0:
                self._find_note(f"Searching... page {p + 1} of {n}")
                self.root.update_idletasks()
        self._find_note(f"'{term}' not found")

    def _to_canvas_rect(self, r, rect):
        q = pymupdf.Rect(rect) * r.mat
        return (q.x0 - r.ox, q.y0 - r.oy, q.x1 - r.ox, q.y1 - r.oy)

    def _draw_search_hits(self, scroll):
        if not self.search:
            return
        cur = self.search["cur"]
        for r, x, y in self.placed:
            for i, rect in enumerate(self._hits(r.pno)):
                x0, y0, x1, y1 = self._to_canvas_rect(r, rect)
                width = 4 if (r.pno, i) == cur else 2
                self.canvas.create_rectangle(x + x0 - 3, y - scroll + y0 - 3, x + x1 + 3, y - scroll + y1 + 3,
                                             outline=self.page_ink(), width=width)


def log(msg):
    """Append to %APPDATA%\\InkReader\\inkreader.log (the windowed app has no console)."""
    try:
        path = os.path.join(config_dir(), "inkreader.log")
        if os.path.exists(path) and os.path.getsize(path) > 256_000:
            os.replace(path, path + ".old")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg.rstrip() + "\n")
    except OSError:
        pass


def _install_crash_logging(root):
    import threading
    import traceback

    def fmt(exc, val, tb):
        return "".join(traceback.format_exception(exc, val, tb))
    sys.excepthook = lambda exc, val, tb: log("UNHANDLED " + fmt(exc, val, tb))
    threading.excepthook = lambda a: log(f"THREAD {a.thread.name} " + fmt(a.exc_type, a.exc_value, a.exc_traceback))
    root.report_callback_exception = lambda exc, val, tb: log("CALLBACK " + fmt(exc, val, tb))


def main():
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    log(f"start {VERSION} args={sys.argv[1:]}")
    enable_dpi_awareness()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Aexonlab.InkReader")
    except Exception:
        pass
    try:
        pymupdf.TOOLS.mupdf_display_errors(False)
        pymupdf.TOOLS.mupdf_display_warnings(False)
    except Exception:
        pass
    root = tk.Tk()
    _install_crash_logging(root)
    try:
        root.iconbitmap(default=resource("inkreader.ico"))
    except Exception:
        pass
    try:
        App(root, sys.argv[1] if len(sys.argv) > 1 else None)
        root.mainloop()
    except BaseException:
        import traceback
        log("FATAL " + traceback.format_exc())
        raise
    log("exit")


if __name__ == "__main__":
    main()
