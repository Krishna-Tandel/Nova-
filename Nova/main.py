import sys
from PyQt6.QtWidgets import QApplication, Qlabel

app = QApplication(sys.argv)
app.setQuitOnastWindowClosed(False)

label = Qlabel("Nova is running")
label.show()

sys.exit(app.exec())