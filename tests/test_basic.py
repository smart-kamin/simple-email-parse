"""
Базовые тесты для проверки работоспособности библиотеки.
Не содержат персональной информации.
"""
import pytest
from bs4 import BeautifulSoup

from email_parser import EmailParser
from html_processor import HtmlProcessor
from json_processor import JsonProcessor, Contact


def test_imports():
    """Проверка импорта всех основных модулей"""
    assert EmailParser is not None
    assert HtmlProcessor is not None
    assert JsonProcessor is not None
    assert Contact is not None


def test_html_processor_basic():
    """Базовый тест HtmlProcessor с простым HTML"""
    html = """
    <html>
        <body>
            <div>Test message</div>
            <blockquote>
                <div>Quoted message</div>
            </blockquote>
        </body>
    </html>
    """
    processor = HtmlProcessor(html=html)
    processor.process()

    assert processor.soup is not None
    assert "Test message" in str(processor.soup)


def test_json_processor_basic():
    """Базовый тест JsonProcessor с простым HTML"""
    html = """
    <div>First message</div>
    <blockquote>
        <div simple-email-parse-attr="quote_header_oneline">14.05.2024, 17:35, Test User &lt;test@example.com&gt;:</div>
        <div>Second message</div>
    </blockquote>
    """
    soup = BeautifulSoup(html, "html.parser")
    processor = JsonProcessor(html=soup)
    messages = processor.process()

    assert len(messages) >= 1
    assert isinstance(messages, list)


def test_email_parser_basic():
    """Базовый тест EmailParser с простым HTML"""
    html = """
    <html>
        <body>
            <div>Test message content</div>
        </body>
    </html>
    """
    parser = EmailParser(html=html)
    messages = parser.get_dict()

    assert isinstance(messages, list)
    assert len(messages) >= 1

    json_str = parser.get_json()
    assert isinstance(json_str, str)
    assert "Test message content" in json_str


def test_contact_creation():
    """Тест создания объекта Contact"""
    contact = Contact(email="test@example.com", name="Test User")

    assert contact.email == "test@example.com"
    assert contact.name == "Test User"

    contact_dict = dict(contact)
    assert contact_dict["email"] == "test@example.com"
    assert contact_dict["name"] == "Test User"


def test_email_parser_with_contact():
    """Тест EmailParser с указанием основного контакта"""
    html = "<div>Message text</div>"
    main_contact = Contact(email="user@example.com", name="User")

    parser = EmailParser(html=html, main_contact=main_contact)
    messages = parser.get_dict()

    assert len(messages) >= 1
    assert isinstance(messages[0], dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
