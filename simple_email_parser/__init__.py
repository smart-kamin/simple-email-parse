"""
simple_email_parser - библиотека для парсинга email переписки
"""

from .email_parser import EmailParser
from .html_processor import HtmlProcessor
from .json_processor import JsonProcessor, Contact, Header, Message
from .header_adapters import (
    DividerHeaderAdapter,
    MultipleDivHeaderAdapter,
    KeyValueHeaderAdapter,
    OnelineHeaderAdapter,
)

__version__ = "0.1.1"

__all__ = [
    "EmailParser",
    "HtmlProcessor",
    "JsonProcessor",
    "Contact",
    "Header",
    "Message",
    "DividerHeaderAdapter",
    "MultipleDivHeaderAdapter",
    "KeyValueHeaderAdapter",
    "OnelineHeaderAdapter",
]
