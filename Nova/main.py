import sys
from PyQt6.QtWidgets import QApplication, QLabel

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

label = QLabel("Nova is running")
label.show()

sys.exit(app.exec())

# Step 1 Completed
