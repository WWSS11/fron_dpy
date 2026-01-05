
import sys
from PySide6.QtWidgets import QApplication
from deploy_tool.main import MainWindow, apply_dark_theme

if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
