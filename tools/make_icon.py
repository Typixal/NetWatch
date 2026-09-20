"""Generate assets/icon.ico from the design palette.

A small mark rather than artwork: the accent square on the window ground,
matching the title bar's live indicator. Re-run if the palette changes.

    uv run python tools/make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from netwatch.ui import theme  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256)


def render(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor(theme.BG_TITLE))

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    # A bar chart of three rising marks — connections over time, the thing
    # the app actually shows.
    unit = size / 16
    p.fillRect(int(unit * 3), int(unit * 9), int(unit * 2), int(unit * 4),
               QColor(theme.TEXT_DIM))
    p.fillRect(int(unit * 7), int(unit * 6), int(unit * 2), int(unit * 7),
               QColor(theme.TEXT_DIM))
    p.fillRect(int(unit * 11), int(unit * 3), int(unit * 2), int(unit * 10),
               QColor(theme.ACCENT))
    p.end()
    return pm


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841 — QPixmap needs a QGuiApplication

    out = ROOT / "assets" / "icon.ico"
    out.parent.mkdir(parents=True, exist_ok=True)

    # Qt writes .ico from a single image; use the largest and let Windows
    # scale, which is fine for a flat mark with no fine detail.
    image: QImage = render(max(SIZES)).toImage()
    if not image.save(str(out), "ICO"):
        print("Qt could not write ICO on this build", file=sys.stderr)
        return 1

    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
