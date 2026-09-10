import pandas as pd
import os
import re

class XlsxProcessor:
    def __init__(self):
        self.deals = []
        self.target_df = None
        self.report_col = [
            "ТБ",
            "Код дела",
            "Ответчик/Заемщик",
            "Модель сбора",
            "Вид дела",
            "Присвоение",
            "Номер договора/контракта",
            "Закрыто дело",
            "Полностью в пользу банка",
            "КД закрыт",
            "Код дела в старой АС",
            "Итоговый СА",
            "Номер документа СА"
        ]

        self.result_col = [
            "ТБ-балансодержатель",
            "Дата смены ответственного",
            "Присвоение",
            "Сумма",
            "Код дела в АС ВРМ/АС ПО",
            "Модель сбора (Фабрика сбора, КМС)",
            "Банкротство (да/нет)",
            "Заемщик",
            "Номер КД",
            "Вид дела"
        ]

        self.target_col = [
            "Категория дела",
            "Ответчики",
            "Актуальная сумма требований",
            "Суд, рассматривающий дело",
            "Судебный номер дела"
        ]

    def create_load_data(self, xlsx_detail : str, xlsx_uvhd : str):
        '''Готовит данные боту для поиска и скачивания файлов'''
        if not os.path.exists(xlsx_detail):
            return
        
        df_detail = pd.read_excel(xlsx_detail)
        df_uvhd = pd.read_excel(xlsx_uvhd)

        df_detail["Код дела"] = df_detail["Код дела"].astype(str)
        df_detail["Судебный номер дела"] = df_detail["Судебный номер дела"].astype(str)
        df_uvhd["Номер судебного дела"] = df_uvhd["Номер судебного дела"].astype(str)

        df_detail["Код дела"] = df_detail["Код дела"].apply(lambda x: x.lower().replace("cp-", ""))
        df_detail = df_detail[df_detail["Категория дела"] == "Банкротство"]

        mask = r"[АA]-\d+/d+"
        deal_mask = r"([AaАа]\d+-\d+/\d{4})"
        df_uvhd = df_uvhd[df_uvhd["Назначение платежа_1"].str.contains(deal_mask, regex=True, case=False, na=False)]
        df_uvhd["Судебный номер дела"] = df_uvhd["Назначение платежа_1"].apply(lambda x: re.search(deal_mask, x))
        target_deal = [ d for d in df_detail["Судебный номер дела"] if re.match(mask, d)]
        self.deals = target_deal

        self.target_df = pd.merge(df_detail, df_uvhd, on="Судебный номер дела", how="outer")
        self.target_df = self.target_df.drop_duplicates(subset="Судебный номер дела", keep="last")
        self.target_df = self.target_df[self.target_col]
    
    def get_next_deal(self):
        '''Возвращает список номеров дел'''
        if not self.deals:
            return ValueError("Список пустой")
        return self.deals.pop(0)