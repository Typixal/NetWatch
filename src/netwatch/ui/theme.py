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
    """App-wide QSS. Widget-specific painting lives in the widgets."""
    return f"""
    QWidget {{
        background: {BG_WINDOW};
        color: {TEXT};
    }}

    /* Labels sit on top of custom-painted rows, so they must not paint a
       ground of their own — otherwise every label shows as a grey box. */
    QLabel {{
        background: transparent;
    }}

    QToolTip {{
        background: {BG_TITLE};
        color: {TEXT};
        border: 1px solid {BORDER_HARD};
        padding: 4px 6px;
    }}

    /* — filter box — */
    QLineEdit#filter {{
        background: {BG_APP};
        border: 1px solid {BORDER_HARD};
        border-radius: 0;
        color: {TEXT};
        padding: 9px 10px;
        selection-background-color: {ACCENT};
    }}
    QLineEdit#filter:focus {{
        border-color: {BORDER_CTRL};
    }}

    /* — sidebar filter tabs — */
    QPushButton#tab {{
        background: transparent;
        border: none;
        border-right: 1px solid {BORDER_SOFT};
        color: {TEXT_MUTED};
        padding: 9px 0;
    }}
    QPushButton#tab:hover {{
        color: {TEXT};
    }}
    QPushButton#tab:checked {{
        background: {BG_ROW_SELECTED};
        color: {TEXT};
    }}
    QPushButton#tab:last-child {{
        border-right: none;
    }}

    /* — row action buttons — */
    QPushButton#rowAction {{
        background: transparent;
        border: 1px solid {BORDER_CTRL};
        border-radius: 0;
        color: {TEXT_DIM};
        padding: 8px 12px;
    }}
    QPushButton#rowAction:hover {{
        background: {ACCENT};
        border-color: {ACCENT};
        color: {TEXT};
    }}
    QPushButton#rowAction[blocked="true"] {{
        background: {ACCENT};
        border-color: {ACCENT};
        color: {TEXT};
    }}
    QPushButton#rowAction[blocked="true"]:hover {{
        background: {ACCENT_HOVER};
        border-color: {ACCENT_HOVER};
    }}

    /* — window control buttons in the title bar — */
    QPushButton#winBtn {{
        background: {INACTIVE};
        border: none;
        border-radius: 0;
    }}
    QPushButton#winBtn:hover {{
        background: {TEXT_DIM};
    }}
    QPushButton#winBtnClose:hover {{
        background: {ACCENT};
    }}

    /* — scrollbars: thin, square, unobtrusive — */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER_HARD};
        min-height: 30px;
        border-radius: 0;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {BORDER_CTRL};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QScrollArea {{
        border: none;
    }}
    """
