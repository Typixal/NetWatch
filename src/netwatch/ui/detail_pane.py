"""The right pane: selected process header, 60s chart, connection table, footer."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from netwatch.core.store import Connection, ProcessGroup
from netwatch.ui import theme
from netwatch.ui.chart import ConnectionsChart
from netwatch.ui.labels import ElidedLabel
from netwatch.ui.toggle import BlockToggle

COLUMNS = ("Remote IP", "Domain", "Port", "Status", "Action")
COLUMN_WIDTHS = (130, -1, 80, 130, 110)
COLUMN_GAP = 16
UNRESOLVED = "— unresolved —"
RESOLVING = "resolving…"


def _add_columns(layout: QHBoxLayout, widgets: list[QWidget]) -> None:
    """Lay widgets out on the shared column grid, so header and rows align."""
    for widget, width in zip(widgets, COLUMN_WIDTHS):
        if width < 0:
            widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            layout.addWidget(widget, 1)
        else:
            widget.setFixedWidth(width)
            layout.addWidget(widget, 0)


class ConnectionRow(QWidget):
    block_toggled = pyqtSignal(object, bool)  # (Connection, want_blocked)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._conn: Connection | None = None
        self._washed = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 13, 24, 13)
        layout.setSpacing(COLUMN_GAP)

        self._ip = QLabel(self)
        self._ip.setFont(theme.mono_font(9))

        self._domain = ElidedLabel(parent=self)
        self._domain.setFont(theme.ui_font(10))

        self._port = QLabel(self)
        self._port.setFont(theme.mono_font(9))
        self._port.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")

        status_wrap = QWidget(self)
        # Column wrappers must not paint a ground either, or they show as
        # boxes over the row's own background (obvious on flagged rows).
        status_wrap.setStyleSheet("background: transparent;")
        status_layout = QHBoxLayout(status_wrap)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(7)
        self._dot = _Dot(status_wrap)
        self._status = QLabel(status_wrap)
        self._status.setFont(theme.mono_font(8))
        status_layout.addWidget(self._dot)
        status_layout.addWidget(self._status)
        status_layout.addStretch(1)

        action_wrap = QWidget(self)
        action_wrap.setStyleSheet("background: transparent;")
        action_layout = QHBoxLayout(action_wrap)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._button = QPushButton("BLOCK", action_wrap)
        self._button.setObjectName("rowAction")
        self._button.setFont(theme.ui_font(8, 600, spacing=0.14))
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.clicked.connect(self._on_click)
        action_layout.addWidget(self._button)

        _add_columns(layout, [self._ip, self._domain, self._port, status_wrap, action_wrap])

    def _on_click(self) -> None:
        if self._conn is not None:
            self.block_toggled.emit(self._conn, self._button.text() == "BLOCK")

    def update_from(self, conn: Connection, blocked: bool) -> None:
        self._conn = conn

        unresolved = conn.domain is None and not conn.dns_pending
        self._washed = unresolved

        self._ip.setText(conn.remote_ip)
        self._ip.setStyleSheet(
            f"color: {theme.ACCENT if unresolved else theme.TEXT}; background: transparent;"
        )

        if conn.domain:
            domain, domain_colour = conn.domain, (
                theme.TEXT_FAINT if blocked else theme.TEXT_DIM
            )
        elif conn.dns_pending:
            domain, domain_colour = RESOLVING, theme.TEXT_FAINT
        else:
            domain, domain_colour = UNRESOLVED, theme.ACCENT
        self._domain.setText(domain)  # ElidedLabel manages its own tooltip
        self._domain.setStyleSheet(f"color: {domain_colour}; background: transparent;")

        self._port.setText(str(conn.remote_port))

        status = "blocked" if blocked else conn.status.lower()
        established = conn.status.upper() == "ESTABLISHED"
        if blocked:
            status_colour = theme.ACCENT
            dot_colour = theme.ACCENT
        elif established:
            status_colour = theme.TEXT
            dot_colour = theme.TEXT_DIM
        else:
            status_colour = theme.TEXT_MUTED
            dot_colour = theme.INACTIVE
        self._status.setText(status)
        self._status.setStyleSheet(f"color: {status_colour}; background: transparent;")
        self._dot.set_colour(dot_colour)

        self._button.setText("UNBLOCK" if blocked else "BLOCK")
        self._button.setProperty("blocked", "true" if blocked else "false")
        # Qt only restyles on a property change when told to re-polish.
        self._button.style().unpolish(self._button)
        self._button.style().polish(self._button)

        if conn.flagged and conn.flag_reason:
            self.setToolTip(conn.flag_reason)

        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG_WINDOW))
        if self._washed:
            p.fillRect(self.rect(), theme.ACCENT_FILL_SOFT)
        p.fillRect(0, self.height() - 1, self.width(), 1, QColor(theme.BORDER_SOFT))
        p.end()


class _Dot(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(6, 6)
        self._colour = theme.INACTIVE

    def set_colour(self, colour: str) -> None:
        if colour != self._colour:
            self._colour = colour
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(self._colour))
        p.end()


class DetailPane(QWidget):
    block_toggled = pyqtSignal(str, bool)  # (process name, want_blocked)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group: ProcessGroup | None = None
        self._rows: list[ConnectionRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())
        layout.addWidget(_Rule(theme.BORDER_HARD, 2, self))
        layout.addWidget(self._build_chart_block())
        layout.addWidget(_Rule(theme.BORDER_HARD, 2, self))
        layout.addWidget(self._build_table_header())
        layout.addWidget(self._build_table(), 1)
        layout.addWidget(_Rule(theme.BORDER_HARD, 2, self))
        layout.addWidget(self._build_footer())

    # — construction —

    def _build_header(self) -> QWidget:
        wrap = QWidget(self)
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        left = QVBoxLayout()
        left.setSpacing(9)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        self._title = QLabel("—", wrap)
        self._title.setFont(theme.ui_font(20, 600, spacing=-0.02))
        self._badge = QLabel("", wrap)
        self._badge.setFont(theme.ui_font(8, 500, spacing=0.14))
        title_row.addWidget(self._title, 0)
        title_row.addWidget(self._badge, 0)
        title_row.addStretch(1)
        left.addLayout(title_row)

        # Paths are long and their tail is the informative part, so elide
        # the middle rather than the end.
        self._subtitle = ElidedLabel(mode=Qt.TextElideMode.ElideMiddle, parent=wrap)
        self._subtitle.setFont(theme.mono_font(9))
        self._subtitle.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
        left.addWidget(self._subtitle)
        layout.addLayout(left, 1)

        right = QHBoxLayout()
        right.setSpacing(14)
        block_label = QLabel("BLOCK ALL TRAFFIC", wrap)
        block_label.setFont(theme.ui_font(8, 500, spacing=0.16))
        block_label.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
        self.block_all = BlockToggle(large=True, parent=wrap)
        self.block_all.toggled.connect(self._on_block_all)
        right.addWidget(block_label)
        right.addWidget(self.block_all)
        layout.addLayout(right, 0)
        return wrap

    def _build_chart_block(self) -> QWidget:
        wrap = QWidget(self)
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        head = QHBoxLayout()
        label = QLabel("CONNECTIONS OVER TIME · LAST 60S", wrap)
        label.setFont(theme.ui_font(8, 500, spacing=0.16))
        label.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
        head.addWidget(label)
        head.addStretch(1)

        self._peak = QLabel("peak 0", wrap)
        self._avg = QLabel("avg 0", wrap)
        self._now = QLabel("now 0", wrap)
        for lbl, colour in (
            (self._peak, theme.TEXT_MUTED),
            (self._avg, theme.TEXT_MUTED),
            (self._now, theme.TEXT),
        ):
            lbl.setFont(theme.mono_font(8))
            lbl.setStyleSheet(f"color: {colour}; background: transparent;")
            head.addWidget(lbl)
            head.addSpacing(6)
        layout.addLayout(head)

        self.chart = ConnectionsChart(wrap)
        layout.addWidget(self.chart)
        return wrap

    def _build_table_header(self) -> QWidget:
        wrap = QWidget(self)
        wrap.setFixedHeight(37)
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(COLUMN_GAP)

        labels = []
        for i, name in enumerate(COLUMNS):
            lbl = QLabel(name.upper(), wrap)
            lbl.setFont(theme.ui_font(8, 500, spacing=0.16))
            lbl.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
            if i == len(COLUMNS) - 1:
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            labels.append(lbl)
        _add_columns(layout, labels)

        # Painted, not styled: a QSS border on the wrapper is inherited by
        # every child label and renders as disjoint segments.
        wrap.paintEvent = lambda _e, w=wrap: _paint_bottom_rule(w, theme.BORDER_HARD)
        return wrap

    def _build_table(self) -> QWidget:
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._table = QWidget()
        self._table_layout = QVBoxLayout(self._table)
        self._table_layout.setContentsMargins(0, 0, 0, 0)
        self._table_layout.setSpacing(0)

        self._empty = QLabel("no active connections", self._table)
        self._empty.setFont(theme.ui_font(10))
        self._empty.setStyleSheet(
            f"color: {theme.TEXT_FAINT}; padding: 24px; background: transparent;"
        )
        self._table_layout.addWidget(self._empty)
        self._table_layout.addStretch(1)

        self._scroll.setWidget(self._table)
        return self._scroll

    def _build_footer(self) -> QWidget:
        wrap = QWidget(self)
        wrap.setFixedHeight(41)
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(24, 12, 24, 12)

        self._footer_left = QLabel("", wrap)
        self._footer_right = QLabel("", wrap)
        for lbl in (self._footer_left, self._footer_right):
            lbl.setFont(theme.mono_font(8))
            lbl.setStyleSheet(f"color: {theme.TEXT_FAINT}; background: transparent;")
        layout.addWidget(self._footer_left)
        layout.addStretch(1)
        layout.addWidget(self._footer_right)
        return wrap

    # — data —

    def show_group(
        self,
        group: ProcessGroup | None,
        series: list[int],
        stats: tuple[int, int, int],
    ) -> None:
        self._group = group

        if group is None:
            self._title.setText("—")
            self._subtitle.setText("")
            self._badge.setText("")
            self._badge.setStyleSheet("")
            self.chart.set_values([])
            self._render_rows([], False)
            return

        self._title.setText(group.name)
        self._title.setStyleSheet(f"color: {theme.TEXT}; background: transparent;")

        pid = group.pid if group.pid is not None else "?"
        path = group.exe or "path unavailable"
        self._subtitle.setText(f"pid {pid} · {path}")

        if group.blocked:
            badge, colour = "BLOCKED", theme.ACCENT
        elif group.flagged:
            badge, colour = "FLAGGED · UNKNOWN DESTINATION", theme.ACCENT
        else:
            badge, colour = "ALLOWED", theme.TEXT_MUTED
        border = theme.ACCENT if (group.blocked or group.flagged) else theme.BORDER_CTRL
        self._badge.setText(f" {badge} ")
        self._badge.setStyleSheet(
            f"color: {colour}; border: 1px solid {border}; padding: 5px 8px;"
            " background: transparent;"
        )

        self.block_all.set_checked(group.blocked)

        peak, avg, now = stats
        self._peak.setText(f"peak {peak}")
        self._avg.setText(f"avg {avg}")
        self._now.setText(f"now {now}")
        self.chart.set_values(series)

        self._render_rows(group.connections, group.blocked)

    def _render_rows(self, connections: list[Connection], blocked: bool) -> None:
        # Grow the row pool as needed; reuse the widgets across refreshes.
        while len(self._rows) < len(connections):
            row = ConnectionRow(self._table)
            row.block_toggled.connect(self._on_row_block)
            self._rows.append(row)
            self._table_layout.insertWidget(len(self._rows) - 1, row)

        for i, row in enumerate(self._rows):
            if i < len(connections):
                row.update_from(connections[i], blocked)
                row.setHidden(False)
            else:
                row.setHidden(True)

        self._empty.setVisible(not connections)

    def set_footer(self, refreshed_s: int, interval_s: int, total: int, procs: int) -> None:
        self._footer_left.setText(
            f"last refreshed {refreshed_s}s ago · auto-refresh every {interval_s}s"
        )
        self._footer_right.setText(
            f"{total} connection{'s' if total != 1 else ''} "
            f"across {procs} process{'es' if procs != 1 else ''}"
        )

    # — actions —

    def _on_block_all(self, want_blocked: bool) -> None:
        if self._group is not None:
            self.block_toggled.emit(self._group.name, want_blocked)

    def _on_row_block(self, conn: Connection, want_blocked: bool) -> None:
        # Firewall rules are per program, not per socket, so a row's button
        # blocks the whole process. The label says BLOCK, the tooltip says why.
        self.block_toggled.emit(conn.process_name, want_blocked)


def _paint_bottom_rule(widget: QWidget, colour: str) -> None:
    p = QPainter(widget)
    p.fillRect(widget.rect(), QColor(theme.BG_WINDOW))
    p.fillRect(0, widget.height() - 1, widget.width(), 1, QColor(colour))
    p.end()


class _Rule(QWidget):
    def __init__(self, colour: str, height: int, parent=None) -> None:
        super().__init__(parent)
        self._colour = colour
        self.setFixedHeight(height)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(self._colour))
        p.end()
