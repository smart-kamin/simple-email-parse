import abc
import copy
import re

import bs4


class BaseHeaderAdapter(abc.ABC):
    attr_value: str

    def __init__(self, attr_value: str):
        self.attr_value = attr_value

    @abc.abstractmethod
    def match(self, element: bs4.Tag | bs4.NavigableString) -> bool:
        """
        Проверяет, является ли элемент заголовком.
        """
        pass

    def mark(self, element: bs4.Tag | bs4.NavigableString) -> None:
        """
        Превращает элемент в чистый текстовый блок заголовка.
        Удаляет вложенные теги, оставляя только текст.
        """
        text_content = self._get_clean_text(element)

        if not text_content:
            return

        if isinstance(element, bs4.Tag):
            element.clear()
            element.string = text_content
            element["simple-email-parse-attr"] = self.attr_value

        elif isinstance(element, bs4.NavigableString):
            factory = bs4.BeautifulSoup("", "html.parser")
            new_tag = factory.new_tag("div")
            new_tag.string = text_content
            new_tag["simple-email-parse-attr"] = self.attr_value
            element.replace_with(new_tag)

    @staticmethod
    def _get_clean_text(element: bs4.Tag | bs4.NavigableString) -> str:
        if isinstance(element, bs4.NavigableString):
            return str(element).strip()

        clone = copy.copy(element)
        for br in clone.find_all("br"):
            br.replace_with("\n")

        return clone.get_text(separator=" ", strip=True)

    @staticmethod
    def _has_marked_children(element: bs4.Tag | bs4.NavigableString) -> bool:
        if isinstance(element, bs4.NavigableString):
            return False
        return bool(element.find(attrs={"simple-email-parse-attr": True}))


class OnelineHeaderAdapter(BaseHeaderAdapter):
    """
    Адаптер для однострочных заголовков.
    """

    DATE_PATTERN = r"(\d{1,2}[\.\s]+\w+[\.\s]+\d{4}|\d{2}\.\d{2}\.\d{4})"
    TIME_PATTERN = r"\d{1,2}:\d{2}"
    EMAIL_PATTERN = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

    KEYWORDS = {"от", "from", "sender", "via", "написал", "wrote"}
    ACTION_PHRASES = {"вы писали", "you wrote", "wrote"}

    def match(self, element: bs4.Tag | bs4.NavigableString) -> bool:
        if self._has_marked_children(element):
            return False

        text = self._get_clean_text(element)

        if len(text) < 10 or len(text) > 350:
            return False

        if text.count("\n") > 3:
            return False

        text_lower = text.lower()

        has_date = bool(re.search(self.DATE_PATTERN, text))
        has_time = bool(re.search(self.TIME_PATTERN, text))
        has_email = bool(re.search(self.EMAIL_PATTERN, text))
        has_keyword = any(k in text_lower for k in self.KEYWORDS)
        has_action_phrase = any(phrase in text_lower for phrase in self.ACTION_PHRASES)
        ends_with_colon = text.strip().endswith(":")

        if has_action_phrase and ends_with_colon:
            if has_date or has_time:
                return True

        if has_date and has_time:
            if has_email:
                return True
            if has_keyword and ends_with_colon:
                return True

        return False


class KeyValueHeaderAdapter(BaseHeaderAdapter):
    """
    Адаптер для блочных заголовков (From:, Sent:...).
    """

    KEY_PATTERNS = [
        r"(?:From|От)\s*:",
        r"(?:Sent|Date|Отправлено|Дата)\s*:",
        r"(?:To|Кому)\s*:",
        r"(?:Subject|Тема)\s*:",
        r"(?:Cc|Копия)\s*:",
    ]

    def match(self, element: bs4.Tag | bs4.NavigableString) -> bool:
        if isinstance(element, bs4.NavigableString):
            return False

        if self._has_marked_children(element):
            return False

        text = self._get_clean_text(element)

        if len(text) < 15 or len(text) > 1000:
            return False

        matches = 0
        first_match_pos = float("inf")

        for pattern in self.KEY_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                matches += 1
                if match.start() < first_match_pos:
                    first_match_pos = match.start()

        if matches < 2:
            return False

        if first_match_pos > 50:
            return False

        prev = element.previous_sibling
        while prev and (isinstance(prev, bs4.NavigableString) and not str(prev).strip()):
            prev = prev.previous_sibling

        if prev:
            prev_text = self._get_clean_text(prev)
            for pattern in self.KEY_PATTERNS:
                if re.search(pattern, prev_text, re.IGNORECASE):
                    return False

        return True


class DividerHeaderAdapter(BaseHeaderAdapter):
    PATTERN = r"^-+\s*(?:Пересылаемое сообщение|Forwarded message|Original Message)\s*-+$"

    def match(self, element: bs4.Tag | bs4.NavigableString) -> bool:
        if self._has_marked_children(element):
            return False

        text = self._get_clean_text(element)
        return bool(re.match(self.PATTERN, text, re.IGNORECASE))


class EndDividerHeaderAdapter(BaseHeaderAdapter):
    """
    Адаптер для маркера конца пересылаемого сообщения.
    """

    PATTERN = r"^-+\s*(?:Конец пересылаемого сообщения|End of forwarded message)\s*-+$"

    def match(self, element: bs4.Tag | bs4.NavigableString) -> bool:
        if self._has_marked_children(element):
            return False
        text = self._get_clean_text(element)
        return bool(re.match(self.PATTERN, text, re.IGNORECASE))


class MultipleDivHeaderAdapter(BaseHeaderAdapter):
    """
    Адаптер для заголовков, разбитых на несколько последовательных div.
    Например:
        <div>Кому: email@example.com;</div>
        <div>Тема: Test Subject;</div>
        <div>29.10.2025, 09:16, "Sender" <email@example.com>:</div>
    """

    KEY_PATTERNS = [
        r"(?:From|От)\s*:",
        r"(?:Sent|Date|Отправлено|Дата)\s*:",
        r"(?:To|Кому)\s*:",
        r"(?:Subject|Тема)\s*:",
        r"(?:Cc|Копия)\s*:",
    ]

    DATE_PATTERN = r"(\d{1,2}[\.\s]+\w+[\.\s]+\d{4}|\d{2}\.\d{2}\.\d{4})"
    TIME_PATTERN = r"\d{1,2}:\d{2}"
    EMAIL_PATTERN = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

    def match(self, element: bs4.Tag | bs4.NavigableString) -> bool:
        if isinstance(element, bs4.NavigableString):
            return False

        if self._has_marked_children(element):
            return False

        # Проверяем, является ли текущий элемент div
        if not isinstance(element, bs4.Tag) or element.name != "div":
            return False

        text = self._get_clean_text(element)

        # Проверяем, содержит ли текущий div один из ключей
        has_key = any(re.search(pattern, text, re.IGNORECASE) for pattern in self.KEY_PATTERNS)

        # Или содержит дату+время+email (последняя строка в серии)
        has_date = bool(re.search(self.DATE_PATTERN, text))
        has_time = bool(re.search(self.TIME_PATTERN, text))
        has_email = bool(re.search(self.EMAIL_PATTERN, text))
        ends_with_colon = text.strip().endswith(":")

        # Также проверяем исходный HTML (чтобы найти email в угловых скобках, которые интерпретируются как теги)
        raw_html = str(element)
        has_email_in_html = bool(re.search(self.EMAIL_PATTERN, raw_html))

        is_datetime_line = has_date and has_time and ends_with_colon and (has_email or has_email_in_html)

        if not (has_key or is_datetime_line):
            return False

        siblings_with_keys = []
        prev_siblings = []

        prev = element.previous_sibling
        while prev:
            if isinstance(prev, bs4.NavigableString):
                if prev.strip():
                    break
                prev = prev.previous_sibling
                continue

            if isinstance(prev, bs4.Tag):
                if prev.name != "div":
                    break

                if prev.get("simple-email-parse-attr"):
                    break

                prev_text = self._get_clean_text(prev)
                prev_has_key = any(re.search(pattern, prev_text, re.IGNORECASE) for pattern in self.KEY_PATTERNS)

                if prev_has_key:
                    prev_siblings.insert(0, prev)
                    siblings_with_keys.insert(0, prev)
                    prev = prev.previous_sibling
                else:
                    break
            else:
                break

        next_elem = element.next_sibling
        while next_elem:
            if isinstance(next_elem, bs4.NavigableString):
                if next_elem.strip():
                    break
                next_elem = next_elem.next_sibling
                continue

            if isinstance(next_elem, bs4.Tag):
                if next_elem.name != "div":
                    break

                if next_elem.get("simple-email-parse-attr"):
                    break

                next_text = self._get_clean_text(next_elem)
                next_has_key = any(re.search(pattern, next_text, re.IGNORECASE) for pattern in self.KEY_PATTERNS)

                next_has_date = bool(re.search(self.DATE_PATTERN, next_text))
                next_has_time = bool(re.search(self.TIME_PATTERN, next_text))
                next_has_email = bool(re.search(self.EMAIL_PATTERN, next_text))
                next_ends_with_colon = next_text.strip().endswith(":")
                next_is_datetime = next_has_date and next_has_time and next_has_email and next_ends_with_colon

                if next_has_key or next_is_datetime:
                    siblings_with_keys.append(next_elem)
                    next_elem = next_elem.next_sibling
                else:
                    break
            else:
                break

        if len(siblings_with_keys) >= 1:
            first_div = prev_siblings[0] if prev_siblings else element
            first_text = self._get_clean_text(first_div).strip()

            starts_with_key = any(
                re.match(r"^\s*" + pattern, first_text, re.IGNORECASE)
                for pattern in self.KEY_PATTERNS
            )

            if not starts_with_key:
                return False

            total_elements = 1 + len(siblings_with_keys)
            if total_elements > 5:
                return False

            all_texts = [text] + [self._get_clean_text(sib) for sib in siblings_with_keys]
            total_length = sum(len(t) for t in all_texts)
            if total_length > 600:
                return False

            element._multiline_siblings = siblings_with_keys
            return True

        return False

    def mark(self, element: bs4.Tag | bs4.NavigableString) -> None:
        """
        Объединяет текущий элемент со всеми найденными соседями в один блок.
        """
        if not isinstance(element, bs4.Tag):
            return

        siblings = getattr(element, "_multiline_siblings", [])
        if not siblings:
            return

        first_elem = element
        temp = element.previous_sibling
        while temp:
            if isinstance(temp, bs4.NavigableString):
                if temp.strip():
                    break
                temp = temp.previous_sibling
                continue

            if isinstance(temp, bs4.Tag) and temp in siblings:
                first_elem = temp
                temp = temp.previous_sibling
            else:
                break

        all_elements = [first_elem]
        current = first_elem.next_sibling

        while current:
            if isinstance(current, bs4.NavigableString):
                if current.strip():
                    break
                current = current.next_sibling
                continue

            if isinstance(current, bs4.Tag):
                if current == element or current in siblings:
                    all_elements.append(current)
                    current = current.next_sibling
                else:
                    break
            else:
                break

        texts = [self._get_clean_text(elem) for elem in all_elements]
        combined_text = " ".join(texts)

        if not combined_text:
            return

        first_elem.clear()
        first_elem.string = combined_text
        first_elem["simple-email-parse-attr"] = self.attr_value

        for elem in all_elements[1:]:
            elem.decompose()


DEFAULT_ADAPTERS = [
    DividerHeaderAdapter(attr_value="divider"),
    EndDividerHeaderAdapter(attr_value="end_divider"),
    MultipleDivHeaderAdapter(attr_value="quote_header_multiple_block"),
    KeyValueHeaderAdapter(attr_value="quote_header_block"),
    OnelineHeaderAdapter(attr_value="quote_header_oneline"),
]
