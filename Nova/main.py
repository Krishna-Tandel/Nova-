import sys
import os
import signal
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import QTimer, Qt
from ui.panel import Panel

# Folder where main.py lives, so the icon path works from anywhere
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(BASE_DIR, "assets", "icon.png")


def make_fallback_icon():
    """Draws a purple 'N' icon in code, used if icon.png is missing."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#cba6f7"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setPen(QColor("#1e1e2e"))
    p.setFont(QFont("Arial", 34, QFont.Weight.Bold))
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "N")
    p.end()
    return QIcon(pix)


app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

# Make Ctrl+C in the terminal work
signal.signal(signal.SIGINT, lambda *args: app.quit())
timer = QTimer()
timer.timeout.connect(lambda: None)
timer.start(200)

panel = Panel()
panel.show()

# --- Icon (with diagnostics) ---
print("Icon path:", ICON_PATH)
print("File exists:", os.path.exists(ICON_PATH))
print("Tray available:", QSystemTrayIcon.isSystemTrayAvailable())

icon = QIcon(ICON_PATH)
if icon.isNull():
    print("icon.png not found or unreadable -> using fallback icon")
    icon = make_fallback_icon()

# --- System tray ---
tray = QSystemTrayIcon(icon, app)
tray.setToolTip("Nova")
app.setWindowIcon(icon)

menu = QMenu()
show_action = QAction("Show", menu)
quit_action = QAction("Quit", menu)
menu.addAction(show_action)
menu.addAction(quit_action)
tray.setContextMenu(menu)


def show_panel():
    panel.show()
    panel.raise_()
    panel.activateWindow()


def on_tray_click(reason):
    # Left-click toggles the panel
    if reason == QSystemTrayIcon.ActivationReason.Trigger:
        if panel.isVisible():
            panel.hide()
        else:
            show_panel()


show_action.triggered.connect(show_panel)
quit_action.triggered.connect(app.quit)
tray.activated.connect(on_tray_click)
tray.show()

sys.exit(app.exec())