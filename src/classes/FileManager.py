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
        self.actuals = os.path.join(self.target_folder, "actual")
        self.others = os.path.join(self.target_folder, "others")
        os.mkdir(self.actuals)
        os.mkdir(self.others)
    
    def move_actual(self, file : str):
        shutil.copy2(file, self.actuals)
    
    def move_other(self, file : str):
        shutil.copy2(file, self.others)
    
    def get_files_in_target_folder(self):
        self.sub_files = [f for f in glob(os.path.join(self.target_folder, "*")) if os.path.isfile(f)]
    
    def get_next_file(self) -> str:
        if not self.sub_files:
            return None
        return self.sub_files.pop(0)
    
    def get_xlsx_filse(self) -> list:
        return glob(os.path.join(self.target_folder + "*.xlsx"))
        