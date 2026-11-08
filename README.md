# InkReader

**A calm PDF and e-book reader for Windows, built for e-ink monitors and tired eyes.**

Ordinary readers like Acrobat scroll smoothly, animate, and draw thin gray text on glaring white. On an e-ink monitor (Dasung Paperlike, Boox Mira, an e-ink tablet used as a second screen) that causes smearing, ghosting and faint pages. On a normal LCD it tires your eyes. InkReader turns whole pages at a time, shows dark, sharp text on soft warm paper, and has a full-screen reading mode with nothing else on screen.

Free and open source under the [GNU AGPL v3](LICENSE).

## Download

Get **`InkReader.exe`** from the [latest release](https://github.com/Gautam1988/inkreader/releases/latest). It is a single portable file for Windows 10 or 11, with no install and no Python needed.

> **Windows may warn you the first time** ("Windows protected your PC"). This happens because the app isn't code-signed yet. Click **More info → Run anyway**. You can also build it yourself from this source (see below).

## Support InkReader ♥

InkReader is free and always will be. If it makes your reading more comfortable, please consider [**sponsoring it on GitHub**](https://github.com/sponsors/Gautam1988). Sponsorships fund:

- **Code signing**, so Windows stops warning about an unknown app
- **Testing on real e-ink monitors** (Dasung, Boox Mira and others)
- New features and continued maintenance

Starring the repository and sharing it with someone who reads a lot help too.

## Run it

- Double-click it, then click anywhere or press **Ctrl+O**.
- To open PDFs with it from Explorer, right-click a PDF, choose **Open with → Choose another app → More apps → Look for another app on this PC**, and pick `InkReader.exe`. Tick "Always use" if you want it as the default.
- Drag the window onto your e-ink monitor and press **F** for full screen.

Supported formats: PDF, EPUB, MOBI, FB2, XPS, CBZ.

## Features

| Feature | What it does |
|---|---|
| **Soft paper** (I / Paper button) | The default page is black text on warm off-white paper (#F1EAD8) instead of glaring pure white. You can also choose Soft white, Sepia, Low-glare gray, Pure white (best on e-ink) or Night (white on black). The *Paper brightness* setting dims the paper further. |
| **Reading mode** (F11 / F / button) | Full screen with only the page, which fills the **whole screen width** by default (− / + to narrow or widen it). The pointer hides when idle and a small page counter sits in the corner (H hides it). Move the mouse to the top edge or press T to float the toolbar over the page, and Esc to leave. Reading mode remembers its own layout (e.g. Two pages) and reopens in reading mode if you closed it that way. |
| **Dark app frame** (U) | The toolbar, dialogs, title bar and the area around the page are black, so the only bright thing on screen is the page itself. |
| **Sharp LCD text** | Subpixel text rendering, like Windows ClearType: each pixel's red, green and blue stripes get their own sample, which gives 3× horizontal detail. FreeType's LCD filter keeps colour fringes down. It is on by default (RGB); in Display settings, set **BGR** for those panels or **Off** for e-ink and rotated screens. It is used with the Grayscale rendering mode. |
| **High resolution** (Q) | Pages are drawn at 2× (or 3×) the screen resolution and scaled down with a sharp filter. Bold text is applied at the higher resolution, which gives cleaner, more even strokes. The image processing runs on a background thread, so upcoming pages are prepared while you read. |
| **Zoom** (+ / −, Ctrl+wheel, Ctrl+0) | Steps from Fit page through wider widths (in 10% steps of the screen) to full screen width. |
| Page-at-a-time turning | No smooth scrolling. Clicks, arrow keys and the mouse wheel move a full page. |
| **Fit width** mode (W) | Pages wider than the screen are read in whole-screen steps, with a small overlap so you don't lose your line. |
| Crop margins (C) | Removes white margins so the text gets larger. The crop stays the same from page to page, so the text size doesn't jump. |
| 16 gray levels (M) | Matches what most e-ink panels can show, which avoids blotchy dithering by the panel. |
| Black & white mode | Pure black-or-white output, which gives the sharpest text and the fastest refresh. |
| Dithered mode | Gives better photos and diagrams in black and white. |
| Text darkness `[` `]` | Darkens light or gray text without making the background gray. |
| Bold text (B) | Thickens thin font strokes. There are 4 levels. |
| Clean background | Turns off-white or yellowed scans into pure white paper. |
| Full refresh (F5) | Flashes the screen black then white to clear ghosting. In Display settings you can make it happen automatically every N page turns. |
| E-book font size `+` `-` | EPUB, MOBI and FB2 books re-flow to the screen shape. Your reading position is kept. |
| Big click zones | Clicking the left third goes back and clicking anywhere else goes forward. You can change the split in settings. |
| Remembers everything | Remembers the last page of every document, plus your display settings, window position and recent files. |

Also: contents (Ctrl+T), find with highlighted matches (Ctrl+F / F3), clickable links, go to page (Ctrl+G), rotate (R), two-page view, and a right-click menu with every command. Press **?** in the app for all shortcuts.

Settings are stored in `%APPDATA%\InkReader\settings.json`. Errors and exits are logged to `inkreader.log` in the same folder.

## Building from source

You need Python 3.12 on Windows.

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

That creates a virtual environment, installs the pinned dependencies from `requirements.txt` and builds `dist\InkReader.exe`.

To run it without building: `.venv\Scripts\python.exe inkreader.py [file.pdf]`.

It is built with [PyMuPDF](https://pymupdf.readthedocs.io/) (the MuPDF rendering engine), Pillow and Tkinter.

## License

Copyright (C) 2026 Gautam1988

InkReader is free software: you can redistribute it and/or modify it under the terms of the [GNU Affero General Public License](LICENSE) as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. It is distributed WITHOUT ANY WARRANTY.

InkReader uses PyMuPDF/MuPDF, which is itself licensed under the AGPL. Bundled components and their licences are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Contributions are welcome. By submitting a pull request, you agree that your contribution is licensed under the same AGPL v3-or-later terms.
