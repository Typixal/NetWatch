from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QCheckBox

class ToggleSwitch(QCheckBox):
    def __init__(self, parent=None, width=46, height=24):
        super().__init__(parent)
        self._w, self._h = width, height
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._circle_pos = 3
        self._anim = QPropertyAnimation(self, b"circle_pos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.stateChanged.connect(self._start_transition)

    def _start_transition(self, state):
        end = self._w - self._h + 3 if state else 3
        self._anim.stop()
        self._anim.setStartValue(self._circle_pos)
        self._anim.setEndValue(end)
        self._anim.start()

    def get_circle_pos(self):
        return self._circle_pos

    def set_circle_pos(self, pos):
        self._circle_pos = pos
        self.update()

    circle_pos = pyqtProperty(float, fget=get_circle_pos, fset=set_circle_pos)

    def hitButton(self, pos):
        return self.contentsRect().contains(pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        track_color = QColor("#ef4444") if self.isChecked() else QColor("#2b2b31")
        p.setBrush(track_color)
        p.drawRoundedRect(0, 0, self._w, self._h, self._h / 2, self._h / 2)

        circle_d = self._h - 6
        p.setBrush(QColor("#f4f4f5"))
        p.drawEllipse(QRectF(self._circle_pos, 3, circle_d, circle_d))


class BlockToggle(ToggleSwitch):
    """Toggle used to block a process, with a larger detail-pane variant."""

    def __init__(self, parent=None, large=False):
        width, height = (54, 28) if large else (46, 24)
        super().__init__(parent, width, height)

    def set_checked(self, checked):
        self.setChecked(checked)