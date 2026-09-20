"""The 60-second connections chart in the detail pane.

Full-width, 130px tall, two gridlines, accent line over a translucent fill,
with a ``-60s … now`` axis underneath.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from netwatch.ui import theme
from netwatch.ui.sparkline import area_path, line_path, normalise, points

#: Gridline positions as fractions of height — y=43 and y=86 of 130 in the mock.
GRIDLINES = (43 / 130, 86 / 130)
AXIS_LABELS = ("-60s", "-45s", "-30s", "-15s", "now")
AXIS_HEIGHT = 20


class ConnectionsChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[int] = []
        self.setMinimumHeight(theme.CHART_HEIGHT + AXIS_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_values(self, values: list[int]) -> None:
        if values == self._values:
            return
        self._values = list(values)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        w = float(self.width())
        h = float(theme.CHART_HEIGHT)

        # Gridlines, then the baseline the design draws as a bottom border.
        p.setPen(QPen(QColor(theme.BORDER_SOFT), 1))
        for frac in GRIDLINES:
            y = round(h * frac) + 0.5
            p.drawLine(int(0), int(y), int(w), int(y))
        p.setPen(QPen(QColor(theme.BORDER_HARD), 1))
        p.drawLine(0, int(h), int(w), int(h))

        if self._values:
            pts = points(normalise(self._values), w, h, pad=6.0)
            if pts:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                p.fillPath(area_path(pts, w, h), theme.ACCENT_FILL)
                pen = QPen(QColor(theme.ACCENT), 2)
                pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
                p.setPen(pen)
                p.drawPath(line_path(pts))
                p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Axis labels, first left-aligned and last right-aligned so neither
        # hangs off the edge.
        p.setFont(theme.mono_font(8))
        p.setPen(QColor(theme.TEXT_FAINT))
        y = int(h) + AXIS_HEIGHT - 6
        last = len(AXIS_LABELS) - 1
        for i, label in enumerate(AXIS_LABELS):
            metrics = p.fontMetrics()
            tw = metrics.horizontalAdvance(label)
            if i == 0:
                x = 0
            elif i == last:
                x = int(w) - tw
            else:
                x = int(w * i / last - tw / 2)
            p.drawText(x, y, label)
        p.end()
