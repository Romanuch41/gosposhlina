import os
import shutil
from glob import glob

class FileManager:
    def __init__(self, target_folder : str):
        self.target_folder = target_folder
        self.actuals = ""
        self.others = ""
        self.sub_files = []
    
    def create_start_folders(self):
        '''Создает папки с релевантными и мусорными делами для сортировки уже скачанных файлов .pdf'''
        self.actuals = os.path.join(self.target_folder, "actual")
        self.others = os.path.join(self.target_folder, "others")
        os.mkdir(self.actuals)
        os.mkdir(self.others)
    
    def move_actual(self, file : str):
        '''Копирует файл в папку с релевантными файлами'''
        shutil.copy2(file, self.actuals)
    
    def move_other(self, file : str):
        '''Копирует файл в папку с мусорными файлами'''
        shutil.copy2(file, self.others)
    
    def get_files_in_target_folder(self):
        '''собирает файлы из папки, в которую качаются фалы'''
        self.sub_files = [f for f in glob(os.path.join(self.target_folder, "*")) if os.path.isfile(f)]
    
    def get_next_file(self) -> str:
        '''возвращает файл из списка (работает как stack)'''
        if not self.sub_files:
            return None
        return self.sub_files.pop(0)
    
    def get_xlsx_filse(self) -> list:
        '''Собирает файлы .xlsx'''
        return glob(os.path.join(self.target_folder + "*.xlsx"))
        