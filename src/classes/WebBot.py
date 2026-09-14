#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
WebBot.py - Поиск дел и скачивание PDF-вложений с сайта kad.arbitr.ru.
"""

import glob
import logging
import os
import re
import shutil
import sys
import time
import urllib.parse

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions

KAD_URL = "https://kad.arbitr.ru/"
USER_DATA_DIR = "./kad_session"

# Пути под Linux (SberOS), как в casebook_downloader.py
CHROMEDRIVER_PATH = "/opt/sberdriver/sberdriver"
SBER_BROWSER_PATH = "/usr/bin/sberbrowser-browser-stable"

EDGEDRIVER_PATH = r"C:\Users\Roman\Downloads\edgedriver_win64 (2)\msedgedriver.exe"
EDGE_PATH_BINAR = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Безопасный запас относительно ограничения Windows на длину пути (MAX_PATH = 260)
MAX_PATH_LENGTH = 240

# Безопасный запас относительно ограничения Linux/ext4 на длину компонента имени файла (обычно 255 байт)
MAX_FILENAME_BYTES = 200

# Ожидание скачивания файла браузером: интервал опроса и общий таймаут (сек)
DOWNLOAD_POLL_INTERVAL = 0.5
DOWNLOAD_TIMEOUT = 40

# Как часто напоминать в лог, что капча еще не решена, пока пользователь вводит символы (сек)
CAPTCHA_LOG_REMINDER_INTERVAL = 30


class KadSiteUnavailableError(Exception):
    """Сайт kad.arbitr.ru недоступен: подряд превышено число попыток на уровне сессии/запросов."""


class StopRequested(Exception):
    """Внутренний сигнал остановки процесса по запросу пользователя."""


def sanitize_filename(name: str) -> str:
    """Убирает символы, недопустимые в имени файла Windows."""
    name = re.sub(r'[\\/:*?"<>|]', "_", name or "")
    return name.strip().strip(".") or "file"


def normalize_pdf_url(url: str) -> str:
    """
    Ссылки вида /Kad/PdfDocument/{caseId}/{docId}/{filename} в разметке карточки дела
    ведут не на сам файл, а на JS-обертку (при прямом GET сервер отдает HTML, а не PDF).
    Реальный файл отдается по /Document/Pdf/{caseId}/{docId}/{filename}?isAddStamp=True.
    """
    normalized = url.replace("/Kad/PdfDocument/", "/Document/Pdf/")
    if "isAddStamp" not in normalized:
        separator = "&" if "?" in normalized else "?"
        normalized = f"{normalized}{separator}isAddStamp=True"
    return normalized


def _build_logger(output_dir: str):
    """Создает логгер с записью в файл (папка logs внутри output_dir) и в консоль."""
    logs_dir = os.path.join(os.path.abspath(output_dir), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, f"kad_bot_{time.strftime('%Y%m%d_%H%M%S')}.log")

    logger = logging.getLogger(f"WebBot.{id(logs_dir)}.{time.time()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger, log_path


class WebBot:
    def __init__(
        self,
        output_dir: str,
        user_data_dir: str = USER_DATA_DIR,
        driver_path: str = EDGEDRIVER_PATH,
        browser_path: str = EDGE_PATH_BINAR,
        max_retries: int = 3,
        log_callback=None,
        progress_callback=None,
        captcha_callback=None,
    ):
        self.output_dir = output_dir
        self.user_data_dir = user_data_dir
        self.driver_path = driver_path
        self.browser_path = browser_path
        self.max_retries = max_retries
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self.captcha_callback = captcha_callback

        self.driver = None
        self._site_failures = 0
        self._stop_requested = False

        os.makedirs(self.output_dir, exist_ok=True)
        self._download_tmp_dir = os.path.join(os.path.abspath(self.output_dir), ".kad_download_tmp")
        os.makedirs(self._download_tmp_dir, exist_ok=True)

        self.logger, self.log_file_path = _build_logger(self.output_dir)
        self._log(f"[*] Полный лог сохраняется в файл: {self.log_file_path}")

    # ---------- служебное ----------
    def _log(self, msg: str, level: str = "info"):
        log_fn = getattr(self.logger, level, self.logger.info)
        log_fn(msg)
        if self.log_callback:
            self.log_callback(msg)

    def _report_progress(self, current: int, total: int):
        if self.progress_callback:
            self.progress_callback(current, total)

    def request_stop(self):
        """Запрашивает остановку процесса. Останавливается на ближайшей проверке между шагами."""
        self._stop_requested = True

    def _check_stop(self):
        if self._stop_requested:
            raise StopRequested()

    def _note_site_failure(self, context: str):
        self._site_failures += 1
        self._log(
            f"[-] Сбой соединения с kad.arbitr.ru ({context}), попытка {self._site_failures}/{self.max_retries}",
            level="warning",
        )
        if self._site_failures >= self.max_retries:
            message = f"kad.arbitr.ru недоступен после {self.max_retries} попыток подряд ({context})"
            self._log(f"[!] {message}", level="error")
            raise KadSiteUnavailableError(message)

    def _note_site_success(self):
        self._site_failures = 0

    # ---------- драйвер ----------
    def _build_driver(self):
        #options = Options()
        options = EdgeOptions()


        if self.browser_path and os.path.exists(self.browser_path):
            options.binary_location = self.browser_path
            self._log(f"[+] Используется SberBrowser: {self.browser_path}")
        else:
            for win_path in (
                os.path.expandvars(r"%LocalAppData%\SberBrowser\Application\SberBrowser.exe"),
                os.path.expandvars(r"%ProgramFiles%\SberBrowser\Application\SberBrowser.exe"),
            ):
                if os.path.exists(win_path):
                    options.binary_location = win_path
                    self._log(f"[+] Найден SberBrowser: {win_path}")
                    break

        options.add_argument(f"user-data-dir={os.path.abspath(self.user_data_dir)}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        #options.add_argument("--start-maximized")
        #options.add_argument("--no-sandbox")
        #options.add_experimental_option("excludeSwitches", ["enable-automation"])
        #options.add_experimental_option("useAutomationExtension", False)
        options.add_argument(f"user-agent={USER_AGENT}")

        # Скачивать PDF файлом в указанную папку вместо открытия во встроенном просмотрщике браузера
        options.add_experimental_option("prefs", {
            "download.default_directory": self._download_tmp_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True,
            "safebrowsing.enabled": True,
        })

        if self.driver_path and os.path.exists(self.driver_path):
            self._log(f"[*] Подключение службы SberDriver: {self.driver_path}")
            service = EdgeService(executable_path=self.driver_path)
            #service = Service(executable_path=self.driver_path)
        else:
            win_driver_path = r"C:\chromedriver_win64\chromedriver.exe"
            if os.path.exists(win_driver_path):
                self._log(f"[*] Запуск chromedriver под Windows: {win_driver_path}")
                service = EdgeService(executable_path=self.driver_path)
                #service = Service(executable_path=win_driver_path)
            else:
                self._log("[*] Локальные драйверы не найдены. Подключение ChromeDriverManager...")
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
        
        driver = webdriver.Edge(service=service, options=options)
        #driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "const p = navigator.__proto__; delete p.webdriver; navigator.__proto__ = p;"
        })
        try:
            driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                "behavior": "allow",
                "downloadPath": self._download_tmp_dir,
            })
        except Exception as e:
            self._log(f"[-] Не удалось настроить папку загрузок браузера через CDP: {e}")
        return driver

    def start(self):
        """Запускает браузер и открывает главную страницу kad.arbitr.ru. До max_retries попыток."""
        for attempt in range(1, self.max_retries + 1):
            self._check_stop()
            try:
                self._log("[*] Запуск браузера...")
                self.close()
                self.driver = self._build_driver()
                self.driver.get(KAD_URL)
                self._wait_captcha_if_any()
                self._note_site_success()
                return
            except StopRequested:
                raise
            except (TimeoutException, WebDriverException) as e:
                self._note_site_failure(f"запуск браузера: {e.__class__.__name__}")
                time.sleep(1.5)

        raise KadSiteUnavailableError(
            f"Не удалось запустить браузер и открыть kad.arbitr.ru после {self.max_retries} попыток"
        )

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        self._clear_download_tmp()

    # ---------- капча ----------
    def _captcha_visible(self) -> bool:
        try:
            popup = self.driver.find_elements(By.CLASS_NAME, "b-pravocaptcha")
        except Exception:
            return False
        return bool(popup) and popup[0].is_displayed()

    def _wait_captcha_if_any(self):
        """
        Капча (b-pravocaptcha) на kad.arbitr.ru требует, чтобы человек вручную ввел символы с картинки -
        это может занять некоторое время, поэтому ждем без жесткого таймаута (только по запросу остановки),
        периодически напоминая о себе в лог и уведомляя интерфейс через captcha_callback.
        """
        if not self._captcha_visible():
            return

        self._log(
            "[!] На kad.arbitr.ru появилась капча — нужно вручную ввести символы с картинки в открытом окне "
            "браузера. Это может занять некоторое время, работа продолжится автоматически после её решения.",
            level="warning",
        )
        if self.captcha_callback:
            try:
                self.captcha_callback()
            except Exception:
                pass

        started_at = time.time()
        last_reminder = started_at
        while self._captcha_visible():
            self._check_stop()
            now = time.time()
            if now - last_reminder >= CAPTCHA_LOG_REMINDER_INTERVAL:
                elapsed_min = int((now - started_at) // 60)
                self._log(f"[!] Капча еще не решена (прошло {elapsed_min} мин.). Ожидание продолжается...", level="warning")
                last_reminder = now
            time.sleep(1.0)

        self._log("[+] Капча решена, продолжаем работу.")

    # ---------- поиск дела ----------
    def search_case(self, case_number: str) -> list:
        """
        Ищет дело по номеру на kad.arbitr.ru.
        Возвращает список ссылок на карточки дела: пустой список, если дело не найдено,
        или несколько ссылок, если найдено несколько записей (разные инстанции/производства).
        """
        for attempt in range(1, self.max_retries + 1):
            self._check_stop()
            try:
                self.driver.get(KAD_URL)
                self._wait_captcha_if_any()

                case_input = WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#sug-cases input[type='text']"))
                )
                case_input.click()
                case_input.clear()
                case_input.send_keys(case_number)
                time.sleep(0.6)

                self.driver.find_element(By.ID, "b-form-submit").click()

                WebDriverWait(self.driver, 20).until(
                    lambda d: d.find_elements(By.CSS_SELECTOR, "#b-cases tbody tr") or self._no_results_visible(d)
                )
                self._wait_captcha_if_any()
                self._note_site_success()

                if self._no_results_visible(self.driver):
                    return []

                links = []
                for a in self.driver.find_elements(By.CSS_SELECTOR, "#b-cases a.num_case"):
                    href = a.get_attribute("href")
                    if href and href not in links:
                        links.append(href)
                return links

            except StopRequested:
                raise
            except (TimeoutException, WebDriverException) as e:
                self._note_site_failure(f"поиск дела {case_number}: {e.__class__.__name__}")
                time.sleep(1.5)

        return []

    @staticmethod
    def _no_results_visible(driver) -> bool:
        try:
            el = driver.find_element(By.CLASS_NAME, "b-noResults")
        except Exception:
            return False
        classes = el.get_attribute("class") or ""
        return "g-hidden" not in classes

    # ---------- карточка дела ----------
    def get_pdf_links(self, case_url: str) -> list:
        """Открывает карточку дела и собирает все ссылки на PDF-вложения (все инстанции)."""
        for attempt in range(1, self.max_retries + 1):
            self._check_stop()
            try:
                self.driver.get(case_url)
                self._wait_captcha_if_any()

                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "b-case-chrono-content"))
                )
                self._note_site_success()

                links = []
                seen = set()
                for a in self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/Kad/PdfDocument/']"):
                    href = a.get_attribute("href")
                    if not href or href in seen:
                        continue
                    seen.add(href)
                    name = (a.text or "").strip() or os.path.basename(urllib.parse.urlparse(href).path)
                    links.append({"url": normalize_pdf_url(href), "name": name})
                return links

            except StopRequested:
                raise
            except (TimeoutException, WebDriverException) as e:
                self._note_site_failure(f"открытие карточки дела: {e.__class__.__name__}")
                time.sleep(1.5)

        return []

    # ---------- скачивание ----------
    def _clear_download_tmp(self):
        for f in glob.glob(os.path.join(self._download_tmp_dir, "*")):
            try:
                os.remove(f)
            except OSError:
                pass

    def _wait_for_browser_download(self, timeout: float = DOWNLOAD_TIMEOUT) -> str:
        """
        Ждет, пока браузер закончит скачивание файла во временную папку.
        Возвращает путь к скачанному файлу или None, если файл не появился за отведенное время.
        """
        deadline = time.time() + timeout
        last_size = {}
        while time.time() < deadline:
            self._check_stop()
            entries = glob.glob(os.path.join(self._download_tmp_dir, "*"))
            in_progress = [f for f in entries if f.endswith(".crdownload") or f.endswith(".tmp")]
            finished = [f for f in entries if f not in in_progress]

            if finished and not in_progress:
                path = finished[0]
                try:
                    size = os.path.getsize(path)
                except OSError:
                    size = -1
                # ждем стабильного размера файла между двумя опросами, чтобы не схватить недописанный файл
                if size > 0 and last_size.get(path) == size:
                    return path
                last_size[path] = size

            time.sleep(DOWNLOAD_POLL_INTERVAL)

        return None

    @staticmethod
    def _file_looks_like_pdf(path: str) -> bool:
        try:
            with open(path, "rb") as f:
                return f.read(5) == b"%PDF-"
        except OSError:
            return False

    @staticmethod
    def _safe_remove(path: str):
        try:
            os.remove(path)
        except OSError:
            pass

    def _truncate_filename(self, filename: str, directory: str) -> str:
        """
        Обрезает имя файла с учетом двух разных ограничений файловой системы:
        - длина отдельного компонента имени файла в байтах (Linux/ext4: обычно 255 байт;
          кириллица в UTF-8 занимает 2 байта на символ, поэтому обрезка по числу символов недостаточна);
        - общая длина пути в символах (Windows: MAX_PATH ~260).
        """
        base, ext = os.path.splitext(filename)
        ext_bytes = len(ext.encode("utf-8"))

        # запас под суффикс уникальности "_N" и сам лимит на компонент имени файла
        max_base_bytes = max(MAX_FILENAME_BYTES - ext_bytes - 10, 20)

        # запас под разделитель, суффикс уникальности и лимит MAX_PATH
        max_name_chars = MAX_PATH_LENGTH - len(os.path.abspath(directory)) - len(ext) - 10
        max_name_chars = max(max_name_chars, 20)

        if len(base) > max_name_chars:
            base = base[:max_name_chars]

        while len(base.encode("utf-8")) > max_base_bytes and base:
            base = base[:-1]

        return base.rstrip() + ext

    def _unique_filepath(self, filename: str, directory: str) -> str:
        filename = self._truncate_filename(filename, directory)
        filepath = os.path.join(directory, filename)
        base, ext = os.path.splitext(filepath)
        counter = 1
        while os.path.exists(filepath):
            filepath = f"{base}_{counter}{ext}"
            counter += 1
        return filepath

    def download_pdf(self, url: str, filename: str, directory: str = None, referer: str = None) -> bool:
        """
        Скачивает один PDF-файл средствами самого браузера (переход по ссылке со страницы дела,
        как это делает пользователь), до self.max_retries попыток. Возвращает True при успехе.
        """
        directory = directory or self.output_dir
        os.makedirs(directory, exist_ok=True)
        filepath = self._unique_filepath(filename, directory)

        for attempt in range(1, self.max_retries + 1):
            self._check_stop()
            try:
                self._clear_download_tmp()

                if referer:
                    # заходим на страницу дела и переходим по ссылке из ее контекста -
                    # так браузер отправит корректный Referer, как при обычном клике пользователя
                    self.driver.get(referer)
                    self._wait_captcha_if_any()
                    self.driver.execute_script("window.location.href = arguments[0];", url)
                else:
                    self.driver.get(url)

                self._wait_captcha_if_any()

                downloaded_path = self._wait_for_browser_download()

                if not downloaded_path:
                    self._log(
                        f"    -> [Попытка {attempt}/{self.max_retries}] Файл не скачался браузером за отведенное время",
                        level="warning",
                    )
                elif not self._file_looks_like_pdf(downloaded_path):
                    self._log(
                        f"    -> [Попытка {attempt}/{self.max_retries}] Браузер получил не PDF-файл "
                        f"(возможно, истекла сессия или требуется капча)",
                        level="warning",
                    )
                    self._safe_remove(downloaded_path)
                else:
                    shutil.move(downloaded_path, filepath)
                    self._note_site_success()
                    self._log(f"    -> [Успешно] {os.path.basename(filepath)}")
                    return True

            except StopRequested:
                raise
            except (TimeoutException, WebDriverException) as e:
                self._log(f"    -> [Попытка {attempt}/{self.max_retries}] Ошибка скачивания: {e}", level="warning")
                self._note_site_failure(f"скачивание {filename}: {e.__class__.__name__}")

            time.sleep(1.0)

        self._log(f"    -> [Пропуск] Не удалось скачать файл после {self.max_retries} попыток: {filename}", level="warning")
        return False

    # ---------- основной процесс ----------
    def run(self, case_numbers: list) -> list:
        """
        Основной цикл: для каждого номера дела ищет карточки на kad.arbitr.ru
        и скачивает все найденные PDF-вложения во временную рабочую папку.
        Возвращает сводку по каждому делу.
        """
        total = len(case_numbers)
        summary = []

        self.start()
        try:
            for index, raw_case_number in enumerate(case_numbers, start=1):
                self._check_stop()
                case_number = str(raw_case_number).strip()
                if not case_number:
                    continue

                self._log(f"\n[Дело {index}/{total}] Поиск: {case_number}")
                self._report_progress(index - 1, total)

                case_links = self.search_case(case_number)

                if not case_links:
                    self._log("  -> Дело не найдено, пропуск.", level="warning")
                    summary.append({"case_number": case_number, "found": False, "downloaded": 0, "skipped": 0})
                    self._report_progress(index, total)
                    continue

                self._log(f"  -> Найдено карточек дела: {len(case_links)}")

                downloaded = 0
                skipped = 0
                safe_case_number = sanitize_filename(case_number)
                case_dir = os.path.join(self.output_dir, safe_case_number)
                os.makedirs(case_dir, exist_ok=True)

                for case_url in case_links:
                    self._check_stop()
                    pdf_links = self.get_pdf_links(case_url)
                    self._log(f"    Карточка {case_url}: PDF-файлов найдено {len(pdf_links)}")

                    for doc in pdf_links:
                        self._check_stop()
                        original_name = sanitize_filename(doc["name"])
                        if not original_name.lower().endswith(".pdf"):
                            original_name += ".pdf"

                        if self.download_pdf(doc["url"], original_name, directory=case_dir, referer=case_url):
                            downloaded += 1
                        else:
                            skipped += 1

                summary.append({
                    "case_number": case_number,
                    "found": True,
                    "downloaded": downloaded,
                    "skipped": skipped,
                })
                self._report_progress(index, total)

        finally:
            self.close()

        return summary
