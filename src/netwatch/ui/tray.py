"""System tray icon: show, run-on-startup, quit."""

from __future__ import annotations

from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from netwatch.ui import theme
from netwatch.utils.paths import asset_path
from netwatch.utils.startup import is_startup_enabled, toggle_startup


def tray_icon() -> QIcon:
    """The bundled icon, or a drawn stand-in if assets are missing."""
    ico = asset_path("icon.ico")
    if ico.exists():
        return QIcon(str(ico))

    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor(theme.BG_TITLE))
    p = QPainter(pixmap)
    p.fillRect(6, 6, 20, 20, QColor(theme.ACCENT))
    p.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._window = window
        self.setIcon(tray_icon())
        self.setToolTip("NetWatch")

        menu = QMenu()

        show = QAction("Show NetWatch", menu)
        show.triggered.connect(self._window.show_window)
        menu.addAction(show)

        menu.addSeparator()

        self._startup = QAction("Run on startup", menu)
        self._startup.setCheckable(True)
        self._startup.setChecked(is_startup_enabled())
        self._startup.triggered.connect(self._toggle_startup)
        menu.addAction(self._startup)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._window.quit)
        menu.addAction(quit_action)

        self._menu = menu  # keep a reference; Qt won't hold it for us
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _toggle_startup(self) -> None:
        # Show what the registry actually says, not what was clicked.
        toggle_startup()
        self._startup.setChecked(is_startup_enabled())

    def _on_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self._window.show_window()
