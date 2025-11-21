import json
import pathlib

import bs4

from .html_processor import HtmlProcessor
from .json_processor import JsonProcessor, Contact


class EmailParser:
    """
    Класс для парсинга email-сообщений.
    Последовательно использует HtmlProcessor и JsonProcessor для обработки HTML.
    """

    html_processor: HtmlProcessor
    json_processor: JsonProcessor
    soup: bs4.BeautifulSoup
    messages: list[dict]

    def __init__(
        self,
        filepath: str | pathlib.Path | None = None,
        html: str | None = None,
        soup: bs4.BeautifulSoup | None = None,
        encoding: str | None = None,
        remove_img: bool = False,
        main_contact: Contact | None = None,
    ):
        """
        Инициализирует EmailParser с теми же параметрами, что и HtmlProcessor.

        Args:
            filepath: Путь к HTML файлу
            html: HTML строка
            soup: BeautifulSoup объект
            encoding: Кодировка файла (если указан filepath)
            remove_img: Удалять ли изображения из HTML
            main_contact: Основной контакт (для JsonProcessor)
        """
        self.html_processor = HtmlProcessor(
            filepath=filepath,
            html=html,
            soup=soup,
            encoding=encoding,
            remove_img=remove_img,
        )
        self.html_processor.process()

        self.soup = self.html_processor.soup

        self.json_processor = JsonProcessor(
            html=self.soup,
            main_contact=main_contact,
        )
        self.messages = self.json_processor.process()

    def get_dict(self) -> list[dict]:
        """
        Возвращает результат обработки как список словарей.

        Returns:
            list[dict]: Список сообщений, где каждое сообщение - словарь с ключами 'header' и 'text'
        """
        return self.messages

    def get_json(self, indent: int = 2, ensure_ascii: bool = False) -> str:
        """
        Возвращает результат обработки как JSON строку.

        Args:
            indent: Количество пробелов для форматирования (по умолчанию 2)
            ensure_ascii: Экранировать ли не-ASCII символы (по умолчанию False)

        Returns:
            str: JSON строка с сообщениями
        """
        return json.dumps(self.messages, indent=indent, ensure_ascii=ensure_ascii, default=str)

    def save_json(self, filepath: str | pathlib.Path, indent: int = 2, ensure_ascii: bool = False) -> None:
        """
        Сохраняет результат обработки в JSON файл.

        Args:
            filepath: Путь к файлу для сохранения
            indent: Количество пробелов для форматирования (по умолчанию 2)
            ensure_ascii: Экранировать ли не-ASCII символы (по умолчанию False)
        """
        filepath = pathlib.Path(filepath)
        filepath.write_text(self.get_json(indent=indent, ensure_ascii=ensure_ascii), encoding="utf-8")

    def save_html(self, filepath: str | pathlib.Path) -> None:
        """
        Сохраняет обработанный soup в HTML файл.

        Args:
            filepath: Путь к файлу для сохранения
        """
        filepath = pathlib.Path(filepath)
        filepath.write_text(str(self.soup), encoding="utf-8")


if __name__ == "__main__":
    parser = EmailParser("tests/data/email_1.htm", remove_img=True)
    messages = parser.get_dict()
    print(f"Найдено сообщений: {len(messages)}")
    json_str = parser.get_json()
    print(json_str[:200])
