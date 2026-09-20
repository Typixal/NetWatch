"""The custom title bar: window controls, brand, and the live indicator.

The window is frameless, so this bar also provides dragging and the
minimise/maximise/close buttons. The three squares on the left are the
controls themselves rather than decoration.
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from netwatch.ui import theme

DOT_SIZE = 11
PULSE_SIZE = 7


class PulseDot(QWidget):
    """The 7px accent square that pulses to show polling is live."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(PULSE_SIZE, PULSE_SIZE)
        self._opacity = 1.0

        self._anim = QPropertyAnimation(self, b"pulse", self)
        self._anim.setDuration(2000)
        self._anim.setStartValue(1.0)
        self._anim.setKeyValueAt(0.5, 0.25)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.start()

    @pyqtProperty(float)
    def pulse(self) -> float:
        return self._opacity

    @pulse.setter
    def pulse(self, value: float) -> None:
        self._opacity = value
        self.update()

    def stop(self) -> None:
        self._anim.stop()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        colour = QColor(theme.ACCENT)
        colour.setAlphaF(self._opacity)
        p.fillRect(self.rect(), colour)
        p.end()


class TitleBar(QWidget):
    minimise_requested = pyqtSignal()
    maximise_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, interval_s: int = 2, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setAutoFillBackground(True)
        self._drag_offset: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        for name, signal in (
            ("winBtn", self.minimise_requested),
            ("winBtn", self.maximise_requested),
            ("winBtnClose", self.close_requested),
        ):
            btn = QPushButton(self)
            btn.setObjectName(name if name == "winBtnClose" else "winBtn")
            if name == "winBtnClose":
                btn.setProperty("class", "close")
            btn.setFixedSize(DOT_SIZE, DOT_SIZE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(signal)
            controls.addWidget(btn)
        layout.addLayout(controls)

        brand = QLabel("NetWatch", self)
        brand.setFont(theme.ui_font(9, 600, spacing=0.14))
        brand.setStyleSheet(f"color: {theme.TEXT}; background: transparent;")
        layout.addWidget(brand)

        tagline = QLabel("per-app network monitor", self)
        tagline.setFont(theme.ui_font(9))
        tagline.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
        layout.addWidget(tagline)

        layout.addStretch(1)

        self._dot = PulseDot(self)
        layout.addWidget(self._dot)

        self._live = QLabel(f"LIVE · {interval_s}s", self)
        self._live.setFont(theme.mono_font(8))
        self._live.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
        layout.addWidget(self._live)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_interval(self, seconds: int) -> None:
        self._live.setText(f"LIVE · {seconds}s")

    def set_live(self, live: bool) -> None:
        """Stop the pulse when polling stops, so the bar never lies."""
        if live:
            self._dot.show()
        else:
            self._dot.stop()
            self._dot.hide()

    # — dragging a frameless window —

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            self._drag_offset = (
                event.globalPosition().toPoint() - window.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is None:
            return
        window = self.window()
        if window.isMaximized():
            # Dragging a maximised window restores it under the cursor.
            window.showNormal()
            self._drag_offset = QPoint(window.width() // 2, self.height() // 2)
        window.move(event.globalPosition().toPoint() - self._drag_offset)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximise_requested.emit()
            event.accept()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG_TITLE))
        p.fillRect(
            0, self.height() - 2, self.width(), 2, QColor(theme.BORDER_HARD)
        )
        p.end()
