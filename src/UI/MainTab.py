import sys

from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Грузчик СА")
        #self.resize(400, 180)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Укажите путь до папки")

        self.start_button = QPushButton("Запустить")
        self.start_button.clicked.connect(self.start_processing)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Папку, куда буду скачивать документы"))
        layout.addWidget(self.input_field)
        layout.addWidget(self.start_button)
        #layout.addWidget(self.result_label)

        self.setLayout(layout)

    def start_processing(self):
        text = self.input_field.text().strip()

        if not text:
            QMessageBox.information(self, "Предупреждение", "Убедитесь, что файлы excel лежат в целевой папке")
            QMessageBox.warning(
                self,
                "Предупреждение",
                "Введите значение в поле."
            )
            return

        self.result_label.setText(f"Введено: {text}")


