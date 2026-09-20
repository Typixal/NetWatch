"""The frameless window, and the wiring between the core and the widgets."""

from __future__ import annotations

import time

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSizeGrip,
    QVBoxLayout,
    QWidget,
)

from netwatch.core.dns_resolver import DNSResolver
from netwatch.core.elevation import ElevatingBackend, ElevationCancelled, ElevationFailed
from netwatch.core.firewall import FirewallManager
from netwatch.core.history import HistoryTracker
from netwatch.core.poller import DEFAULT_INTERVAL_MS, NetworkPoller
from netwatch.core.store import ConnectionStore, ProcessGroup
from netwatch.ui import theme
from netwatch.ui.detail_pane import DetailPane
from netwatch.ui.process_list import ProcessList
from netwatch.ui.summary_bar import SummaryBar
from netwatch.ui.title_bar import TitleBar

RESIZE_MARGIN = 6


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NetWatch")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(theme.WINDOW_MIN_WIDTH, theme.WINDOW_MIN_HEIGHT)
        self._quitting = False
        self._last_update = time.monotonic()

        # — core —
        self._dns = DNSResolver(self)
        self._firewall = FirewallManager(ElevatingBackend())
        self._store = ConnectionStore(self._firewall)
        self._history = HistoryTracker()
        self._groups: list[ProcessGroup] = []

        dropped = self._firewall.sync_with_firewall()
        if dropped:
            # Rules vanished while we weren't running. The list is now honest.
            print(f"blocklist reconciled, dropped: {', '.join(dropped)}")

        # — widgets —
        central = QWidget(self)
        central.setObjectName("root")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        interval_s = DEFAULT_INTERVAL_MS // 1000
        self.title_bar = TitleBar(interval_s, central)
        self.title_bar.minimise_requested.connect(self.showMinimized)
        self.title_bar.maximise_requested.connect(self._toggle_maximised)
        self.title_bar.close_requested.connect(self.close)
        outer.addWidget(self.title_bar)

        self.summary = SummaryBar(central)
        outer.addWidget(self.summary)

        body = QWidget(central)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = ProcessList(body)
        self.sidebar.process_selected.connect(self._on_process_selected)
        self.sidebar.block_toggled.connect(self._on_block_requested)
        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(_VRule(theme.BORDER_HARD, 2, body))

        self.detail = DetailPane(body)
        self.detail.block_toggled.connect(self._on_block_requested)
        body_layout.addWidget(self.detail, 1)

        outer.addWidget(body, 1)
        self.setCentralWidget(central)

        # Resize grip, since a frameless window has no frame to drag.
        self._grip = QSizeGrip(self)
        self._grip.resize(16, 16)

        # — polling —
        self._poller = NetworkPoller(self._dns, DEFAULT_INTERVAL_MS, self)
        self._poller.connections_updated.connect(self._on_update)
        self._dns.dns_resolved.connect(self._on_dns_resolved)
        self._poller.start()

        # Footer clock, so "last refreshed Ns ago" actually counts up.
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._update_footer)
        self._tick.start(1000)

    # — polling updates —

    def _on_update(self, groups: list[ProcessGroup]) -> None:
        enriched = self._store.update(groups)
        self._history.record(enriched)
        self._groups = enriched
        self._last_update = time.monotonic()

        self.summary.update_stats(
            enriched, len(self._firewall.blocked_processes())
        )
        self.sidebar.update_groups(enriched, self._history)
        self._refresh_detail()
        self._update_footer()

    def _on_dns_resolved(self, _ip: str, _domain: str) -> None:
        # Redraw the detail table so domains fill in between polls.
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        name = self.sidebar.selected_name()
        group = next((g for g in self._groups if g.name == name), None)
        series = self._history.series(name) if name else []
        stats = self._history.stats(name) if name else (0, 0, 0)
        self.detail.show_group(group, series, stats)

    def _on_process_selected(self, _name: str) -> None:
        self._refresh_detail()

    def _update_footer(self) -> None:
        total = sum(len(g.connections) for g in self._groups)
        ago = int(time.monotonic() - self._last_update)
        self.detail.set_footer(
            ago, self._poller.interval_ms // 1000, total, len(self._groups)
        )

    # — blocking —

    def _on_block_requested(self, process_name: str, want_blocked: bool) -> None:
        group = next((g for g in self._groups if g.name == process_name), None)
        exe = group.exe if group else None

        try:
            if want_blocked:
                ok = self._firewall.block(process_name, exe or None)
                failure = (
                    f"Could not block {process_name}.\n\n"
                    "Windows Firewall rules are per program, and the path to "
                    "this process could not be read — usually a protected "
                    "system process."
                    if not exe
                    else f"Windows Firewall rejected the rule for {process_name}."
                )
            else:
                ok = self._firewall.unblock(process_name)
                failure = f"Could not remove the firewall rule for {process_name}."
        except ElevationCancelled:
            # Dismissing UAC is a decision, not an error. Put the toggle back.
            self._refresh_all_toggles()
            return
        except ElevationFailed as exc:
            self._refresh_all_toggles()
            QMessageBox.warning(self, "NetWatch", f"Elevation failed.\n\n{exc}")
            return

        if not ok:
            self._refresh_all_toggles()
            QMessageBox.warning(self, "NetWatch", failure)
            return

        # Reflect the new state at once rather than waiting for the next poll.
        for g in self._groups:
            g.blocked = self._firewall.is_blocked(g.name)
        self.summary.update_stats(
            self._groups, len(self._firewall.blocked_processes())
        )
        self.sidebar.update_groups(self._groups, self._history)
        self._refresh_detail()

    def _refresh_all_toggles(self) -> None:
        """Re-assert the firewall's view onto every toggle."""
        for g in self._groups:
            g.blocked = self._firewall.is_blocked(g.name)
        self.sidebar.update_groups(self._groups, self._history)
        self._refresh_detail()

    # — window chrome —

    def _toggle_maximised(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._grip.move(
            self.width() - self._grip.width(), self.height() - self._grip.height()
        )

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG_WINDOW))
        p.setPen(QColor(theme.BORDER_HARD))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)
        p.end()

    # — lifecycle —

    def closeEvent(self, event) -> None:
        if self._quitting:
            event.accept()
            return
        # Closing hides to the tray; Quit in the tray menu really exits.
        event.ignore()
        self.hide()

    def show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def quit(self) -> None:
        self._quitting = True
        self._tick.stop()
        self.title_bar.set_live(False)
        self._poller.stop()
        self._poller.wait(3000)
        self._dns.shutdown()
        self._store.close()
        QApplication.quit()


class _VRule(QWidget):
    def __init__(self, colour: str, width: int, parent=None) -> None:
        super().__init__(parent)
        self._colour = colour
        self.setFixedWidth(width)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(self._colour))
        p.end()
