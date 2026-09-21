from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget


class TitleBarButton(QPushButton):
    """Draws its own minimize/maximize/restore/close glyph — no icon files needed."""
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind  # "min" | "max" | "restore" | "close"
        self.setFixedSize(38, 32)
        self.setFlat(True)
        self.setStyleSheet(self._style())

    def _style(self):
        hover = "#ef4444" if self.kind == "close" else "#26262b"
        return f"""
            QPushButton {{ background: transparent; border: none; }}
            QPushButton:hover {{ background-color: {hover}; }}
        """

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#f4f4f5") if not (self.kind == "close" and self.underMouse()) else QColor("#ffffff")
        pen = QPen(color, 1.2)
        p.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2
        s = 5  # half-size of glyph

        if self.kind == "min":
            p.drawLine(int(cx - s), int(cy), int(cx + s), int(cy))
        elif self.kind == "max":
            p.drawRect(int(cx - s), int(cy - s), int(s * 2), int(s * 2))
        elif self.kind == "restore":
            p.drawRect(int(cx - s + 3), int(cy - s), int(s * 2 - 3), int(s * 2 - 3))
            p.drawRect(int(cx - s), int(cy - s + 3), int(s * 2 - 3), int(s * 2 - 3))
        elif self.kind == "close":
            p.drawLine(int(cx - s), int(cy - s), int(cx + s), int(cy + s))
            p.drawLine(int(cx - s), int(cy + s), int(cx + s), int(cy - s))


class TitleBar(QWidget):
    minimise_requested = pyqtSignal()
    maximise_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, interval_s: int, parent=None):
        super().__init__(parent)
        self.interval_s = interval_s
        self.win = parent.window() if parent is not None else None
        self.setFixedHeight(34)
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(0)

        self.title = QLabel("NetWatch  |  per-app network monitor")
        self.title.setStyleSheet("color:#d4d4d8; font-weight:600; font-size:12px;")
        layout.addWidget(self.title)

        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(spacer)

        self.btn_min = TitleBarButton("min")
        self.btn_max = TitleBarButton("max")
        self.btn_close = TitleBarButton("close")
        for b in (self.btn_min, self.btn_max, self.btn_close):
            layout.addWidget(b)

        self.btn_min.clicked.connect(self.minimise_requested)
        self.btn_max.clicked.connect(self.maximise_requested)
        self.btn_close.clicked.connect(self.close_requested)

    def set_live(self, live: bool) -> None:
        """Update the title-bar tooltip when polling stops or resumes."""
        self.setToolTip("Live monitoring" if live else "Monitoring stopped")

    def _toggle_max(self):
        self.maximise_requested.emit()

    # Drag-to-move since the OS title bar is gone
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.win is not None:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.win.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event):
        if (
            self._drag_pos is not None
            and event.buttons() == Qt.MouseButton.LeftButton
            and self.win is not None
        ):
            self.win.move(event.globalPosition().toPoint() - self._drag_pos)