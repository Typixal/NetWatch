"""The square block toggle, in sidebar (34x18) and detail (56x28) sizes."""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget

from netwatch.ui import theme

SMALL = (34, 18)
LARGE = (56, 28)


class BlockToggle(QWidget):
    """Square track, square knob, knob slides on state change.

    Emits ``toggled`` on click but does **not** change its own state: the
    firewall decides whether the block actually happened. The owner calls
    ``set_checked`` once it knows. That keeps the toggle from ever showing a
    state the firewall doesn't have.
    """

    toggled = pyqtSignal(bool)

    def __init__(self, large: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._w, self._h = LARGE if large else SMALL
        self._pad = 3 if large else 2
        self._knob = self._h - self._pad * 2
        self._checked = False
        self._pos = 0.0  # 0 = left, 1 = right
        self.setFixedSize(self._w, self._h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"knob_pos", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # — state —

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool, animate: bool = True) -> None:
        if checked == self._checked:
            return
        self._checked = checked
        target = 1.0 if checked else 0.0
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.knob_pos = target

    @pyqtProperty(float)
    def knob_pos(self) -> float:
        return self._pos

    @knob_pos.setter
    def knob_pos(self, value: float) -> None:
        self._pos = value
        self.update()

    # — interaction —

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            # Report the state being asked for, not a state we've adopted.
            self.toggled.emit(not self._checked)
        else:
            super().mousePressEvent(event)

    def sizeHint(self) -> QSize:
        return QSize(self._w, self._h)

    # — painting —

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # hard edges

        on = self._checked
        track = QColor(theme.ACCENT if on else theme.BG_APP)
        border = QColor(theme.ACCENT if on else theme.BORDER_CTRL)
        knob = QColor(theme.TEXT if on else theme.TEXT_FAINT)

        p.fillRect(self.rect(), track)
        p.setPen(border)
        p.drawRect(0, 0, self._w - 1, self._h - 1)

        travel = self._w - self._pad * 2 - self._knob
        x = self._pad + travel * self._pos
        p.fillRect(int(round(x)), self._pad, self._knob, self._knob, knob)
        p.end()
