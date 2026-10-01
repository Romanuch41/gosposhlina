import os
import sys
import pandas as pd
import re

from PyQt6.QtCore import QThread, QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.classes.FileManager import FileManager
from src.classes.PdfParser import PdfParser
from src.classes.WebBot import WebBot, KadSiteUnavailableError, StopRequested
from src.classes.XlsxProcessor import XlsxProcessor


class FolderProcessingTab(QWidget):
    def __init__(self):
        super().__init__()

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Укажите путь до папки")

        self.start_button = QPushButton("Запустить")
        self.start_button.clicked.connect(self.start_processing)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Папку, куда буду скачивать документы"))
        layout.addWidget(self.input_field)
        layout.addWidget(self.start_button)

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
        webbot = KadWorker(xlsxproc.deals, foldmanager.target_folder)
        webbot.run()


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
                pass


class KadWorker(QObject):
    """Выполняет поиск дел и скачивание PDF в отдельном потоке, чтобы не блокировать интерфейс."""

    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)
    captcha_signal = pyqtSignal()

    def __init__(self, case_numbers: list, output_dir: str):
        super().__init__()
        self.case_numbers = case_numbers
        self.output_dir = output_dir
        self.bot = None

    def run(self):
        self.bot = WebBot(
            output_dir=self.output_dir,
            log_callback=self.log_signal.emit,
            progress_callback=self.progress_signal.emit,
            captcha_callback=self.captcha_signal.emit,
        )
        try:
            summary = self.bot.run(self.case_numbers)
            self.finished_signal.emit(summary)
        except StopRequested:
            self.log_signal.emit("\n[*] Процесс остановлен пользователем.")
            self.finished_signal.emit([])
        except KadSiteUnavailableError as e:
            self.error_signal.emit(str(e))
        except Exception as e:
            self.error_signal.emit(f"Непредвиденная ошибка: {e}")

    def stop(self):
        if self.bot:
            self.bot.request_stop()


class KadSearchTab(QWidget):
    def __init__(self):
        super().__init__()

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        default_excel = os.path.join(project_root, "docs", "дела.xlsx")
        default_output = os.path.join(project_root, "downloads_kad")

        self.thread = None
        self.worker = None
        self.filemanager = None
        self.xlsxworker = None

        self.excel_field = QLineEdit(default_excel if os.path.exists(default_excel) else "")
        self.excel_field.setPlaceholderText("Excel-файл со столбцом «Номер дела»")
        self.excel_files =[]
        browse_excel_btn = QPushButton("Обзор...")
        browse_excel_btn.clicked.connect(self.browse_excel)

        self.output_field = QLineEdit(default_output)
        self.output_field.setPlaceholderText("Папка для скачанных файлов")
        browse_output_btn = QPushButton("Обзор...")
        browse_output_btn.clicked.connect(self.browse_output)

        self.start_button = QPushButton("Начать")
        self.start_button.clicked.connect(self.start_search)

        self.stop_button = QPushButton("Остановить")
        self.stop_button.clicked.connect(self.stop_search)
        self.stop_button.setEnabled(False)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setValue(0)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)

        excel_row = QHBoxLayout()
        excel_row.addWidget(self.excel_field)
        excel_row.addWidget(browse_excel_btn)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output_field)
        output_row.addWidget(browse_output_btn)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.start_button)
        buttons_row.addWidget(self.stop_button)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Excel-файл со списком дел (столбец «Номер дела»)"))
        layout.addLayout(excel_row)
        layout.addWidget(QLabel("Папка для скачивания PDF"))
        layout.addLayout(output_row)
        layout.addLayout(buttons_row)
        layout.addWidget(self.progress_bar)
        layout.addWidget(QLabel("Лог"))
        layout.addWidget(self.log_view)

        self.setLayout(layout)

    def browse_excel(self):
        path, _ = QFileDialog.getOpenFileNames(self, "Выберите Excel-файлы", "", "Excel файлы (*.xlsx *.xls)")
        if path and len(path) == 2:
            self.excel_field.setText(" ".join([os.path.basename(f) for f in path]))
            self.excel_files = path
        else:
            QMessageBox.warning(self, "Ошибка!", "Выберите 2 файла excel")

    def browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Выберите папку для скачивания")
        if path:
            self.output_field.setText(path)

    def append_log(self, message: str):
        self.log_view.appendPlainText(message)

    def update_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(current)

    def start_search(self):
        output_dir = self.output_field.text().strip()

        if not self.excel_files[0] or not os.path.exists(self.excel_files[0]):
            QMessageBox.warning(self, "Предупреждение", "Укажите существующий Excel-файл со списком дел.")
            return

        if not self.excel_files[1] or not os.path.exists(self.excel_files[1]):
            QMessageBox.warning(self, "Предупреждение", "Укажите существующий Excel-файл со списком дел.")
            return

        if not output_dir:
            QMessageBox.warning(self, "Предупреждение", "Укажите папку для скачивания.")
            return

        #try:
        #    case_numbers, invalid_numbers = FileManager.read_case_numbers(excel_path)
        #except Exception as e:
        #    QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать номера дел: {e}")
        #    return

        #if not case_numbers:
        #    QMessageBox.warning(self, "Предупреждение", "В файле не найдено ни одного корректного номера дела.")
        #    return
        
        self.xlsxworker = XlsxProcessor()

        self.xlsxworker.create_load_data(self.excel_files[0], self.excel_files[1])

        self.filemanager = FileManager(output_dir)
        self.filemanager.create_start_folders()
        #os.makedirs(output_dir, exist_ok=True)

        deals = self.xlsxworker.deals[:30]
        self.log_view.clear()
        self.progress_bar.setMaximum(len(deals))
        self.progress_bar.setValue(0)
        self.append_log(f"[*] Загружено номеров дел: {len(deals)}")
        if deals:
            self.append_log(
                f"[*] Пропущено некорректных значений (не похожи на номер дела): {len(deals)} "
                ##f"— {', '.join(invalid_numbers)}"
            )

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.excel_field.setEnabled(False)
        self.output_field.setEnabled(False)

        self.thread = QThread(self)
        self.worker = KadWorker(deals, output_dir)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log_signal.connect(self.append_log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.error_signal.connect(self.on_error)
        self.worker.captcha_signal.connect(self.on_captcha_detected)
        self.worker.finished_signal.connect(self.thread.quit)
        self.worker.error_signal.connect(self.thread.quit)
        self.thread.finished.connect(self.on_thread_finished)
        self.thread.start()
        
    
    def analize_docs(self):
        errors = {"error_files" : []}
        self.filemanager.get_files_in_target_folder()
        self.append_log(f"Получил скачанные файлы {len(self.filemanager.sub_files)}")
        pdfparser = PdfParser()

        while self.filemanager.sub_files:
            file = self.filemanager.get_next_file()
            
            dir_name = os.path.basename(os.path.dirname(file))
            new_name = file.replace(".pdf", f" {dir_name}.pdf")
            os.replace(file, new_name)
            file = new_name
            if pdfparser.detect_sber(file) and pdfparser.detect_rtk(file):
                self.append_log("Найдено дело в отношении Сбербанк")
                self.filemanager.move_actual(file)
            else:
                self.append_log("Дело не относится к Сберу")
                self.filemanager.move_other(file)
        
        self.filemanager.get_actual_deal()
        if not self.filemanager.actual_deal:
            self.append_log("не найдено подходящих файлов для анализа")
            return
        
        pattern_deal = r"(\w\d+-\d+-\d{4})"
        self.xlsxworker.target_df["Сумма госпошлины"] = "0"
        self.xlsxworker.target_df["Файл"] = "None"
        while self.filemanager.actual_deal:
            file = self.filemanager.get_next_actual()
            self.append_log(f"current file {file}")
            print(f"current file {file}")
            deal_number = ""
            deal_number_search = re.search(pattern_deal, file)
            if deal_number_search:
                deal_number = deal_number_search.group(1)
                idx = deal_number.rfind("-")
                deal_number = deal_number[:idx] + "/" + deal_number[idx + 1:]
                print(deal_number) 

            if pdfparser.detect_gosposhlina(file):
                gos_summ = pdfparser.get_gosposhlina(file)
                if gos_summ and float(gos_summ) > 0:
                    print(f"полученная сумма госпошлины {gos_summ}")
                else:
                    gos_summ = "0.0"
                    errors["error_files"].append(file)

            index = self.xlsxworker.target_df[self.xlsxworker.target_df["Судебный номер дела"].str.contains(deal_number, na = False, case = False)].index.to_list()
            if len(index) < 1:
                if "A" in deal_number:
                    deal_number = deal_number.replace("A", "А")
                    index = self.xlsxworker.target_df[self.xlsxworker.target_df["Судебный номер дела"].str.contains(deal_number, na = False, case = False)].index.to_list()
                elif "А" in deal_number:
                    deal_number = deal_number.replace("А", "A")
                    index = self.xlsxworker.target_df[self.xlsxworker.target_df["Судебный номер дела"].str.contains(deal_number, na = False, case = False)].index.to_list()
            
            print(index)
            if len(index) > 0:
                for idx in index:
                    self.xlsxworker.target_df.loc[idx, "Сумма госпошлины"] = gos_summ
                    self.xlsxworker.target_df.loc[idx, "Файл"] = file
        
        self.xlsxworker.target_df.to_excel("text.xlsx", sheet_name="text", index=False)
        gos_summ = "0.0"
        erdf = pd.DataFrame(errors)
        erdf.to_excel("errors.xlsx", index = False)

        



    def stop_search(self):
        if self.worker:
            self.append_log("[*] Запрошена остановка. Завершение после текущего шага...")
            self.worker.stop()
        self.stop_button.setEnabled(False)

    def on_finished(self, summary: list):
        total_downloaded = sum(item.get("downloaded", 0) for item in summary)
        total_skipped = sum(item.get("skipped", 0) for item in summary)
        not_found = sum(1 for item in summary if not item.get("found"))
        self.append_log(
            f"\n[+] Готово. Скачано файлов: {total_downloaded}, пропущено: {total_skipped}, "
            f"дел не найдено: {not_found} из {len(summary)}."
        )

    def on_error(self, message: str):
        self.append_log(f"\n[!] {message}")
        QMessageBox.critical(self, "Остановлено", message)

    def on_captcha_detected(self):
        QApplication.beep()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Требуется действие")
        box.setText(
            "На kad.arbitr.ru появилась капча — нужно вручную ввести символы с картинки "
            "в открытом окне браузера.\n\nЭто может занять некоторое время — работа продолжится "
            "автоматически после решения капчи."
        )
        box.setModal(False)
        box.show()
        self._captcha_box = box  # удерживаем ссылку, чтобы окно не закрылось сборщиком мусора

    def on_thread_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.excel_field.setEnabled(True)
        self.output_field.setEnabled(True)
        self.analize_docs()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Грузчик СА")
        self.resize(760, 600)

        #self.folder_tab = FolderProcessingTab()
        self.kad_tab = KadSearchTab()

        tabs = QTabWidget()
        #tabs.addTab(self.folder_tab, "Обработка папки")
        tabs.addTab(self.kad_tab, "Поиск на kad.arbitr.ru")

        layout = QVBoxLayout()
        layout.addWidget(tabs)
        self.setLayout(layout)

    def closeEvent(self, event):
        if self.kad_tab.thread and self.kad_tab.thread.isRunning():
            self.kad_tab.stop_search()
            self.kad_tab.thread.wait(5000)
        event.accept()
