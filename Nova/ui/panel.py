from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit
from PyQt6.QtCore import Qt


class Panel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nova")
        self.resize(420, 220)

        # Frameless + always on top + hidden from taskbar
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        # Needed so the rounded corners show properly
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
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

        # Styling
        self.setStyleSheet("""
            Panel {
                background-color: #1e1e2e;
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

    def on_enter(self):
        text = self.input.text().strip()
        if text:
            self.reply.setText(f"You said: {text}")
            self.input.clear()

    # Press Esc to hide the panel
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()