"""The left sidebar: filter box, All/Flagged/Blocked tabs, and the process list.

Rows are reused across polls and keyed on process name. Rebuilding the list
every two seconds would flicker, lose the selection, and fight the scroll
position.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from netwatch.core.history import HistoryTracker
from netwatch.core.store import ProcessGroup
from netwatch.ui import theme
from netwatch.ui.labels import ElidedLabel
from netwatch.ui.sparkline import Sparkline
from netwatch.ui.toggle import BlockToggle

FILTER_ALL = "all"
FILTER_FLAGGED = "flagged"
FILTER_BLOCKED = "blocked"


class ProcessRow(QWidget):
    """One process. Name + pid, a meta line, a sparkline, and a block toggle."""

    clicked = pyqtSignal(str)
    block_toggled = pyqtSignal(str, bool)

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.name = name
        self._selected = False
        self._hovered = False
        self._flagged = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 13, 16, 13)
        outer.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._name = ElidedLabel(name, parent=self)
        self._name.setFont(theme.ui_font(10, 600))
        self._pid = QLabel("", self)
        self._pid.setFont(theme.mono_font(8))
        self._pid.setStyleSheet(f"color: {theme.TEXT_FAINT}; background: transparent;")
        top.addWidget(self._name, 1)
        top.addWidget(self._pid, 0)
        left.addLayout(top)

        self._meta = QLabel("", self)
        self._meta.setFont(theme.ui_font(8))
        left.addWidget(self._meta)

        self._rate = QLabel("", self)
        self._rate.setFont(theme.mono_font(8))
        self._rate.setStyleSheet(f"color: {theme.TEXT_FAINT}; background: transparent;")
        left.addWidget(self._rate)

        outer.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.spark = Sparkline(self)
        right.addWidget(self.spark, 0, Qt.AlignmentFlag.AlignRight)
        self.toggle = BlockToggle(parent=self)
        self.toggle.setToolTip("Block all outbound traffic for this process")
        self.toggle.toggled.connect(lambda want: self.block_toggled.emit(self.name, want))
        right.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignRight)
        outer.addLayout(right, 0)

    # — state —

    def update_from(self, group: ProcessGroup, series: list[int]) -> None:
        blocked = group.blocked
        self._flagged = group.flagged

        self._pid.setText(f"pid {group.pid}" if group.pid is not None else "")

        if blocked:
            meta, colour = "blocked", theme.TEXT_MUTED
        elif group.flagged:
            count = len(group.connections)
            meta = f"{count} connection{'s' if count != 1 else ''} · unknown destination"
            colour = theme.ACCENT
        else:
            count = len(group.connections)
            meta = f"{count} connection{'s' if count != 1 else ''}"
            colour = theme.TEXT_MUTED
        self._meta.setText(meta)
        self._meta.setStyleSheet(f"color: {colour}; background: transparent;")

        name_colour = theme.TEXT_FAINT if blocked else theme.TEXT
        decoration = "line-through" if blocked else "none"
        self._name.setStyleSheet(
            f"color: {name_colour}; text-decoration: {decoration};"
            " background: transparent;"
        )

        endpoints = len({(c.remote_ip, c.remote_port) for c in group.connections})
        peak = max(series) if series else 0
        self._rate.setText(
            "no traffic" if not group.connections
            else f"{endpoints} endpoint{'s' if endpoints != 1 else ''} · peak {peak}"
        )

        state = "blocked" if blocked else ("flagged" if group.flagged else "normal")
        self.spark.set_values(series, state)
        self.toggle.set_checked(blocked)

    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self.update()

    # — interaction —

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.name)
            event.accept()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        if self._selected:
            background = QColor(theme.BG_ROW_SELECTED)
        elif self._hovered:
            background = QColor(theme.BG_ROW_HOVER)
        else:
            background = QColor(theme.BG_SIDEBAR)
        p.fillRect(self.rect(), background)

        # 3px accent marker on the selected row.
        if self._selected:
            p.fillRect(0, 0, 3, self.height(), QColor(theme.ACCENT))

        p.fillRect(
            0, self.height() - 1, self.width(), 1, QColor(theme.BORDER_SOFT)
        )
        p.end()


class ProcessList(QWidget):
    """Sidebar. Owns filtering and selection; the window owns the data."""

    process_selected = pyqtSignal(str)
    block_toggled = pyqtSignal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(theme.SIDEBAR_WIDTH)

        self._rows: dict[str, ProcessRow] = {}
        self._groups: list[ProcessGroup] = []
        self._selected: str | None = None
        self._filter_text = ""
        self._filter_mode = FILTER_ALL

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Filter box.
        search_wrap = QWidget(self)
        search_layout = QVBoxLayout(search_wrap)
        search_layout.setContentsMargins(16, 12, 16, 12)
        self.search = QLineEdit(search_wrap)
        self.search.setObjectName("filter")
        self.search.setPlaceholderText("filter processes")
        self.search.setFont(theme.ui_font(10))
        self.search.textChanged.connect(self._on_filter_text)
        search_layout.addWidget(self.search)
        layout.addWidget(search_wrap)
        layout.addWidget(_HLine(theme.BORDER_SOFT, 1, self))

        # All / Flagged / Blocked.
        tabs = QWidget(self)
        tabs_layout = QHBoxLayout(tabs)
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(0)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        for mode, label in (
            (FILTER_ALL, "All"),
            (FILTER_FLAGGED, "Flagged"),
            (FILTER_BLOCKED, "Blocked"),
        ):
            btn = QPushButton(label.upper(), tabs)
            btn.setObjectName("tab")
            btn.setCheckable(True)
            btn.setFont(theme.ui_font(8, 600, spacing=0.14))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setChecked(mode == FILTER_ALL)
            btn.clicked.connect(lambda _c, m=mode: self.set_filter_mode(m))
            self._tab_group.addButton(btn)
            tabs_layout.addWidget(btn, 1)
        layout.addWidget(tabs)
        layout.addWidget(_HLine(theme.BORDER_SOFT, 1, self))

        # Scrolling row list.
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._container = QWidget()
        self._container.setStyleSheet(f"background: {theme.BG_SIDEBAR};")
        self._rows_layout = QVBoxLayout(self._container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)

        self._empty = QLabel("no processes match", self._container)
        self._empty.setFont(theme.ui_font(9))
        self._empty.setStyleSheet(
            f"color: {theme.TEXT_FAINT}; padding: 20px 16px; background: transparent;"
        )
        self._empty.hide()
        self._rows_layout.addWidget(self._empty)
        self._rows_layout.addStretch(1)

        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll, 1)

    # — data —

    def update_groups(self, groups: list[ProcessGroup], history: HistoryTracker) -> None:
        self._groups = groups
        names = {g.name for g in groups}

        for name in list(self._rows):
            if name not in names:
                row = self._rows.pop(name)
                self._rows_layout.removeWidget(row)
                row.deleteLater()

        # Keep display order in sync with the sorted groups.
        for index, group in enumerate(groups):
            row = self._rows.get(group.name)
            if row is None:
                row = ProcessRow(group.name, self._container)
                row.clicked.connect(self._on_row_clicked)
                row.block_toggled.connect(self.block_toggled)
                self._rows[group.name] = row
            self._rows_layout.insertWidget(index, row)
            row.update_from(group, history.spark(group.name))

        if self._selected not in names:
            self._selected = None
        if self._selected is None and groups:
            self.select(self._visible_names()[0] if self._visible_names() else None)

        self._apply_filter()
        self._refresh_selection()

    def selected_name(self) -> str | None:
        return self._selected

    def select(self, name: str | None) -> None:
        if name is None or name == self._selected:
            return
        self._selected = name
        self._refresh_selection()
        self.process_selected.emit(name)

    def _on_row_clicked(self, name: str) -> None:
        self.select(name)

    def _refresh_selection(self) -> None:
        for name, row in self._rows.items():
            row.set_selected(name == self._selected)

    # — filtering —

    def _on_filter_text(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self._apply_filter()

    def set_filter_mode(self, mode: str) -> None:
        self._filter_mode = mode
        self._apply_filter()

    def _matches(self, group: ProcessGroup) -> bool:
        if self._filter_mode == FILTER_FLAGGED and not group.flagged:
            return False
        if self._filter_mode == FILTER_BLOCKED and not group.blocked:
            return False
        if self._filter_text and self._filter_text not in group.name.lower():
            return False
        return True

    def _visible_names(self) -> list[str]:
        return [g.name for g in self._groups if self._matches(g)]

    def _apply_filter(self) -> None:
        visible = set(self._visible_names())
        for name, row in self._rows.items():
            # setHidden, not a rebuild — filtering must never re-query psutil.
            row.setHidden(name not in visible)
        self._empty.setVisible(not visible and bool(self._rows))


class _HLine(QWidget):
    def __init__(self, colour: str, height: int, parent=None) -> None:
        super().__init__(parent)
        self._colour = colour
        self.setFixedHeight(height)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(self._colour))
        p.end()
