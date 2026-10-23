import sys
import signal
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from ui.panel import Panel

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

# Make Ctrl+C in the terminal work
signal.signal(signal.SIGINT, lambda *args: app.quit())
timer = QTimer()
timer.timeout.connect(lambda: None)
timer.start(200)

panel = Panel()
panel.show()

sys.exit(app.exec())