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
                if "третью очередь" in text:
                    return True
        
        return False
    
    def detect_gosposhlina(self, file):
        '''Проверяет сведения о госпошлине'''
        text = ""
        with fitz.open(file) as pdf:
            for page in pdf:
                text = text + page.get_text().lower()
                if "госпошлин" in text:
                    return True
        
        return False
        
    def get_gosposhlina(self, file):
        """Парсит сумму включенной госпошлины."""
        pattern1 = r"(\d+\s+\d+).+по\s+оплате\s+госпошлины"
        #pattern2 = r"(\d+\s+\d+)\s+руб.+государств"
        pattern3 = r"(\d+\s+\d+)\s+руб\.\s+\d+\s+коп\.\s+.\s+госпошлин"
        pattern4 = r"государственной.+пошлины\s+в\s+размере\s+(\d+\s+\d+\s+руб).\s+(\d+)"
        pattern5 = r"(\d+\s+\d+\s+руб).\s+.\s+"
        pattern6 = r"«сбербанк россии»\s+(\d+\s+\d+\s+рублей).+оплате\s+госпошлины"
        patterns = [pattern4, pattern1, pattern3, pattern5, pattern6]

        text = ""

        with fitz.open(file) as pdf:
            for page in pdf:
                text += page.get_text().lower()

        find_elements = []

        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)

            print(f"\npattern: {pattern}")
            print(f"matches: {matches}")

            for match in matches:
                # Если одна группа — findall вернёт строку,
                # если несколько — кортеж групп.
                if isinstance(match, tuple):
                    raw = "".join(group for group in match if group)
                else:
                    raw = match

                print(f"raw match: {raw!r}")

                cleaned = (
                    raw.strip()
                    .replace("\n", " ")
                    .replace(" ", "")
                    .replace("рублей", "")
                    .replace("коп", "")
                    .replace(",", ".")
                    .replace("руб", "")
                )

                print(f"cleaned: {cleaned!r}")

                if cleaned.isdigit():
                    # Если есть и рубли, и копейки: последние две цифры — копейки
                    if len(cleaned) > 2 and "руб" in raw and "коп" in raw:
                        amount = int(cleaned[:-2]) + int(cleaned[-2:]) / 100
                    else:
                        amount = float(cleaned)

                    find_elements.append(amount)

        print(f"all amounts: {find_elements}")

        if find_elements:
            return sum(find_elements)

        return ""
                        

                        
    
    def get_case_number(self, file : str) -> str:
        pattern = r"([AaАа]\d+-\d+/\d{4})"
        with fitz.open(file) as pdf:
            for page in pdf:
                text = page.get_text().lower()
                if re.search(pattern, text):
                    return re.search(pattern, text).group(1)
        
        return "None"