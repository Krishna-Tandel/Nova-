import math
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QFrame, QApplication,
                             QGraphicsOpacityEffect)
from PyQt6.QtCore import (Qt, QObject, QPropertyAnimation, QParallelAnimationGroup,
                          QVariantAnimation, QPoint, QPointF, QRect, QRectF,
                          QEasingCurve, QTimer, QEvent, QThread, pyqtSignal)
from PyQt6.QtGui import QPainter, QColor, QPen, QFontMetrics
from core import winfocus
from core.actions import run_command, confirm_pending, cancel_pending
from core.voice import VoiceWorker, CONFIRM_PHRASES

# ---------------- Settings you can change ----------------
WIDTH = 430            # window width (includes the glow around the card)
HEIGHT = 500           # window height
STRIP = 8              # pixels of the card still visible when the panel is hidden
MARGIN = 10            # gap from the screen edge when the panel is open
SHADOW = 14            # size of the soft glow around the card
RADIUS = 20            # roundness of the card corners
HIDE_DELAY = 400       # wait before sliding away after the mouse leaves
BUBBLE_MAX = 270       # widest a chat bubble can be

SPRING = True          # iOS-style springy slide-in (False = smooth, no bounce)
SPRING_DAMPING = 0.7   # lower = bouncier (0.5 very bouncy, 0.9 almost none)
SLIDE_OUT_MS = 420     # coming-in time (a spring needs a little longer)
SLIDE_IN_MS = 260      # going-away time
FADE_CLOSED = 0.6      # how see-through the hidden strip is (1.0 = solid)

# ---------------- Colors ----------------
BG = "#1e1e2e"
PURPLE = "#cba6f7"
GREEN = "#a6e3a1"
YELLOW = "#f9e2af"
TEXT = "#cdd6f4"
SUBTEXT = "#9399b2"
SURFACE = "#313244"
SURFACE_HOVER = "#45475a"

STATE_COLORS = {"idle": PURPLE, "listening": GREEN, "thinking": YELLOW}

NORMAL_HINT = "Type a command..."
CONFIRM_HINT = "Say or type yes / no..."

# Quick buttons shown until you send your first command
CHIPS = [
    ("📝 Notepad", "open notepad"),
    ("🔊 Volume up", "volume up"),
    ("📸 Screenshot", "take a screenshot"),
    ("❓ Help", "help"),
]

YES_WORDS = {"yes", "y", "yes confirm"}
# These need the longer phrase "yes confirm" when answered by voice
STRICT_VOICE = {"shutdown", "restart"}


# ---------------- Animation helpers ----------------
def spring_progress(t):
    """iOS-style spring: runs a little past 1.0, then settles back."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    z = SPRING_DAMPING
    settle = 6.0
    wd = (settle / z) * math.sqrt(1.0 - z * z)
    return 1.0 - math.exp(-settle * t) * (math.cos(wd * t) + (settle / wd) * math.sin(wd * t))


def spring_curve():
    curve = QEasingCurve()
    curve.setCustomType(spring_progress)
    return curve


def mix(a, b, t):
    """Blends two colors. t=0 gives a, t=1 gives b."""
    a, b = QColor(a), QColor(b)
    t = max(0.0, min(1.0, t))
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


class Tween(QObject):
    """Smoothly moves a number toward a target (used for hover, press, fades)."""
    changed = pyqtSignal()

    def __init__(self, value=0.0, parent=None):
        super().__init__(parent)
        self.value = value
        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_value)

    def to(self, target, ms=160, kind=QEasingCurve.Type.InOutCubic):
        self._anim.stop()
        self._anim.setDuration(ms)
        self._anim.setEasingCurve(kind)
        self._anim.setStartValue(float(self.value))
        self._anim.setEndValue(float(target))
        self._anim.start()

    def _on_value(self, v):
        self.value = float(v)
        self.changed.emit()


class ColorFader(QObject):
    """A color that crossfades to a new color instead of jumping."""
    changed = pyqtSignal()

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(300)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.valueChanged.connect(self._on_value)

    def fade_to(self, color):
        self._anim.stop()
        self._anim.setStartValue(QColor(self.color))
        self._anim.setEndValue(QColor(color))
        self._anim.start()

    def _on_value(self, v):
        self.color = QColor(v)
        self.changed.emit()


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


class MicButton(QPushButton):
    """Round mic button. Pulses green while listening, spins yellow while thinking.
    Shrinks slightly when pressed and pops back when released."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(52, 52)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("Speak a command (Ctrl+Alt+Space). Click again to stop listening.")
        self.state = "idle"
        self._shape = "listening"      # which effect to draw while it fades out
        self._phase = 0.0
        self._color = ColorFader(PURPLE, self)
        self._active = Tween(0.0, self)   # 0 = idle look, 1 = listening / thinking look
        self._hover = Tween(0.0, self)
        self._press = Tween(0.0, self)
        for obj in (self._color, self._active, self._hover, self._press):
            obj.changed.connect(self.update)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def set_state(self, state):
        if state == self.state:
            return
        self.state = state
        self._color.fade_to(STATE_COLORS[state])
        if state == "idle":
            self._active.to(0.0, 260)
        else:
            self._shape = state
            self._active.to(1.0, 220)
            if not self._timer.isActive():
                self._timer.start()

    def _tick(self):
        self._phase = (self._phase + 0.025) % 1.0
        # Keep animating until the effect has faded out, then stop to save power
        if self.state == "idle" and self._active.value < 0.01:
            self._timer.stop()
            self._phase = 0.0
        self.update()

    def enterEvent(self, event):
        self._hover.to(1.0, 140)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover.to(0.0, 220)
        self._press.to(0.0, 160)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._press.to(1.0, 90)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._press.to(0.0, 340, QEasingCurve.Type.OutBack)   # springs back
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        base_r = 17
        color = self._color.color
        active = max(0.0, min(1.0, self._active.value))

        if active > 0.01 and self._shape == "listening":
            # Two rings that grow outward and fade, like a sound wave
            for k in range(2):
                t = (self._phase + k * 0.5) % 1.0
                r = base_r + t * (min(cx, cy) - base_r - 1)
                ring = QColor(color)
                ring.setAlpha(int(170 * (1 - t) * active))
                p.setPen(QPen(ring, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, cy), r, r)

        if active > 0.01 and self._shape == "thinking":
            # A short arc that spins around the button
            arc = QColor(color)
            arc.setAlpha(int(255 * active))
            pen = QPen(arc, 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            rr = base_r + 5
            p.drawArc(QRectF(cx - rr, cy - rr, rr * 2, rr * 2),
                      int(-self._phase * 360 * 16), 100 * 16)

        # Press feedback: the button itself shrinks a little
        scale = 1.0 - 0.10 * self._press.value
        p.translate(cx, cy)
        p.scale(scale, scale)
        p.translate(-cx, -cy)

        idle_fill = mix(SURFACE, SURFACE_HOVER, self._hover.value)
        fill = mix(idle_fill, color, active)
        glyph = mix(color, BG, active)
        p.setPen(QPen(color, 1.5))
        p.setBrush(fill)
        p.drawEllipse(QPointF(cx, cy), base_r, base_r)

        # Microphone drawn with shapes (no font needed)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glyph)
        p.drawRoundedRect(QRectF(cx - 4, cy - 9, 8, 13), 4, 4)
        pen = QPen(glyph, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(cx - 7, cy - 8, 14, 14), 180 * 16, 180 * 16)
        p.drawLine(QPointF(cx, cy + 6), QPointF(cx, cy + 9))
        p.drawLine(QPointF(cx - 3.5, cy + 9), QPointF(cx + 3.5, cy + 9))


class StatusPill(QWidget):
    """Small pill in the header: a dot (pulses when busy) and the status text."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(136, 26)
        self.state = "idle"
        self.text = "Ready"
        self._phase = 0.0
        self._color = ColorFader(SUBTEXT, self)
        self._active = Tween(0.0, self)
        for obj in (self._color, self._active):
            obj.changed.connect(self.update)
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def set_state(self, state, text):
        self.text = text
        if state != self.state:
            self.state = state
            self._color.fade_to(SUBTEXT if state == "idle" else STATE_COLORS[state])
            if state == "idle":
                self._active.to(0.0, 240)
            else:
                self._active.to(1.0, 200)
                if not self._timer.isActive():
                    self._timer.start()
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.04) % 1.0
        if self.state == "idle" and self._active.value < 0.01:
            self._timer.stop()
            self._phase = 0.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._color.color
        active = max(0.0, min(1.0, self._active.value))

        bg = QColor(color)
        bg.setAlpha(30)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 13, 13)

        pulse = 0.5 + 0.5 * math.sin(self._phase * 2 * math.pi)
        dot = QColor(color)
        dot.setAlpha(int(255 - active * 145 * (1 - pulse)))
        p.setBrush(dot)
        p.drawEllipse(QPointF(14, self.height() / 2), 4, 4)

        p.setPen(color)
        font = self.font()
        font.setPointSize(9)
        p.setFont(font)
        p.drawText(QRectF(26, 0, self.width() - 32, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text)


class TypingDots(QWidget):
    """Three bouncing dots in a bubble, like the 'typing...' bubble in iMessage."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(64, 36)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._phase = (self._phase + 0.03) % 1.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(SURFACE))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 14, 14)
        for i in range(3):
            wave = max(0.0, math.sin((self._phase - i * 0.12) * 2 * math.pi))
            dot = QColor(TEXT)
            dot.setAlpha(int(110 + 145 * wave))
            p.setBrush(dot)
            p.drawEllipse(QPointF(20 + i * 12, self.height() / 2 - 4 * wave), 3.5, 3.5)


class Panel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nova")
        self.resize(WIDTH, HEIGHT)
        self.expanded = False
        self.worker = None
        self.voice = None
        self.pending = None            # an action waiting for yes / no
        self.spoken_text = None        # text heard by voice, run after the mic thread ends
        self.confirm_by_voice = False  # the command was spoken, so listen for the answer too
        self._typing_row = None        # the "typing..." bubble while Nova is working
        self._chips_hidden = False
        self.accent_fader = ColorFader(PURPLE, self)   # border and glow color
        self.accent_fader.changed.connect(self.update)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # --- Header: logo, title, status ---
        self.logo = QLabel("N")
        self.logo.setObjectName("logo")
        self.logo.setFixedSize(30, 30)
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel("Nova")
        self.title.setObjectName("title")
        self.status = StatusPill()

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(self.logo)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.status)

        # --- Chat area (scrolls, bubbles are added to it) ---
        self.chat_host = QWidget()
        self.chat_host.setObjectName("chatHost")
        self.chat_layout = QVBoxLayout(self.chat_host)
        self.chat_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_layout.setSpacing(8)
        self.chat_layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("chatScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll.setWidget(self.chat_host)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._stick_to_bottom)

        self.chat_box = QFrame()
        self.chat_box.setObjectName("chatBox")
        box_layout = QVBoxLayout(self.chat_box)
        box_layout.setContentsMargins(3, 3, 3, 3)
        box_layout.addWidget(self.scroll)

        # --- Quick buttons (fade in one by one, collapse after your first command) ---
        self.chips = QWidget()
        chip_row = QHBoxLayout(self.chips)
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(6)
        chip_buttons = []
        for label, command in CHIPS:
            btn = QPushButton(label)
            btn.setObjectName("chip")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _checked=False, c=command: self.on_chip(c))
            chip_row.addWidget(btn)
            chip_buttons.append(btn)
        chip_row.addStretch(1)

        # --- Input row: text box + mic ---
        self.input = HistoryLineEdit()
        self.input.setPlaceholderText(NORMAL_HINT)
        self.input.setMinimumHeight(42)
        self.input.returnPressed.connect(self.on_enter)

        self.mic = MicButton()
        self.mic.clicked.connect(self.on_mic_clicked)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.input, 1)
        row.addWidget(self.mic)

        # --- Main layout ---
        layout = QVBoxLayout()
        layout.setContentsMargins(SHADOW + 18, SHADOW + 14, SHADOW + 14, SHADOW + 14)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.chat_box, 1)
        layout.addWidget(self.chips)
        layout.addLayout(row)
        self.setLayout(layout)

        self.setStyleSheet("""
            QLabel#logo {
                background-color: #cba6f7;
                color: #1e1e2e;
                font-size: 17px;
                font-weight: bold;
                border-radius: 9px;
            }
            QLabel#title {
                color: #cdd6f4;
                font-size: 18px;
                font-weight: bold;
            }
            QFrame#chatBox {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 14px;
            }
            QScrollArea#chatScroll { background: transparent; border: none; }
            QWidget#qt_scrollarea_viewport { background: transparent; }
            QWidget#chatHost { background: transparent; }
            QScrollBar:vertical { background: transparent; width: 6px; margin: 4px 2px; }
            QScrollBar::handle:vertical {
                background: #45475a; border-radius: 3px; min-height: 24px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

            QLabel#bubbleYou {
                background-color: #cba6f7;
                color: #1e1e2e;
                border-radius: 14px;
                border-bottom-right-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
            }
            QLabel#bubbleNova {
                background-color: #313244;
                color: #cdd6f4;
                border-radius: 14px;
                border-bottom-left-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
            }
            QLabel#bubbleAsk {
                background-color: #3a3730;
                color: #f9e2af;
                border: 1px solid #f9e2af;
                border-radius: 14px;
                border-bottom-left-radius: 4px;
                padding: 8px 12px;
                font-size: 14px;
            }

            QPushButton#chip {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 13px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QPushButton#chip:hover { border: 1px solid #cba6f7; }

            QLineEdit {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 14px;
                padding: 8px 14px;
                font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #cba6f7; }
            QLineEdit[state="listening"] { border: 1px solid #a6e3a1; }
            QLineEdit[state="thinking"] { border: 1px solid #f9e2af; }
        """)

        # --- Slide + fade animation (coming in and going away) ---
        self.pos_anim = QPropertyAnimation(self, b"pos")
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.group = QParallelAnimationGroup(self)
        self.group.addAnimation(self.pos_anim)
        self.group.addAnimation(self.fade_anim)

        # --- Timer that slides the panel away ---
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(HIDE_DELAY)
        self.hide_timer.timeout.connect(self.try_collapse)

        # --- Timer that remembers your last window (so "type ..." knows where to type) ---
        self.track_timer = QTimer(self)
        self.track_timer.setInterval(250)
        self.track_timer.timeout.connect(lambda: winfocus.track(int(self.winId())))
        self.track_timer.start()

        self.add_message("nova", "Hi! I'm Nova. Type a command, press a quick button, "
                                 "or click the mic and speak.")
        for i, btn in enumerate(chip_buttons):
            self._fade_in_later(btn, 350 + i * 80)

    # The border and glow color (it crossfades when Nova's state changes)
    @property
    def accent(self):
        return self.accent_fader.color

    # ---------- Drawing the card and its glow ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(SHADOW, SHADOW, self.width() - 2 * SHADOW, self.height() - 2 * SHADOW)
        accent = self.accent

        # Soft glow: layers that get fainter the further they are from the card
        for i in range(1, SHADOW + 1):
            glow = QColor(accent)
            glow.setAlpha(int(40 * (1 - (i - 1) / SHADOW) ** 2))
            p.setPen(QPen(glow, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(card.adjusted(-i, -i, i, i), RADIUS + i, RADIUS + i)

        p.setPen(QPen(accent, 2))
        p.setBrush(QColor(BG))
        p.drawRoundedRect(card.adjusted(1, 1, -1, -1), RADIUS, RADIUS)

    # ---------- Small animation helpers ----------
    def _fade_in_later(self, widget, delay_ms):
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)
        anim = QVariantAnimation(widget)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(260)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda v: effect.setOpacity(float(v)))
        anim.finished.connect(lambda: widget.setGraphicsEffect(None))
        QTimer.singleShot(delay_ms, anim.start)

    def _grow_row(self, row, target, ms=300):
        """New chat rows grow from nothing, pushing the chat up smoothly while they fade in."""
        row.setFixedHeight(0)
        effect = QGraphicsOpacityEffect(row)
        effect.setOpacity(0.0)
        row.setGraphicsEffect(effect)
        anim = QVariantAnimation(row)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(ms)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def step(v):
            v = float(v)
            row.setFixedHeight(max(0, int(target * v)))
            effect.setOpacity(min(1.0, v * 1.8))

        def done():
            row.setMinimumHeight(0)
            row.setMaximumHeight(16777215)
            row.setGraphicsEffect(None)

        anim.valueChanged.connect(step)
        anim.finished.connect(done)
        row._grow_anim = anim
        anim.start()

    def _shrink_and_remove(self, row, ms=180):
        old = getattr(row, "_grow_anim", None)
        if old is not None:
            old.stop()
        start_height = max(1, row.height())
        effect = QGraphicsOpacityEffect(row)
        row.setGraphicsEffect(effect)
        anim = QVariantAnimation(row)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setDuration(ms)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        def step(v):
            v = float(v)
            row.setFixedHeight(max(0, int(start_height * v)))
            effect.setOpacity(v)

        def done():
            row.hide()
            row.deleteLater()

        anim.valueChanged.connect(step)
        anim.finished.connect(done)
        anim.start()

    def _show_typing(self):
        if self._typing_row is not None:
            return
        dots = TypingDots()
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(dots)
        h.addStretch(1)
        row.setFixedHeight(0)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)
        self._typing_row = row
        self._grow_row(row, dots.height(), 240)

    def _hide_typing(self):
        row, self._typing_row = self._typing_row, None
        if row is not None:
            self._shrink_and_remove(row)

    def _hide_chips(self):
        if self._chips_hidden:
            return
        self._chips_hidden = True
        start_height = self.chips.height()
        if start_height <= 0 or not self.chips.isVisible():
            self.chips.hide()
            return
        effect = QGraphicsOpacityEffect(self.chips)
        self.chips.setGraphicsEffect(effect)
        anim = QVariantAnimation(self.chips)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setDuration(240)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        def step(v):
            v = float(v)
            self.chips.setFixedHeight(max(0, int(start_height * v)))
            effect.setOpacity(v)

        anim.valueChanged.connect(step)
        anim.finished.connect(self.chips.hide)
        anim.start()

    # ---------- Chat display ----------
    def add_message(self, who, text):
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setObjectName({"you": "bubbleYou", "ask": "bubbleAsk"}.get(who, "bubbleNova"))

        # Qt guesses badly for wrapped labels, so measure the text ourselves.
        # Short messages stay on one line, long ones wrap at BUBBLE_MAX.
        font = label.font()
        font.setPixelSize(14)
        label.setFont(font)
        metrics = QFontMetrics(font)
        border = 2 if who == "ask" else 0
        widest = max(metrics.horizontalAdvance(line) for line in text.split("\n"))
        width = min(BUBBLE_MAX, widest + 24 + border + 8)
        text_width = width - 24 - border
        wrapped = metrics.boundingRect(QRect(0, 0, text_width, 100000),
                                       Qt.TextFlag.TextWordWrap.value, text)
        height = wrapped.height() + 16 + border + 2
        label.setFixedSize(width, height)

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        if who == "you":
            h.addStretch(1)
            h.addWidget(label)
        else:
            h.addWidget(label)
            h.addStretch(1)
        row.setFixedHeight(0)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, row)
        self._grow_row(row, height, 300)

    def _stick_to_bottom(self, _minimum, maximum):
        self.scroll.verticalScrollBar().setValue(maximum)

    def set_status(self, text):
        if text.startswith("Listening"):
            state = "listening"
        elif text.startswith(("Thinking", "Loading", "Starting")):
            state = "thinking"
        else:
            state = "idle"
        self.status.set_state(state, text)
        self.mic.set_state(state)
        self.accent_fader.fade_to(STATE_COLORS[state])
        self.input.setProperty("state", state)
        self.input.style().unpolish(self.input)
        self.input.style().polish(self.input)

    # ---------- Positions ----------
    def _points(self):
        screen = QApplication.primaryScreen().availableGeometry()
        edge = screen.right() + 1
        y = screen.top() + (screen.height() - self.height()) // 2
        # The card sits SHADOW pixels inside the window, so the positions account for it
        open_pos = QPoint(edge - MARGIN + SHADOW - self.width(), y)
        closed_pos = QPoint(edge - STRIP - SHADOW, y)
        return open_pos, closed_pos

    def _animate(self, point, opacity, ms, curve):
        self.group.stop()
        self.pos_anim.setDuration(ms)
        self.pos_anim.setEasingCurve(curve)
        self.pos_anim.setStartValue(self.pos())
        self.pos_anim.setEndValue(point)
        self.fade_anim.setDuration(ms)
        self.fade_anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutCubic))
        self.fade_anim.setStartValue(self.windowOpacity())
        self.fade_anim.setEndValue(opacity)
        self.group.start()

    # ---------- Public actions ----------
    def dock(self):
        """Start hidden at the edge (only the strip is visible)."""
        _, closed_pos = self._points()
        self.setWindowOpacity(FADE_CLOSED)
        self.move(closed_pos)
        self.show()
        self.expanded = False

    def slide_out(self, focus=False):
        self.hide_timer.stop()
        open_pos, _ = self._points()
        self.expanded = True
        self.show()
        self.raise_()
        curve = spring_curve() if SPRING else QEasingCurve(QEasingCurve.Type.OutCubic)
        self._animate(open_pos, 1.0, SLIDE_OUT_MS, curve)
        if focus:
            self.activateWindow()
            self.input.setFocus()

    def slide_in(self):
        # Hiding the panel cancels a waiting question, so a stray "yes" later
        # can never trigger it. (Esc and Ctrl+Space do this on purpose.)
        self._clear_pending()
        _, closed_pos = self._points()
        self.expanded = False
        self.input.clearFocus()
        self._animate(closed_pos, FADE_CLOSED, SLIDE_IN_MS,
                      QEasingCurve(QEasingCurve.Type.InOutCubic))

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
        # Stay open while the mouse is over the panel, you are typing, Nova is busy,
        # or Nova is waiting for your yes / no answer
        if (self.underMouse() or self.input.hasFocus() or self._thinking()
                or self._listening() or self.pending is not None):
            return
        self.slide_in()

    # ---------- Confirmation ----------
    def _clear_pending(self):
        if self.pending is not None:
            print("[panel] waiting question cancelled (panel hidden)")
            cancel_pending(self.pending)
            self.pending = None
            self.confirm_by_voice = False
            self.input.setPlaceholderText(NORMAL_HINT)

    # ---------- Sending a command (typed or spoken) ----------
    def on_chip(self, command):
        if self._thinking() or self._listening():
            return
        self.submit(command)

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
        print(f"[panel] submit ({'spoken' if spoken else 'typed'}): {text}")
        if self._thinking():
            self.add_message("nova", "One moment, I'm still busy with the last thing...")
            return

        self._hide_chips()
        self.input.remember(text)
        self.add_message("you", ("🎤 " if spoken else "") + text)

        # An action is waiting for yes / no
        if self.pending is not None:
            answer = text.lower()
            kind = self.pending["kind"]

            if answer in YES_WORDS:
                # shutdown / restart by voice need the longer phrase "yes confirm"
                if spoken and kind in STRICT_VOICE and answer != "yes confirm":
                    self.add_message("ask", f"To {kind} by voice, say \"yes confirm\". "
                                            f"Or type yes.")
                    QTimer.singleShot(400, self._voice_soon)  # listen again, still waiting
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
        self._show_typing()
        self.worker = CommandWorker(text)
        self.worker.done.connect(self.show_reply)
        self.worker.start()

    def show_reply(self, text, pending):
        print("[panel] reply:", text.replace("\n", " "))
        self._hide_typing()
        self.pending = pending
        listen_for_answer = False
        if pending is not None:
            self.input.setPlaceholderText(CONFIRM_HINT)
            if self.confirm_by_voice:
                phrase = "yes confirm" if pending["kind"] in STRICT_VOICE else "yes"
                text += f"\nListening for your answer: say \"{phrase}\" or \"no\"."
                listen_for_answer = True
        self.confirm_by_voice = False
        self.add_message("ask" if pending is not None else "nova", text)
        self.set_status("Ready")
        if listen_for_answer:
            QTimer.singleShot(300, self._voice_soon)

    # ---------- Voice ----------
    def on_mic_clicked(self):
        if self._listening():
            self.voice.requestInterruption()   # click again = stop listening
            return
        self.start_voice()

    def start_voice(self):
        """Called by the mic button and the Ctrl+Alt+Space hotkey."""
        if self._thinking() or self._listening():
            return
        self._begin_voice()

    def _voice_soon(self, tries=0):
        """Starts listening as soon as Nova is free (retries for up to 3 seconds)."""
        if self._thinking() or self._listening():
            if tries < 15:
                QTimer.singleShot(200, lambda: self._voice_soon(tries + 1))
            return
        self._begin_voice()

    def _begin_voice(self):
        self.spoken_text = None
        self.slide_out()
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
        if self.pending is not None:
            message = "I didn't hear yes or no. Click the mic and try again, or type yes / no."
        self.add_message("nova", message)
        self.set_status("Ready")

    def on_voice_finished(self):
        text, self.spoken_text = self.spoken_text, None
        if text:
            self.set_status("Ready")
            QTimer.singleShot(0, lambda: self.submit(text, spoken=True))
        elif self.status.state != "idle":
            self.set_status("Ready")

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