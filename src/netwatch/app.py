"""QApplication bootstrap.

NetWatch starts unelevated on purpose. Monitoring works without admin (some
system processes simply report no PID and are skipped), and only firewall
writes prompt for elevation, one action at a time.
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import QLockFile, QDir
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from netwatch.ui import theme
from netwatch.ui.main_window import MainWindow
from netwatch.ui.tray import TrayIcon, tray_icon


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("NetWatch")
    app.setOrganizationName("NetWatch")
    app.setApplicationDisplayName("NetWatch")
    app.setWindowIcon(tray_icon())
    # Required for tray-only mode: hiding the window must not exit the app.
    app.setQuitOnLastWindowClosed(False)

    # One instance, or two pollers fight over the same log file.
    lock = QLockFile(QDir.tempPath() + "/netwatch.lock")
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(100):
        QMessageBox.information(
            None, "NetWatch", "NetWatch is already running — check the system tray."
        )
        return 0

    theme.load_fonts()
    app.setStyleSheet(theme.stylesheet())

    window = MainWindow()

    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = TrayIcon(window)
        tray.show()
    else:
        # Without a tray there's nowhere to minimise to, so closing must exit.
        app.setQuitOnLastWindowClosed(True)

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
