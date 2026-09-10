import sys
import pandas as pd

from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.classes.FileManager import FileManager
from src.classes.PdfParser import PdfParser
from src.classes.WebBot import WebBot
from src.classes.XlsxProcessor import XlsxProcessor


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
        QMessageBox.information(self, "Предупреждение", "Убедитесь, что файлы excel лежат в целевой папке")

        text = self.input_field.text().strip()

        if not text:
            QMessageBox.warning(
                self,
                "Предупреждение",
                "Введите значение в поле."
            )
            return
        
        foldmanager = FileManager()
        '''Собираем файлы .xlsx'''
        xlsxfile = foldmanager.get_xlsx_filse()

        '''Берем целевой файл'''
        targ_file = next((s for s in xlsxfile if "Детальный" in s), None)
        xlsxproc = XlsxProcessor()
        '''Готовим данные для загрузки актов'''
        xlsxproc.create_load_data(targ_file)
        '''Создаем бота и запускаем процесс загрузки'''
        webbot = WebBot()
        while xlsxproc.get_next_deal():
            '''логика скачивания файлов'''
        
        '''Собираем файлы из главной папки и создаем парсера pdf'''
        foldmanager.get_files_in_target_folder()
        pdfparser = PdfParser()

        '''сортируем фалы'''
        while foldmanager.sub_files:
            file = foldmanager.get_next_file()
            if pdfparser.detect_sber(file):
                foldmanager.move_actual(file)
            else:
                foldmanager.move_other(file)
        
        '''Готовим данные для отчетов'''
        data_report = {}
        for col in xlsxproc.report_col:
            data_report[col] = []
        
        data_ressult = {}
        for col in xlsxproc.result_col:
            data_ressult[col] = []
        
        
        '''анализируем актуальные файлы'''
        while foldmanager.actual_deal:
            file = foldmanager.get_next_actual()
            if pdfparser.detect_vozvrat(file):
