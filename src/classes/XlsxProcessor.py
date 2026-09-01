import pandas as pd
import os
import re

class XlsxProcessor:
    def __init__(self):
        self.deals = []

    def create_load_data(self, xlsx_detail : str):
        if not os.path.exists(xlsx_detail):
            return
        
        df_detail = pd.read_excel(xlsx_detail)
        #df_uvhd = pd.read_excel(xlsx_uvhd)

        df_detail["Код дела"] = df_detail["Код дела"].astype(str)
        df_detail["Судебный номер дела"] = df_detail["Судебный номер дела"].astype(str)
        #df_uvhd["Номер судебного дела"] = df_uvhd["Номер судебного дела"].astype(str)

        df_detail["Код дела"] = df_detail["Код дела"].apply(lambda x: x.lower().replace("cp-", ""))

        mask = r"[АA]-\d+/d+"
        target_deal = [ d for d in df_detail["Судебный номер дела"] if re.match(mask, d)]
        self.deals = target_deal
    
    def get_deals(self):
        return self.deals