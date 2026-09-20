"""The four stat cards under the title bar."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from netwatch.core.store import ProcessGroup
from netwatch.ui import theme


class StatCard(QWidget):
    def __init__(self, label: str, accent: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._accent = accent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        self._label = QLabel(label.upper(), self)
        self._label.setFont(theme.ui_font(8, 500, spacing=0.16))
        self._label.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")

        self._value = QLabel("0", self)
        self._value.setFont(theme.ui_font(26, 600, spacing=-0.02))
        self._value.setStyleSheet(
            f"color: {theme.ACCENT if accent else theme.TEXT}; background: transparent;"
        )

        layout.addWidget(self._label)
        layout.addWidget(self._value)
        layout.addStretch(1)

    def set_value(self, value: int) -> None:
        text = str(value)
        if self._value.text() != text:
            self._value.setText(text)

    def set_accent_when_nonzero(self, value: int) -> None:
        """Zero flagged items shouldn't glow red — only a real count should."""
        colour = theme.ACCENT if (self._accent and value) else theme.TEXT
        self._value.setStyleSheet(f"color: {colour}; background: transparent;")


class SummaryBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(88)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 2)  # room for the 2px bottom border
        layout.setSpacing(0)

        self.connections = StatCard("Active connections")
        self.processes = StatCard("Active processes")
        self.blocked = StatCard("Blocked apps", accent=True)
        self.unknown = StatCard("Unknown destinations", accent=True)

        for card in (self.connections, self.processes, self.blocked, self.unknown):
            layout.addWidget(card, 1)

    def update_stats(self, groups: list[ProcessGroup], blocked_count: int) -> None:
        connections = sum(len(g.connections) for g in groups)
        unknown = sum(
            1 for g in groups for c in g.connections if c.flagged
        )

        self.connections.set_value(connections)
        self.processes.set_value(len(groups))
        self.blocked.set_value(blocked_count)
        self.unknown.set_value(unknown)

        self.blocked.set_accent_when_nonzero(blocked_count)
        self.unknown.set_accent_when_nonzero(unknown)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG_WINDOW))

        # 1px dividers between cards, 2px rule underneath.
        width = self.width()
        for i in range(1, 4):
            x = round(width * i / 4)
            p.fillRect(x, 0, 1, self.height() - 2, QColor(theme.BORDER_SOFT))
        p.fillRect(
            0, self.height() - 2, width, 2, QColor(theme.BORDER_HARD)
        )
        p.end()
