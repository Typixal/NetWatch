"""Design tokens from the Modernist handoff, plus the app-wide stylesheet.

Values come straight from ``docs/design/project/NetWatch.dc.html`` and its
design system. Two rules carry most of the look:

* Nothing is rounded. ``border-radius`` is 0 everywhere, including inputs
  and buttons, which Qt does not default to.
* Structure is drawn with 2px borders, rows with 1px.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QFontDatabase

# — colour —

BG_APP = "#0e0d0d"       # the ground behind the window frame
BG_WINDOW = "#161514"    # the app frame itself
BG_TITLE = "#1d1b1a"     # title bar, and the selected sidebar row
BG_SIDEBAR = "#131211"
BG_ROW_SELECTED = "#201e1d"
BG_ROW_HOVER = "#1d1b1a"

BORDER_HARD = "#383533"  # 2px structural divisions
BORDER_SOFT = "#2a2726"  # 1px row separators
BORDER_CTRL = "#4a4644"  # control outlines

TEXT = "#f3f2f2"
TEXT_DIM = "#bab6b6"
TEXT_MUTED = "#8d8886"
TEXT_FAINT = "#6d6866"
INACTIVE = "#5c5856"

ACCENT = "#ec3013"
ACCENT_HOVER = "#f2694f"

# Fills for the graphs, as QColor so painters can use them directly.
ACCENT_FILL = QColor(236, 48, 19, 41)       # rgba(236,48,19,.16)
ACCENT_FILL_SOFT = QColor(236, 48, 19, 18)  # rgba(236,48,19,.07) row wash
NEUTRAL_STROKE = QColor(186, 182, 182)
NEUTRAL_FILL = QColor(186, 182, 182, 31)
MUTED_STROKE = QColor(92, 88, 86)
MUTED_FILL = QColor(92, 88, 86, 36)

#: Status dot / label colours, keyed by the psutil status string.
STATUS_ESTABLISHED = TEXT
STATUS_OTHER = TEXT_MUTED

# — type —

FONT_FAMILY = "Archivo"
FONT_FALLBACK = "Segoe UI"
MONO_FAMILY = "Cascadia Mono"
MONO_FALLBACK = "Consolas"

_loaded_families: list[str] = []


def load_fonts() -> None:
    """Register bundled Archivo faces, if they were shipped.

    The design calls for Archivo; without it the app falls back to the system
    UI font rather than failing. Weights and sizes are unchanged either way.
    """
    from netwatch.utils.paths import asset_path

    fonts_dir = asset_path("fonts")
    if not fonts_dir.is_dir():
        return
    for ttf in sorted(fonts_dir.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(ttf))
        if font_id != -1:
            _loaded_families.extend(QFontDatabase.applicationFontFamilies(font_id))


def ui_font(size: int, weight: int = 400, spacing: float = 0.0) -> QFont:
    """A UI font. ``spacing`` is em-based letter-spacing, as in the design."""
    family = FONT_FAMILY if FONT_FAMILY in _loaded_families else FONT_FALLBACK
    f = QFont(family, size)
    f.setWeight(QFont.Weight(weight))
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100 + spacing * 100)
    return f


def mono_font(size: int) -> QFont:
    f = QFont(MONO_FAMILY, size)
    if not f.exactMatch():
        f = QFont(MONO_FALLBACK, size)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


# — measurements, so widgets agree with each other —

SIDEBAR_WIDTH = 320
WINDOW_MIN_WIDTH = 1180
WINDOW_MAX_WIDTH = 1400
WINDOW_MIN_HEIGHT = 760
SPARK_SIZE = (96, 26)
CHART_HEIGHT = 130
#: Detail table columns: remote IP, domain, port, status, action.
TABLE_COLUMNS = (130, -1, 80, 130, 110)


def stylesheet() -> str:
    """Return the app-wide dark stylesheet."""
    return """
QWidget {
    background-color: #0d0d0f;
    color: #d4d4d8;
    font-family: "Segoe UI", "Consolas", sans-serif;
    font-size: 13px;
}

QMainWindow, #centralWidget {
    background-color: #0d0d0f;
}

/* Card / panel look */
QFrame#card, QFrame#detailPanel {
    background-color: #17171a;
    border: 1px solid #26262b;
    border-radius: 10px;
    padding: 14px;
}

/* Stat header (ACTIVE CONNECTIONS, etc.) */
QLabel[role="statLabel"] {
    color: #7a7a82;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}
QLabel[role="statValue"] {
    color: #f4f4f5;
    font-size: 26px;
    font-weight: 700;
}
QLabel[role="statValueAlert"] {
    color: #ef4444;
    font-size: 26px;
    font-weight: 700;
}

/* Process list rows */
QListWidget {
    background-color: transparent;
    border: none;
    outline: none;
}
QListWidget::item {
    padding: 12px 10px;
    margin-bottom: 4px;
    border-radius: 8px;
}
QListWidget::item:selected {
    background-color: #1f1f24;
    border: 1px solid #ef4444;
}
QListWidget::item:hover:!selected {
    background-color: #1a1a1e;
}

/* Filter box */
QLineEdit {
    background-color: #17171a;
    border: 1px solid #2b2b31;
    border-radius: 8px;
    padding: 8px 12px;
    color: #d4d4d8;
}
QLineEdit:focus {
    border: 1px solid #ef4444;
}

/* Table (connections) */
QTableWidget {
    background-color: transparent;
    gridline-color: #26262b;
    border: none;
}
QHeaderView::section {
    background-color: transparent;
    color: #7a7a82;
    font-size: 11px;
    font-weight: 600;
    border: none;
    padding: 6px;
}
QTableWidget::item {
    padding: 10px 6px;
    border-bottom: 1px solid #1e1e22;
}

/* Buttons */
QPushButton {
    background-color: #1f1f24;
    border: 1px solid #2b2b31;
    border-radius: 6px;
    padding: 6px 14px;
    color: #d4d4d8;
}
QPushButton:hover {
    background-color: #262629;
}
QPushButton#blockBtn {
    background-color: #2a1214;
    border: 1px solid #ef4444;
    color: #ef4444;
    font-weight: 600;
}
QPushButton#blockBtn:hover {
    background-color: #ef4444;
    color: #0d0d0f;
}

QScrollBar:vertical {
    background: transparent;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #2b2b31;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""
