import datetime
import re

import bs4


class DictMappingBase:
    def __iter__(self):
        return iter(self.keys())

    def keys(self):
        return type(self).__annotations__.keys()

    def __getitem__(self, key):
        value = getattr(self, key)

        if isinstance(value, DictMappingBase):
            return dict(value)

        return value


class Contact(DictMappingBase):
    name: str | None
    email: str

    def __init__(self, email: str, name: str | None = None):
        self.name = name
        self.email = email


class Header(DictMappingBase):
    from_: Contact
    sent: datetime.datetime | None
    to: Contact | None
    subject: str | None

    def __init__(
        self,
        from_: Contact,
        sent: datetime.datetime | None = None,
        to: Contact | None = None,
        subject: str | None = None,
    ):
        self.from_ = from_
        self.sent = sent
        self.to = to
        self.subject = subject

    def __getitem__(self, key):
        key_mapping = {
            "From": "from_",
            "Sent": "sent",
            "To": "to",
            "Subject": "subject",
        }

        attr_name = key_mapping.get(key, key.lower())
        value = getattr(self, attr_name, None)

        if isinstance(value, DictMappingBase):
            return dict(value)
        return value

    def keys(self):
        return ["From", "Sent", "To", "Subject"]


class Message(DictMappingBase):
    """Представление одного сообщения в переписке."""

    header: Header | None
    text: str

    def __init__(self, header: Header | None, text: str):
        self.header = header
        self.text = text


class JsonProcessor:
    html: str
    soup: bs4.BeautifulSoup
    main_contact: Contact | None

    MONTH_MAP = {
        "янв": 1,
        "фев": 2,
        "мар": 3,
        "апр": 4,
        "май": 5,
        "мая": 5,
        "июн": 6,
        "июл": 7,
        "авг": 8,
        "сен": 9,
        "окт": 10,
        "ноя": 11,
        "дек": 12,
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    def __init__(self, html: str | bs4.BeautifulSoup, main_contact: Contact | None = None):
        self.html = str(html)
        self.soup = bs4.BeautifulSoup(self.html, "html.parser") if isinstance(html, str) else html
        self.main_contact = main_contact

    def _extract_messages_recursive(self, element: bs4.Tag) -> list[dict]:
        """
        Рекурсивно извлекает сообщения из HTML структуры.
        Возвращает список словарей с ключами 'header_str' и 'text'.
        """
        messages = []

        header_elem = None
        header_str = None

        if element.name == "blockquote":
            for child in element.children:
                if isinstance(child, bs4.Tag):
                    attr = child.get("simple-email-parse-attr", "")
                    if str(attr).startswith("quote_header_"):
                        header_elem = child
                        header_str = child.get_text(separator=" ", strip=True)
                        break

        text_parts = []
        nested_blockquotes = []

        for child in element.children:
            if child is header_elem:
                continue

            if isinstance(child, bs4.Tag):
                if child.name == "blockquote":
                    nested_blockquotes.append(child)
                else:
                    html_content = child.decode_contents()
                    if html_content.strip():
                        text_parts.append(html_content)
            elif isinstance(child, bs4.NavigableString):
                text = str(child).strip()
                if text:
                    text_parts.append(text)

        current_text = "\n".join(text_parts)

        messages.append({"header_str": header_str, "text": current_text})

        for bq in nested_blockquotes:
            messages.extend(self._extract_messages_recursive(bq))

        return messages

    def _parse_contact(self, contact_str: str) -> Contact | None:
        """
        Парсит строку контакта вида 'Name <email>' или 'email' в объект Contact.
        Примеры:
        - 'КАМИН <hotline@kamin.kaluga.ru>' -> Contact(name='КАМИН', email='hotline@kamin.kaluga.ru')
        - 'hotline@kamin.kaluga.ru' -> Contact(name=None, email='hotline@kamin.kaluga.ru')
        - 'Name email@test.com [email@test.com]' -> Contact(name='Name', email='email@test.com')
        """
        if not contact_str:
            return None

        contact_str = contact_str.strip().strip("'\"")

        email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

        match = re.search(r"^(.+?)\s*[<\[]\s*(?:mailto:)?(" + email_pattern + r")\s*[>\]]", contact_str)
        if match:
            name = match.group(1).strip()
            email = match.group(2).strip()
            name = re.sub(email_pattern, "", name).strip()
            name = name.strip("'\"")
            return Contact(email=email, name=name if name else None)

        match = re.search(r"[<\[]\s*(?:mailto:)?(" + email_pattern + r")\s*[>\]]", contact_str)
        if match:
            email = match.group(1).strip()
            return Contact(email=email, name=None)

        match = re.search(email_pattern, contact_str)
        if match:
            email = match.group(0).strip()
            name_part = contact_str[: match.start()].strip()
            if name_part:
                name_part = name_part.strip("'\"")
                return Contact(email=email, name=name_part)
            return Contact(email=email, name=None)

        return None

    def _parse_datetime(self, date_str: str) -> datetime.datetime | None:
        """
        Парсит строку даты/времени в объект datetime.
        Поддерживает различные форматы:
        - '14.05.2024' (дата без времени)
        - 'Вторник, 14 мая 2024, 17:35 +03:00'
        - 'Wednesday, May 08, 2024 1:34 PM'
        - '21.09.2023, 16:13'
        - 'пт, 15 апр. 2022 г. в 20:47'
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})[,\s]+(\d{1,2}):(\d{2})", date_str)
        if match:
            day, month, year, hour, minute = match.groups()
            return datetime.datetime(int(year), int(month), int(day), int(hour), int(minute))

        match = re.search(
            r"(?:\w+,\s+)?(\d{1,2})\s+(\w+)\.?\s+(\d{4})\s+г\.\s+в\s+(\d{1,2}):(\d{2})",
            date_str,
            re.IGNORECASE | re.UNICODE,
        )
        if match:
            day, month_name, year, hour, minute = match.groups()
            month_name_lower = month_name.lower()[:3]
            month = self.MONTH_MAP.get(month_name_lower)
            if month:
                return datetime.datetime(int(year), month, int(day), int(hour), int(minute))

        match = re.search(
            r"(?:\w+,\s+)?(\w+)\s+(\d{1,2}),\s+(\d{4})\s+(\d{1,2}):(\d{2})\s+(AM|PM)",
            date_str,
            re.IGNORECASE
        )
        if match:
            month_name, day, year, hour, minute, am_pm = match.groups()
            month_name_lower = month_name.lower()[:3]
            month = self.MONTH_MAP.get(month_name_lower)
            if month:
                hour_int = int(hour)
                if am_pm.upper() == "PM" and hour_int != 12:
                    hour_int += 12
                elif am_pm.upper() == "AM" and hour_int == 12:
                    hour_int = 0
                return datetime.datetime(int(year), month, int(day), hour_int, int(minute))

        match = re.search(
            r"(\d{1,2})\s+(\w+)\s+(\d{4})\s+г\.[,\s]+(\d{1,2}):(\d{2}):(\d{2})(?:\s*([+-]\d{2}:\d{2}))?",
            date_str,
            re.IGNORECASE
        )
        if match:
            day, month_name, year, hour, minute, second, tz_offset = match.groups()
            month_name_lower = month_name.lower()[:3]
            month = self.MONTH_MAP.get(month_name_lower)
            if month:
                dt = datetime.datetime(int(year), month, int(day), int(hour), int(minute), int(second))
                if tz_offset:
                    tz_match = re.match(r"([+-])(\d{2}):(\d{2})", tz_offset)
                    if tz_match:
                        sign, tz_hours, tz_mins = tz_match.groups()
                        offset = datetime.timedelta(hours=int(tz_hours), minutes=int(tz_mins))
                        if sign == "-":
                            offset = -offset
                        tz = datetime.timezone(offset)
                        dt = dt.replace(tzinfo=tz)
                return dt

        match = re.search(
            r"(\d{1,2})\s+(\w+)\s+(\d{4})[,\s]+(\d{1,2}):(\d{2})(?:\s*([+-]\d{2}:\d{2}))?", date_str, re.IGNORECASE
        )
        if match:
            day, month_name, year, hour, minute, tz_offset = match.groups()
            month_name_lower = month_name.lower()[:3]
            month = self.MONTH_MAP.get(month_name_lower)
            if month:
                dt = datetime.datetime(int(year), month, int(day), int(hour), int(minute))
                if tz_offset:
                    tz_match = re.match(r"([+-])(\d{2}):(\d{2})", tz_offset)
                    if tz_match:
                        sign, tz_hours, tz_mins = tz_match.groups()
                        offset = datetime.timedelta(hours=int(tz_hours), minutes=int(tz_mins))
                        if sign == "-":
                            offset = -offset
                        tz = datetime.timezone(offset)
                        dt = dt.replace(tzinfo=tz)
                return dt

        match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", date_str)
        if match:
            day, month, year = match.groups()
            return datetime.datetime(int(year), int(month), int(day), 0, 0, 0)

        return None

    def _parse_header_block(self, header_str: str) -> Header | None:
        """
        Парсит блочный заголовок (quote_header_block).
        Формат: "From: ... Sent: ... To: ... Subject: ..."
        """
        from_contact = None
        to_contact = None
        sent_date = None
        subject = None

        from_match = re.search(r"\b(?:From|От)\s*:\s*(.+?)(?=\s+\b(?:Sent|Date|Отправлено|Дата|To|Кому)\s*:|$)", header_str, re.IGNORECASE)
        if from_match:
            from_contact = self._parse_contact(from_match.group(1))

        sent_match = re.search(
            r"\b(?:Sent|Date|Отправлено|Дата)\s*:\s*(.+?)(?=\s+\b(?:To|Кому|Subject|Тема|Cc|Копия)\s*:|$)",
            header_str,
            re.IGNORECASE,
        )
        if sent_match:
            sent_date = self._parse_datetime(sent_match.group(1))

        to_match = re.search(
            r"\b(?:To|Кому)\s*:\s*(.+?)(?=\s+\b(?:Subject|Тема|Cc|Копия)\s*:|$)", header_str, re.IGNORECASE
        )
        if to_match:
            to_contact = self._parse_contact(to_match.group(1))

        subject_match = re.search(r"\b(?:Subject|Тема)\s*:\s*(.+?)(?=\s+\b(?:Cc|Копия)\s*:|$)", header_str, re.IGNORECASE)
        if subject_match:
            subject = subject_match.group(1).strip()

        if not from_contact:
            return None

        return Header(from_=from_contact, sent=sent_date, to=to_contact, subject=subject)

    def _parse_header_oneline(self, header_str: str) -> Header | None:
        """
        Парсит однострочный заголовок (quote_header_oneline).
        Формат: "Вторник, 14 мая 2024, 17:35 +03:00 от КАМИН <hotline@kamin.kaluga.ru>:"
        или: "21.09.2023, 16:13, 'КАМИН' <hotline@kamin.kaluga.ru>:"
        или: "пт, 15 апр. 2022 г. в 20:47, КАМИН <hotline@kamin.kaluga.ru>:"
        или: "Вы писали 8 мая 2024 г., 13:55:58:" (использует main_contact)
        """
        if re.search(r"^Вы\s+писали\s+", header_str, re.IGNORECASE):
            sent_date = self._parse_datetime(header_str)
            if self.main_contact:
                return Header(from_=self.main_contact, sent=sent_date, to=None, subject=None)
            return None

        sent_date = self._parse_datetime(header_str)

        from_contact = None

        email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        email_match = re.search(email_pattern, header_str)

        if email_match:
            email = email_match.group(0)

            time_match = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)", header_str)
            if time_match:
                after_time = header_str[time_match.end() :].strip()
                after_time = re.sub(r"^\s*[+-]\d{2}:\d{2}\s*", "", after_time)
                after_time = re.sub(r"^[,\s]*(?:от|from)?\s*", "", after_time, flags=re.IGNORECASE)

                name_match = re.search(r"^['\"]*(.+?)['\"]*\s*[<\[]?\s*" + re.escape(email), after_time)
                if name_match:
                    name_part = name_match.group(1).strip().strip("'\"").strip(",")
                    from_contact = Contact(email=email, name=name_part if name_part else None)
                else:
                    from_contact = Contact(email=email, name=None)
            else:
                from_contact = self._parse_contact(header_str)

        if not from_contact:
            return None

        return Header(from_=from_contact, sent=sent_date, to=None, subject=None)

    def _parse_header_string(self, header_str: str) -> Header | None:
        """
        Парсит строку заголовка и возвращает объект Header.
        Автоматически определяет тип заголовка (block или oneline).
        """
        if not header_str:
            return None

        if re.search(r"(?:From|От)\s*:", header_str, re.IGNORECASE):
            return self._parse_header_block(header_str)
        else:
            return self._parse_header_oneline(header_str)

    def extract_messages(self) -> list[dict]:
        """
        Извлекает все сообщения из HTML.
        Возвращает список словарей с ключами 'header_str' и 'text'.
        """
        return self._extract_messages_recursive(self.soup)

    def parse_messages(self, messages_data: list[dict]) -> list[Message]:
        """
        Парсит список сообщений (словари с header_str и text) в список объектов Message.
        """
        messages = []
        for msg_data in messages_data:
            header_str = msg_data.get("header_str")
            text = msg_data.get("text", "")

            if header_str:
                header = self._parse_header_string(header_str)
            else:
                if self.main_contact:
                    header = Header(from_=self.main_contact, sent=None, to=None, subject=None)
                else:
                    header = None

            messages.append(Message(header=header, text=text))

        return messages

    def reverse_messages(self, messages: list[Message]) -> list[Message]:
        """
        Разворачивает порядок сообщений.
        Самое глубокое (последнее в списке) становится первым.
        """
        return list(reversed(messages))

    def _convert_to_msk(self, dt: datetime.datetime | None) -> datetime.datetime | None:
        """
        Конвертирует datetime в московское время (МСК, UTC+3).
        Если timezone не указан, считаем что время уже в МСК.
        """
        if dt is None:
            return None

        # Московское время (UTC+3)
        msk_tz = datetime.timezone(datetime.timedelta(hours=3))

        # Если у datetime нет timezone, считаем что это уже МСК
        if dt.tzinfo is None:
            return dt.replace(tzinfo=msk_tz)

        # Конвертируем в МСК
        return dt.astimezone(msk_tz)

    def process_timestamps(self, messages: list[Message]) -> list[Message]:
        """
        Обрабатывает временные метки для сообщений.
        Если время не указано (sent is None или time == 00:00:00):
        - Для первого сообщения: берем время следующего и вычитаем 1 час
        - Для последнего сообщения: берем время предыдущего и прибавляем 1 час
        - Для остальных: берем среднее между предыдущим и следующим
        """
        for i, msg in enumerate(messages):
            needs_time_calculation = False
            base_date = None

            if msg.header:
                if msg.header.sent is None:
                    needs_time_calculation = True
                elif msg.header.sent.time() == datetime.time(0, 0, 0) and msg.header.sent.tzinfo is None:
                    needs_time_calculation = True
                    base_date = msg.header.sent.date()

            if needs_time_calculation:
                calculated_time = None

                if i == 0:
                    if i + 1 < len(messages) and messages[i + 1].header and messages[i + 1].header.sent:
                        next_time = messages[i + 1].header.sent
                        if next_time.time() != datetime.time(0, 0, 0) or next_time.tzinfo is not None:
                            calculated_time = next_time - datetime.timedelta(hours=1)
                elif i == len(messages) - 1:
                    if i - 1 >= 0 and messages[i - 1].header and messages[i - 1].header.sent:
                        prev_time = messages[i - 1].header.sent
                        if prev_time.time() != datetime.time(0, 0, 0) or prev_time.tzinfo is not None:
                            calculated_time = prev_time + datetime.timedelta(hours=1)
                else:
                    prev_time = None
                    next_time = None

                    for j in range(i - 1, -1, -1):
                        if messages[j].header and messages[j].header.sent:
                            if messages[j].header.sent.time() != datetime.time(0, 0, 0) or messages[j].header.sent.tzinfo is not None:
                                prev_time = messages[j].header.sent
                                break

                    for j in range(i + 1, len(messages)):
                        if messages[j].header and messages[j].header.sent:
                            if messages[j].header.sent.time() != datetime.time(0, 0, 0) or messages[j].header.sent.tzinfo is not None:
                                next_time = messages[j].header.sent
                                break

                    if prev_time and next_time:
                        if prev_time.tzinfo is None and next_time.tzinfo is not None:
                            prev_time = self._convert_to_msk(prev_time)
                        elif prev_time.tzinfo is not None and next_time.tzinfo is None:
                            next_time = self._convert_to_msk(next_time)

                        delta = next_time - prev_time
                        calculated_time = prev_time + delta / 2

                if calculated_time:
                    if base_date:
                        msg.header.sent = datetime.datetime.combine(
                            base_date,
                            calculated_time.time(),
                            tzinfo=calculated_time.tzinfo
                        )
                    else:
                        msg.header.sent = calculated_time

        return messages

    def process(self) -> list[dict]:
        """
        Главный метод обработки.
        Возвращает список словарей, где каждый словарь содержит 'header' и 'text'.
        """
        messages_data = self.extract_messages()
        messages = self.parse_messages(messages_data)
        messages = self.reverse_messages(messages)
        messages = self.process_timestamps(messages)

        for msg in messages:
            if msg.header and msg.header.sent:
                msg.header.sent = self._convert_to_msk(msg.header.sent)

        result = []
        for msg in messages:
            result.append({"header": dict(msg.header) if msg.header else None, "text": msg.text})

        return result


if __name__ == "__main__":
    with open("tests/convert_br_to_newlines/expected_4.htm", "r", encoding="windows-1251") as f:
        processor = JsonProcessor(f.read())
