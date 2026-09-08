import fitz
import re

class PdfParser:
    def __init__(self):
        self.vozvrat_forms = [
            "возврат",
            "возврата",
            "возврату",
            "возвратом",
            "возврате",
            "возвраты",
            "возвратов",
            "возвратам",
            "возвратами",
            "возвратах"]
        
        self.rtk_pattern = [
            "РТК",
            "включении в реестр",
            "включения требований",
            "включения требования"
        ]

        self.duty = [
            ""
        ]

    def detect_sber(self, file : str) -> bool:
        '''Проверяет, что в файле есть сведения про сбер'''
        with fitz.open(file) as pdf:
            for page in pdf:
                if "сбербанк" in page.get_text().lower():
                    return True
        
        return False
        
    
    def detect_vozvrat(self, file : str) -> bool:
        '''проверяет, что есть сведения о возврате госпошлины'''
        text = ""
        with fitz.open(file) as pdf:
            for page in pdf:
                text = text + page.get_text().lower()

        return any(word in text for word in self.vozvrat_forms)

    def detect_rtk(self, file : str) -> bool:
        '''проверяет признак включения в РТК'''
        text = ""
        with fitz.open(file) as pdf:
            for page in pdf:
                text = text + page.get_text().lower()
                if "включить в тертью очередь" in text:
                    return True
        
        return False
        
    def get_gosposhlina(self, file):
        '''парсит сумму включенной госпошлины'''
        pattern = r"государственной пошлины в размере\s+(\d+\s*[\d,]?)"

        with fitz.open(file) as pdf:
            for page in pdf:
                text = text + page.get_text().lower()
                sear = re.search(pattern, text)
                if sear:
                    return sear.group(1)