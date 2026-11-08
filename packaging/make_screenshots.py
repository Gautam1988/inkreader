# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Gautam1988
"""Makes Microsoft Store screenshots (1366x768) of InkReader with a sample book.

The app window is placed off-screen as a tool window (no taskbar button), and only that window is
captured with PrintWindow, so nothing on the desktop appears in the images.

Usage: python packaging/make_screenshots.py   (writes packaging/store-screenshots/*.png)
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "store-screenshots")
WORK = os.path.join(ROOT, "build", "store")
W, H = 1366, 768

CHAPTERS = [
    ("The Quiet Page", [
        "There is a particular kind of attention that only arrives when nothing on the screen is moving. "
        "The page sits still, the words wait, and the reader is free to go as slowly as the sentence deserves. "
        "Most software forgets this. It scrolls when you breathe on the wheel, slides panels in from the edges, "
        "and lights every pixel as brightly as it can.",
        "A good reading tool should behave more like paper. It should hold one page steady until you ask for the "
        "next, keep its controls out of sight, and let the text be the darkest, sharpest thing in view. Comfort "
        "is not a feature to be switched on; it is the absence of small irritations that add up over an hour.",
        "This short book is a sample. It exists so you can try the reader on something pleasant: turn the pages, "
        "change the paper, and see which settings suit your eyes and your screen.",
    ]),
    ("Light and Paper", [
        "Pure white on a bright monitor is closer to a lamp than to a sheet of paper. Over a long evening it "
        "tires the eyes, and the thin gray strokes of many PDF fonts make the effort worse. A warm, slightly "
        "dimmed paper tone with near-black text keeps the contrast high while taking the glare away.",
        "Different rooms want different pages. Warm paper suits a lamp-lit desk; sepia feels like an old "
        "novel; low-glare gray is calm on a bright office screen; and night mode turns the page dark when "
        "everything else is dark too. None of these is correct for everyone, which is why they are choices.",
        "On an e-ink monitor the picture changes again. Colour disappears, every flicker costs a refresh, and "
        "crisp black text on clean white is what the panel does best.",
    ]),
    ("Turning, Not Scrolling", [
        "Scrolling asks the eye to chase a moving line. Turning a page asks nothing: the old page is replaced "
        "by the new one, and the eye simply returns to the top. On e-ink displays this matters even more, "
        "because smooth motion leaves smears and ghosts behind it.",
        "So the reader turns whole pages, or whole screens when a page is wider than the window, with a small "
        "overlap so you never lose your line. A click on the right side moves forward, a click on the left "
        "moves back, and the arrow keys, space bar and mouse wheel all do the same.",
        "When you want nothing else at all, reading mode fills the screen with the page alone. The pointer "
        "hides, the toolbar waits at the top edge, and a small counter in the corner tells you where you are.",
    ]),
    ("Margins", [
        "Printed books need wide margins for thumbs and binding. A screen needs neither, yet most PDFs keep "
        "them, and the text shrinks to make room for empty paper. Cropping those margins away lets the same "
        "page fill more of the display, so the letters grow without any change to the document.",
        "The crop is chosen across the whole book rather than page by page, so the text size stays steady "
        "as you read. A short final page does not suddenly balloon, and a wide table is never cut off.",
        "These are small decisions. Together they make a reader you can forget about, which is the point: "
        "the best tool for reading is the one that leaves you alone with the words.",
    ]),
]


def make_book(path):
    import pymupdf
    css = ("body { font-family: serif; font-size: 11.5pt; line-height: 1.5; text-align: justify; color: #111; }"
           "h1 { font-size: 22pt; font-weight: normal; margin: 0 0 18pt 0; text-align: left; }"
           "p { margin: 0 0 9pt 0; text-indent: 14pt; } p.first { text-indent: 0; }"
           ".num { font-size: 10pt; letter-spacing: 2pt; color: #666; margin-bottom: 6pt; }")
    doc = pymupdf.open()
    toc = []
    for i, (title, paras) in enumerate(CHAPTERS, 1):
        page = doc.new_page(width=432, height=648)
        body = "".join(f'<p class="{"first" if k == 0 else ""}">{t}</p>' for k, t in enumerate(paras))
        page.insert_htmlbox(pymupdf.Rect(54, 60, 378, 600),
                            f'<div class="num">CHAPTER {i}</div><h1>{title}</h1>{body}', css=css)
        page.insert_text((207, 625), str(i), fontsize=9, fontname="tiro", color=(0.4, 0.4, 0.4))
        toc.append([1, title, i])
    doc.set_toc(toc)
    doc.set_metadata({"title": "The Quiet Page", "author": "InkReader sample"})
    doc.save(path)


class BMI(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def capture_client(root, path):
    """Copy only this window's client area via PrintWindow (works off-screen; no desktop capture)."""
    from PIL import Image
    u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
    for _ in range(30):
        root.update()
        time.sleep(0.03)
    hwnd = u32.GetParent(root.winfo_id())
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc = u32.GetWindowDC(hwnd)
    mdc = g32.CreateCompatibleDC(hdc)
    bmp = g32.CreateCompatibleBitmap(hdc, w, h)
    g32.SelectObject(mdc, bmp)
    u32.PrintWindow(hwnd, mdc, 2)
    bmi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u32.ReleaseDC(hwnd, hdc)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    x, y = root.winfo_rootx() - r.left, root.winfo_rooty() - r.top
    img = img.crop((x, y, x + root.winfo_width(), y + root.winfo_height()))
    if img.size != (W, H):
        img = img.resize((W, H))
    img.save(path)
    print("wrote", path, img.size)


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    books = os.path.join(WORK, "Books")
    os.makedirs(books)
    book = os.path.join(books, "The Quiet Page.pdf")
    make_book(book)
    others = ["Notes on Thermal Hydraulics.pdf", "Field Guide to Garden Birds.epub", "Annual Report 2026.pdf"]
    for name in others:
        shutil.copy(book, os.path.join(books, name))
    recent = [book] + [os.path.join(books, n) for n in others]

    appdata = tempfile.mkdtemp(prefix="inkreader-shots-")
    os.environ["APPDATA"] = appdata
    os.makedirs(os.path.join(appdata, "InkReader"))
    with open(os.path.join(appdata, "InkReader", "settings.json"), "w", encoding="utf-8") as fh:
        json.dump({"schema": 2, "recent": recent,
                   "positions": {recent[0]: [2, 0], recent[1]: [41, 0], recent[3]: [7, 0]}}, fh)

    sys.path.insert(0, ROOT)
    import tkinter as tk
    import inkreader as ir
    ir.enable_dpi_awareness()
    root = tk.Tk()
    root.attributes("-toolwindow", True)
    real_attributes = root.attributes

    def attributes(*a):          # never really go full screen: emulate it in the off-screen window
        if a and a[0] == "-fullscreen" and len(a) > 1:
            return None
        return real_attributes(*a)
    root.attributes = attributes
    root.geometry(f"{W}x{H}+-8000+0")
    # show a neutral folder in the Recent list instead of this machine's real path
    real_elide = ir.App._elide
    ir.App._elide = staticmethod(lambda font, text, width, middle=False:
                                 real_elide(font, text.replace(books, "D:\\Books"), width, middle))
    app = ir.App(root, None)
    os.makedirs(OUT, exist_ok=True)

    capture_client(root, os.path.join(OUT, "1-welcome.png"))

    app.open(book)
    app.set_view("two")
    capture_client(root, os.path.join(OUT, "2-two-pages-warm-paper.png"))

    app.goto(2)
    app.set_reading_mode(True)
    app.hint_until = time.monotonic() + 30
    capture_client(root, os.path.join(OUT, "3-reading-mode.png"))
    app.set_reading_mode(False)

    app._set_setting("page", "night")
    app.set_view("two")
    app.goto(0)
    capture_client(root, os.path.join(OUT, "4-night-paper.png"))

    app._set_setting("page", "sepia")
    capture_client(root, os.path.join(OUT, "5-sepia.png"))
    app.quit()
    shutil.rmtree(appdata, ignore_errors=True)


if __name__ == "__main__":
    main()
