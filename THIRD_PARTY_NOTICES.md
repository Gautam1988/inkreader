# Third-party notices

InkReader is licensed under the GNU Affero General Public License v3.0 or later (see `LICENSE`).
The Windows executable bundles the components below. Each one remains under its own licence.

| Component | Version | Licence | Source |
|---|---|---|---|
| PyMuPDF (includes the MuPDF library) | 2.1 (MuPDF 1.28.6) | GNU AGPL v3.0, or a commercial licence from Artifex | https://github.com/pymupdf/PyMuPDF |
| Pillow | 13.0.0 | MIT-CMU (HPND) | https://github.com/python-pillow/Pillow |
| Python | 3.12.10 | Python Software Foundation License | https://www.python.org/downloads/source/ |
| Tcl/Tk (tkinter) | 8.6 | Tcl/Tk License (BSD-style) | https://www.tcl.tk/ |
| PyInstaller bootloader | 6.22.3 | GPL v2 or later, with the bootloader exception that allows bundling apps under any licence | https://github.com/pyinstaller/pyinstaller |

MuPDF also includes third-party libraries, such as FreeType, HarfBuzz, libjpeg, OpenJPEG, jbig2dec, lcms2, zlib and Gumbo. Their notices ship with the PyMuPDF and MuPDF source distributions linked above.

## Corresponding source

The source code of InkReader itself, including the build scripts, is at
https://github.com/Gautam1988/inkreader. Every release is tagged.

The exact versions of the libraries bundled in a release are pinned in `requirements.txt`. Their source code is at the project links above. You can rebuild the executable with `build.ps1`.
