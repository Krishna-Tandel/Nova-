import sys
import os
import signal
import keyboard
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import QTimer, Qt, QObject, pyqtSignal
from ui.panel import Panel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(BASE_DIR, "assets", "icon.png")
HOTKEY = "ctrl+space"


def make_fallback_icon():
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


class HotkeySignals(QObject):
    toggle = pyqtSignal()


app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

signal.signal(signal.SIGINT, lambda *args: app.quit())
timer = QTimer()
timer.timeout.connect(lambda: None)
timer.start(200)

panel = Panel()
panel.dock()   # start hidden at the right edge

icon = QIcon(ICON_PATH)
if icon.isNull():
    icon = make_fallback_icon()
app.setWindowIcon(icon)

# --- System tray ---
tray = QSystemTrayIcon(icon, app)
tray.setToolTip("Nova")

menu = QMenu()
show_action = QAction("Show", menu)
quit_action = QAction("Quit", menu)
menu.addAction(show_action)
menu.addAction(quit_action)
tray.setContextMenu(menu)


def on_tray_click(reason):
    if reason == QSystemTrayIcon.ActivationReason.Trigger:
        panel.toggle()


show_action.triggered.connect(lambda: panel.slide_out(focus=True))
quit_action.triggered.connect(app.quit)
tray.activated.connect(on_tray_click)
tray.show()

# --- Global hotkey ---
hotkey_signals = HotkeySignals()
hotkey_signals.toggle.connect(panel.toggle)
keyboard.add_hotkey(HOTKEY, hotkey_signals.toggle.emit)
app.aboutToQuit.connect(keyboard.unhook_all)

sys.exit(app.exec())