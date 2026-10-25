from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QApplication
from PyQt6.QtCore import (Qt, QPropertyAnimation, QPoint, QEasingCurve,
                          QTimer, QEvent, QThread, pyqtSignal)
from core.actions import run_command, confirm_pending, cancel_pending

STRIP = 8         # pixels still visible when the panel is hidden
MARGIN = 10       # gap from the screen edge when the panel is open
SLIDE_MS = 220    # slide animation time
HIDE_DELAY = 400  # wait before sliding back in after the mouse leaves

NORMAL_HINT = "Type a command..."
CONFIRM_HINT = "Type yes or no..."


class CommandWorker(QThread):
    """Runs a command in the background so the UI never freezes."""
    done = pyqtSignal(str, object)

    def __init__(self, text):
        super().__init__()
        self.text = text

    def run(self):
        try:
            reply, pending = run_command(self.text)
            self.done.emit(reply, pending)
        except Exception as e:
            self.done.emit(f"Error: {type(e).__name__}", None)


class Panel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nova")
        self.resize(420, 220)
        self.expanded = False
        self.worker = None
        self.pending = None   # an action waiting for yes / no

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # --- Layout ---
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 20, 20)
        layout.setSpacing(12)

        self.title = QLabel("Nova")
        self.title.setObjectName("title")

        self.reply = QLabel("How can I help you?")
        self.reply.setObjectName("reply")
        self.reply.setWordWrap(True)
        self.reply.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.input = QLineEdit()
        self.input.setPlaceholderText(NORMAL_HINT)
        self.input.returnPressed.connect(self.on_enter)

        layout.addWidget(self.title)
        layout.addWidget(self.reply, 1)
        layout.addWidget(self.input)
        self.setLayout(layout)

        self.setStyleSheet("""
            Panel {
                background-color: #1e1e2e;
                border: 2px solid #cba6f7;
                border-radius: 18px;
            }
            QLabel#title {
                color: #cba6f7;
                font-size: 18px;
                font-weight: bold;
            }
            QLabel#reply {
                color: #cdd6f4;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 10px;
                padding: 8px 12px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #cba6f7;
            }
        """)

        # --- Slide animation ---
        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(SLIDE_MS)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # --- Timer that slides the panel back in ---
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(HIDE_DELAY)
        self.hide_timer.timeout.connect(self.try_collapse)

    # ---------- Positions ----------
    def _points(self):
        screen = QApplication.primaryScreen().availableGeometry()
        edge = screen.right() + 1
        y = screen.top() + (screen.height() - self.height()) // 2
        open_pos = QPoint(edge - self.width() - MARGIN, y)
        closed_pos = QPoint(edge - STRIP, y)
        return open_pos, closed_pos

    def _move_to(self, point):
        self.anim.stop()
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(point)
        self.anim.start()

    # ---------- Public actions ----------
    def dock(self):
        """Start hidden at the edge (only the strip is visible)."""
        _, closed_pos = self._points()
        self.move(closed_pos)
        self.show()
        self.expanded = False

    def slide_out(self, focus=False):
        self.hide_timer.stop()
        open_pos, _ = self._points()
        self.expanded = True
        self.show()
        self.raise_()
        self._move_to(open_pos)
        if focus:
            self.activateWindow()
            self.input.setFocus()

    def slide_in(self):
        # A waiting confirmation is cancelled when the panel hides,
        # so a stray "yes" later can never trigger it
        self._clear_pending()
        _, closed_pos = self._points()
        self.expanded = False
        self.input.clearFocus()
        self._move_to(closed_pos)

    def toggle(self):
        if self.expanded:
            self.slide_in()
        else:
            self.slide_out(focus=True)

    # ---------- Hover logic ----------
    def enterEvent(self, event):
        self.hide_timer.stop()
        if not self.expanded:
            self.slide_out()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.expanded:
            self.hide_timer.start()
        super().leaveEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if self.expanded and not self.isActiveWindow():
                self.hide_timer.start()
        super().changeEvent(event)

    def try_collapse(self):
        busy = self.worker is not None and self.worker.isRunning()
        if self.underMouse() or self.input.hasFocus() or busy:
            return
        self.slide_in()

    # ---------- Confirmation ----------
    def _clear_pending(self):
        if self.pending is not None:
            cancel_pending(self.pending)
            self.pending = None
            self.input.setPlaceholderText(NORMAL_HINT)

    # ---------- Input ----------
    def on_enter(self):
        text = self.input.text().strip()
        if not text:
            return
        if self.worker is not None and self.worker.isRunning():
            return
        self.input.clear()

        # An action is waiting for yes / no
        if self.pending is not None:
            pending, self.pending = self.pending, None
            self.input.setPlaceholderText(NORMAL_HINT)
            if text.lower() in ("yes", "y"):
                self.reply.setText(confirm_pending(pending))
            else:
                self.reply.setText(cancel_pending(pending))
            return

        self.reply.setText("Thinking...")
        self.worker = CommandWorker(text)
        self.worker.done.connect(self.show_reply)
        self.worker.start()

    def show_reply(self, text, pending):
        self.reply.setText(text)
        self.pending = pending
        if pending is not None:
            self.input.setPlaceholderText(CONFIRM_HINT)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.slide_in()