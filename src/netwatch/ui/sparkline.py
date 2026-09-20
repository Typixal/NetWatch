"""Shared polyline maths, and the small sidebar sparkline.

Normalisation matches the design prototype's ``spark()`` exactly:
``x = i/(n-1)*w``, ``y = h - pad - v*(h - 2*pad)`` over values scaled to 0..1.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from netwatch.ui import theme


#: Headroom above the peak, so a steady series doesn't pin to the top and
#: flood the fill. Most processes hold a near-constant connection count, so
#: scaling to the peak alone would make almost every graph a solid block.
HEADROOM = 1.25
#: Smallest y-axis ceiling. Keeps a 1-connection process from looking maxed.
MIN_CEILING = 4


def ceiling_for(values: list[int], headroom: float = HEADROOM) -> float:
    """The y-axis maximum for a series."""
    peak = max(values) if values else 0
    return max(float(MIN_CEILING), peak * headroom)


def normalise(values: list[int], ceiling: float | None = None) -> list[float]:
    """Scale counts to 0..1 against ``ceiling`` (default: peak plus headroom)."""
    if not values:
        return []
    top = ceiling_for(values) if ceiling is None else ceiling
    if top <= 0:
        return [0.0] * len(values)
    return [min(1.0, v / top) for v in values]


def points(values: list[float], width: float, height: float, pad: float = 2.0):
    """Polyline points for a 0..1 series across the given box."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        y = height - pad - values[0] * (height - pad * 2)
        return [QPointF(0.0, y), QPointF(width, y)]
    span = height - pad * 2
    return [
        QPointF(i / (n - 1) * width, height - pad - v * span)
        for i, v in enumerate(values)
    ]


def line_path(pts) -> QPainterPath:
    path = QPainterPath()
    if not pts:
        return path
    path.moveTo(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    return path


def area_path(pts, width: float, height: float) -> QPainterPath:
    """The line, closed down to the baseline, for the fill underneath."""
    path = line_path(pts)
    if pts:
        path.lineTo(width, height)
        path.lineTo(0.0, height)
        path.closeSubpath()
    return path


class Sparkline(QWidget):
    """96x26 connection-count trace for one process."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        w, h = theme.SPARK_SIZE
        self.setFixedSize(w, h)
        self._values: list[int] = []
        self._state = "normal"  # normal | flagged | blocked

    def set_values(self, values: list[int], state: str = "normal") -> None:
        if values == self._values and state == self._state:
            return
        self._values = list(values)
        self._state = state
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(*theme.SPARK_SIZE)

    def _colours(self) -> tuple[QColor, QColor]:
        if self._state == "blocked":
            return theme.MUTED_STROKE, theme.MUTED_FILL
        if self._state == "flagged":
            return QColor(theme.ACCENT), theme.ACCENT_FILL
        return theme.NEUTRAL_STROKE, theme.NEUTRAL_FILL

    def paintEvent(self, _event) -> None:
        if not self._values:
            return
        w = float(self.width())
        h = float(self.height())
        pts = points(normalise(self._values), w, h)
        if not pts:
            return

        stroke, fill = self._colours()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillPath(area_path(pts, w, h), fill)
        pen = QPen(stroke, 1.5)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)  # the design is hard-edged
        p.setPen(pen)
        p.drawPath(line_path(pts))
        p.end()
