import fitz

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

    def detect_sber(self, file : str) -> bool:
        with fitz.open(file) as pdf:
            for page in pdf:
                if "сбербанк" in page.get_text().lower():
                    return True
        
        return False
        
    
    def detect_vozvrat(self, file : str) -> bool:
        text = ""
        with fitz.open(file) as pdf:
            for page in pdf:
                text = text + page.get_text().lower()

        return any(word in text for word in self.vozvrat_forms)
