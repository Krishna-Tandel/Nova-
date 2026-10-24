from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QApplication
from PyQt6.QtCore import Qt, QPropertyAnimation, QPoint, QEasingCurve, QTimer, QEvent

STRIP = 8        # pixels still visible when the panel is hidden
MARGIN = 10      # gap from the screen edge when the panel is open
SLIDE_MS = 220   # slide animation time
HIDE_DELAY = 400 # wait before sliding back in after the mouse leaves


class Panel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nova")
        self.resize(420, 220)
        self.expanded = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Needed so the stylesheet background actually paints
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
        self.input.setPlaceholderText("Type a command...")
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
        # Lost focus (clicked another app): schedule a slide back in
        if event.type() == QEvent.Type.ActivationChange:
            if self.expanded and not self.isActiveWindow():
                self.hide_timer.start()
        super().changeEvent(event)

    def try_collapse(self):
        # Stay open while the mouse is over the panel or you are typing
        if self.underMouse() or self.input.hasFocus():
            return
        self.slide_in()

    # ---------- Input ----------
    def on_enter(self):
        text = self.input.text().strip()
        if text:
            self.reply.setText(f"You said: {text}")
            self.input.clear()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.slide_in()