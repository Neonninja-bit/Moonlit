import sys
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QAction, QFont

app = QApplication(sys.argv)

app.setFont(QFont("Inter", 10))

from overlay import FullscreenOverlay
from backend import ClipboardWatcher, HotkeyThread

class TrayApp(QSystemTrayIcon):
    def __init__(self, app, overlay: FullscreenOverlay):
        super().__init__()
        self.app     = app
        self.overlay = overlay

        self.setIcon(app.style().standardIcon(
            app.style().StandardPixmap.SP_FileIcon))
        self.setToolTip("ClipVault — Clipboard History  (Ctrl+Shift+Q)")

        menu = QMenu()
        show_a = QAction("Open ClipVault  (Ctrl+Shift+Q)")
        show_a.triggered.connect(overlay.fade_in)
        menu.addAction(show_a)
        menu.addSeparator()
        
        clr_a = QAction("Clear History")
        clr_a.triggered.connect(overlay._clear_all)
        menu.addAction(clr_a)
        menu.addSeparator()
        
        quit_a = QAction("Quit")
        quit_a.triggered.connect(overlay._quit)
        menu.addAction(quit_a)

        self.setContextMenu(menu)
        self.activated.connect(self._click)
        self.show()

    def _click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.overlay.toggle_visibility()


if __name__ == "__main__":
    app.setQuitOnLastWindowClosed(False)

    overlay = FullscreenOverlay()
    
    watcher = ClipboardWatcher()
    watcher.new_item.connect(overlay.add_item)
    watcher.start()

    hotkey = HotkeyThread()
    hotkey.triggered.connect(overlay.toggle_visibility)
    hotkey.start()

    tray = TrayApp(app, overlay)

    def _quit():
        watcher.stop()
        hotkey.stop()
        watcher.wait(400)
        hotkey.wait(400)
        app.quit()

    overlay._quit = _quit

    sys.exit(app.exec())