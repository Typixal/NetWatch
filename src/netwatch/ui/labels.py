"""A label that shows an ellipsis instead of clipping.

Process names and exe paths routinely overrun their column; Qt's default is
a hard clip, which reads as a rendering bug rather than as truncation.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget


class ElidedLabel(QLabel):
    def __init__(
        self,
        text: str = "",
        mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802 — Qt naming
        self._full = text
        self._apply()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply()

    def _apply(self) -> None:
        elided = self.fontMetrics().elidedText(self._full, self._mode, self.width())
        super().setText(elided)
        # Only offer a tooltip when something is actually hidden.
        self.setToolTip(self._full if elided != self._full else "")
