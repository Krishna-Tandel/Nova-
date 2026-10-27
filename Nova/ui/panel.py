import html
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QTextBrowser, QApplication)
from PyQt6.QtCore import (Qt, QPropertyAnimation, QPoint, QEasingCurve,
                          QTimer, QEvent, QThread, pyqtSignal)
from core import winfocus
from core.actions import run_command, confirm_pending, cancel_pending
from core.voice import VoiceWorker, CONFIRM_PHRASES

STRIP = 8         # pixels still visible when the panel is hidden
MARGIN = 10       # gap from the screen edge when the panel is open
SLIDE_MS = 220    # slide animation time
HIDE_DELAY = 400  # wait before sliding back in after the mouse leaves

NORMAL_HINT = "Type a command..."
CONFIRM_HINT = "Say or type yes / no..."

YES_WORDS = {"yes", "y", "yes confirm"}
# These need the longer phrase "yes confirm" when answered by voice
STRICT_VOICE = {"shutdown", "restart"}


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


class HistoryLineEdit(QLineEdit):
    """Text box where Up and Down recall earlier commands."""

    def __init__(self):
        super().__init__()
        self.history = []
        self.idx = 0
        self.draft = ""

    def remember(self, text):
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)
        self.idx = len(self.history)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Up and self.history:
            if self.idx == len(self.history):
                self.draft = self.text()
            self.idx = max(0, self.idx - 1)
            self.setText(self.history[self.idx])
        elif key == Qt.Key.Key_Down and self.history:
            if self.idx < len(self.history):
                self.idx += 1
                if self.idx == len(self.history):
                    self.setText(self.draft)
                else:
                    self.setText(self.history[self.idx])
        else:
            super().keyPressEvent(event)


class Panel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nova")
        self.resize(420, 440)
        self.expanded = False
        self.worker = None
        self.voice = None
        self.pending = None           # an action waiting for yes / no
        self.spoken_text = None       # text heard by voice, run after the mic thread ends
        self.confirm_by_voice = False # the command was spoken, so listen for the answer too

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # --- Header: title + status ---
        self.title = QLabel("Nova")
        self.title.setObjectName("title")
        self.status = QLabel("Ready")
        self.status.setObjectName("status")

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.status)

        # --- Chat history ---
        self.chat = QTextBrowser()
        self.chat.setObjectName("chat")
        self.chat.setOpenLinks(False)
        self.chat.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # --- Input row: text box + mic ---
        self.input = HistoryLineEdit()
        self.input.setPlaceholderText(NORMAL_HINT)
        self.input.returnPressed.connect(self.on_enter)

        self.mic = QPushButton("🎤")
        self.mic.setObjectName("mic")
        self.mic.setToolTip("Speak a command (Ctrl+Alt+Space)")
        self.mic.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic.clicked.connect(self.start_voice)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.input, 1)
        row.addWidget(self.mic)

        # --- Main layout ---
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 18, 18, 18)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.chat, 1)
        layout.addLayout(row)
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
            QLabel#status {
                color: #9399b2;
                font-size: 12px;
            }
            QTextBrowser#chat {
                background-color: #181825;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 10px;
                padding: 6px;
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
            QPushButton#mic {
                background-color: #313244;
                border: 1px solid #45475a;
                border-radius: 10px;
                font-size: 16px;
                min-width: 44px;
                max-width: 44px;
                padding: 6px;
            }
            QPushButton#mic:hover {
                border: 1px solid #cba6f7;
            }
            QPushButton#mic:disabled {
                background-color: #cba6f7;
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

        # --- Timer that remembers your last window (so "type ..." knows where to type) ---
        self.track_timer = QTimer(self)
        self.track_timer.setInterval(250)
        self.track_timer.timeout.connect(lambda: winfocus.track(int(self.winId())))
        self.track_timer.start()

        self.add_message("nova", "How can I help you? Type a command, or press the mic and speak.")

    # ---------- Chat display ----------
    def add_message(self, who, text):
        safe = html.escape(text).replace("\n", "<br>")
        color = "#cba6f7" if who == "you" else "#a6e3a1"
        name = "You" if who == "you" else "Nova"
        self.chat.append(
            f'<p style="margin-top:6px; margin-bottom:6px;">'
            f'<span style="color:{color};"><b>{name}</b></span><br>'
            f'<span style="color:#cdd6f4;">{safe}</span></p>'
        )
        # Scroll to the newest message (after the layout has updated)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        bar = self.chat.verticalScrollBar()
        bar.setValue(bar.maximum())

    def set_status(self, text):
        self.status.setText(text)
        color = {"Listening...": "#a6e3a1", "Thinking...": "#f9e2af"}.get(text)
        self.status.setStyleSheet(f"color: {color};" if color else "")

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

    def _thinking(self):
        return self.worker is not None and self.worker.isRunning()

    def _listening(self):
        return self.voice is not None and self.voice.isRunning()

    def try_collapse(self):
        # Stay open while the mouse is over the panel, you are typing, or Nova is busy
        if self.underMouse() or self.input.hasFocus() or self._thinking() or self._listening():
            return
        self.slide_in()

    # ---------- Confirmation ----------
    def _clear_pending(self):
        if self.pending is not None:
            cancel_pending(self.pending)
            self.pending = None
            self.confirm_by_voice = False
            self.input.setPlaceholderText(NORMAL_HINT)

    # ---------- Sending a command (typed or spoken) ----------
    def on_enter(self):
        text = self.input.text().strip()
        if not text:
            return
        if self._thinking() or self._listening():
            return
        self.input.clear()
        self.submit(text)

    def submit(self, text, spoken=False):
        text = text.strip()
        if not text:
            return
        if self._thinking():
            self.add_message("nova", "Still working on the last command...")
            return

        self.input.remember(text)
        self.add_message("you", ("🎤 " if spoken else "") + text)

        # An action is waiting for yes / no
        if self.pending is not None:
            answer = text.lower()
            kind = self.pending["kind"]

            if answer in YES_WORDS:
                # shutdown / restart by voice need the longer phrase "yes confirm"
                if spoken and kind in STRICT_VOICE and answer != "yes confirm":
                    self.add_message("nova", f"To {kind} by voice, say \"yes confirm\". "
                                             f"Or type yes.")
                    QTimer.singleShot(400, self.start_voice)  # listen again, still waiting
                    return
                pending, self.pending = self.pending, None
                self.confirm_by_voice = False
                self.input.setPlaceholderText(NORMAL_HINT)
                self.add_message("nova", confirm_pending(pending))
            else:
                pending, self.pending = self.pending, None
                self.confirm_by_voice = False
                self.input.setPlaceholderText(NORMAL_HINT)
                self.add_message("nova", cancel_pending(pending))
            self.set_status("Ready")
            return

        # A new command: remember if it was spoken, so Nova can listen for the answer
        self.confirm_by_voice = spoken
        self.set_status("Thinking...")
        self.worker = CommandWorker(text)
        self.worker.done.connect(self.show_reply)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def show_reply(self, text, pending):
        self.pending = pending
        if pending is not None:
            self.input.setPlaceholderText(CONFIRM_HINT)
            if self.confirm_by_voice:
                phrase = "yes confirm" if pending["kind"] in STRICT_VOICE else "yes"
                text += f"\nListening for your answer: say \"{phrase}\" or \"no\"."
        self.add_message("nova", text)
        self.set_status("Ready")

    def on_worker_finished(self):
        # The command thread has fully ended. If it needs an answer, listen for it.
        if self.confirm_by_voice and self.pending is not None:
            self.confirm_by_voice = False
            QTimer.singleShot(200, self.start_voice)

    # ---------- Voice ----------
    def start_voice(self):
        if self._thinking() or self._listening():
            return
        self.spoken_text = None
        self.slide_out()
        self.mic.setEnabled(False)
        self.set_status("Starting mic...")
        # While waiting for an answer, listen only for yes / no
        phrases = CONFIRM_PHRASES if self.pending is not None else None
        self.voice = VoiceWorker(phrases)
        self.voice.status.connect(self.set_status)
        self.voice.heard.connect(self.on_voice_heard)
        self.voice.failed.connect(self.on_voice_failed)
        self.voice.finished.connect(self.on_voice_finished)
        self.voice.start()

    def on_voice_heard(self, text):
        # Just remember it. It runs when the mic thread has fully finished.
        self.spoken_text = text

    def on_voice_failed(self, message):
        self.add_message("nova", message)
        self.set_status("Ready")

    def on_voice_finished(self):
        self.mic.setEnabled(True)
        text, self.spoken_text = self.spoken_text, None
        if text:
            self.set_status("Ready")
            QTimer.singleShot(0, lambda: self.submit(text, spoken=True))

    def shutdown_workers(self):
        """Called when Nova quits, so no background thread is left running."""
        for thread in (self.voice, self.worker):
            if thread is not None and thread.isRunning():
                thread.requestInterruption()
                thread.wait(1500)

    # ---------- Keys ----------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.slide_in()