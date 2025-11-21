import pathlib
import re

import bs4

import header_adapters


class HtmlProcessor:
    soup: bs4.BeautifulSoup
    encoding: str | None
    html: str
    filepath: str | pathlib.Path
    remove_img: bool

    SYSTEM_TAGS = {"html", "body", "head", "doctype", "style", "meta", "title", "script", "link", "base"}
    ENCODINGS = {"utf-8", "windows-1251"}

    DEFAULT_KEEP_TAGS = {"br"}

    TABLE_TAGS = {"table", "thead", "tbody", "tr", "td", "th", "tfoot", "caption", "colgroup", "col"}

    EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

    BLOCK_TAGS = {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "header",
        "footer",
        "nav",
        "section",
        "article",
        "aside",
        "main",
        "address",
        "figure",
        "figcaption",
        "pre",
        "form",
        "fieldset",
        "center",
        "noscript",
        "dir",
        "menu",
        "details",
        "summary",
    }

    def __init__(
        self,
        filepath: str | pathlib.Path | None = None,
        html: str | None = None,
        soup: bs4.BeautifulSoup | None = None,
        encoding: str | None = None,
        remove_img: bool = False,
    ):
        provided = sum([filepath is not None, html is not None, soup is not None])
        if provided == 0:
            raise ValueError("Необходимо передать один из параметров: filepath, html или soup")
        if provided > 1:
            raise ValueError("Можно передать только один из параметров: filepath, html или soup")

        self.filepath = pathlib.Path(filepath) if filepath is not None else None
        self.encoding = encoding
        self.remove_img = remove_img
        self.html = ""
        self.soup = bs4.BeautifulSoup()

        if filepath is not None:
            self._read_file()
            self._process_html()
        elif html is not None:
            self.html = html
            self._process_html()
        elif soup is not None:
            self.soup = soup
            self.html = str(soup)

        self.process_images()
        self.simplify_links()

    def _read_file(self) -> "HtmlProcessor":
        if self.encoding is not None:
            self.html = self.filepath.read_text(encoding=self.encoding)
            return self
        for encoding in self.ENCODINGS:
            try:
                self.html = self.filepath.read_text(encoding=encoding)
                self.encoding = encoding
                return self
            except UnicodeDecodeError:
                continue

        self.html = self.filepath.read_text(encoding="utf-8", errors="ignore")
        return self

    def _process_html(self) -> "HtmlProcessor":
        if not self.html:
            raise ValueError("html not found")

        if self.html.startswith("\ufeff") or self.html.startswith("п»ї"):
            self.html = self.html.lstrip("\ufeff").lstrip("п»ї")
        self.html = re.sub(r"^\s*<!DOCTYPE[^>]*>", "", self.html, flags=re.IGNORECASE)
        self.soup = bs4.BeautifulSoup(self.html, "html.parser")
        return self

    def process_images(self) -> "HtmlProcessor":
        """
        Обрабатывает теги <img>.
        Заменяет их на <p>![alt](src)</p> или заглушку.
        """
        for img in self.soup.find_all("img"):
            new_p = self.soup.new_tag("p")

            if self.remove_img:
                new_p.string = "ИЗОБРАЖЕНИЕ УДАЛЕНО"
            else:
                src = img.get("src", "")
                alt = img.get("alt", "").strip()

                label = "ИЗОБРАЖЕНИЕ"
                if alt:
                    label += f" {alt}"

                new_p.string = f"![{label}]({src})"

            img.replace_with(new_p)

        return self

    def simplify_links(self) -> "HtmlProcessor":
        """
        Упрощает теги <a>.
        Заменяет их на <span> (если email) или <p>/<span> (если ссылка/картинка).
        """
        for a in self.soup.find_all("a"):
            href = a.get("href", "").strip()
            text = a.get_text(separator=" ", strip=True)

            if not href:
                a.replace_with(text)
                continue

            if self.EMAIL_REGEX.search(text):
                new_tag = self.soup.new_tag("span")
                new_tag.string = f"{text}"
                a.replace_with(new_tag)
            else:
                if text == href:
                    content = text
                else:
                    content = f"[{text}]({href}) "

                if "ИЗОБРАЖЕНИЕ" in text:
                    new_tag = self.soup.new_tag("p")
                else:
                    new_tag = self.soup.new_tag("span")
                new_tag.string = content
                a.replace_with(new_tag)

        return self

    def clear_html(self) -> "HtmlProcessor":
        self.clear_system_tags().clear_empty_tags().clear_attributes()
        return self

    def clear_system_tags(self) -> "HtmlProcessor":
        for tag_name in ["html", "body"]:
            for tag in self.soup.find_all(tag_name):
                tag.unwrap()

        for tag_name in self.SYSTEM_TAGS:
            if tag_name not in ["html", "body"]:
                for tag in self.soup.find_all(tag_name):
                    tag.decompose()

        return self

    def clear_empty_tags(self, keep_tags: set[str] | None = None) -> "HtmlProcessor":
        if keep_tags is None:
            keep_tags = self.DEFAULT_KEEP_TAGS

        changed = True

        while changed:
            changed = False
            for tag in self.soup.find_all():
                if tag.name in keep_tags:
                    continue

                text = tag.get_text(strip=True)
                has_preserved_tags = False
                for child in tag.descendants:
                    if isinstance(child, bs4.Tag) and child.name in keep_tags:
                        has_preserved_tags = True
                        break

                if not text and not has_preserved_tags:
                    tag.decompose()
                    changed = True

        for text_node in self.soup.find_all(string=True):
            if isinstance(text_node, (bs4.Comment, bs4.Doctype)):
                continue
            if text_node.strip() == "":
                text_node.extract()

        return self

    def clear_attributes(self) -> "HtmlProcessor":
        for tag in self.soup.find_all():
            if tag.get("class") and "mail-quote-collapse" in tag.get("class", []):
                tag["simple-email-parse-attr"] = "quote"

            if tag.get("data-type") == "sender":
                tag["simple-email-parse-attr"] = "sender"

            if tag.get("data-type") == "body":
                tag["simple-email-parse-attr"] = "body"

            attrs_to_remove = []
            for attr in tag.attrs:
                if attr == "simple-email-parse-attr":
                    continue
                attrs_to_remove.append(attr)

            for attr in attrs_to_remove:
                del tag[attr]

        return self

    def simplify_tags(self) -> "HtmlProcessor":
        keep_tags = self.TABLE_TAGS | self.DEFAULT_KEEP_TAGS | {"div", "span", "blockquote"}

        for tag in self.soup.find_all():
            if tag.name in keep_tags:
                continue

            if tag.name in self.BLOCK_TAGS:
                tag.name = "div"
            else:
                tag.name = "span"

        return self

    def wrap_orphan_text_nodes(self) -> "HtmlProcessor":
        """
        Оборачивает последовательности сиротных узлов (текст + span) в div.
        Проверяет, является ли обернутый контент заголовком.
        Если НЕ заголовок - не оборачивает.
        """
        import header_adapters

        sequences_to_wrap = []

        for parent in self.soup.find_all():
            children = list(parent.contents)

            i = 0
            while i < len(children):
                if isinstance(children[i], bs4.NavigableString) and not children[i].strip():
                    i += 1
                    continue
                if isinstance(children[i], bs4.Tag) and children[i].name in {"br", "div", "blockquote"}:
                    i += 1
                    continue

                sequence = []
                j = i
                while j < len(children):
                    child = children[j]

                    if isinstance(child, bs4.NavigableString) and not child.strip():
                        j += 1
                        continue

                    if isinstance(child, bs4.Tag) and child.name in {"br", "div", "blockquote"}:
                        break

                    if isinstance(child, bs4.NavigableString) or (
                        isinstance(child, bs4.Tag) and child.name == "span"
                    ):
                        sequence.append(child)
                        j += 1
                    else:
                        break

                if len(sequence) > 1:
                    has_text = any(isinstance(c, bs4.NavigableString) for c in sequence)
                    has_span = any(isinstance(c, bs4.Tag) and c.name == "span" for c in sequence)

                    if has_text and has_span:
                        sequences_to_wrap.append((parent, sequence))

                i = j if j > i else i + 1

        for parent, sequence in sequences_to_wrap:
            if not all(elem.parent == parent for elem in sequence):
                continue

            first_elem = sequence[0]
            insert_index = list(parent.contents).index(first_elem)

            temp_div = self.soup.new_tag("div")
            for elem in sequence:
                temp_div.append(elem.extract())

            is_header = False
            for adapter in header_adapters.DEFAULT_ADAPTERS:
                if adapter.match(temp_div):
                    is_header = True
                    break

            if is_header:
                parent.insert(insert_index, temp_div)
            else:
                for i, elem in enumerate(sequence):
                    parent.insert(insert_index + i, elem.extract() if elem.parent else elem)

        return self

    def unwrap_span(self) -> "HtmlProcessor":
        """
        Удаляет все теги <span>, следуя алгоритму снизу-вверх:
        1. Сначала обрабатываются специальные span (quote_header) -> превращаются в div.
        2. Обрабатываются вложенные span.
        3. Если span содержит div: span удаляется (unwrap), div остается.
        4. Если span текстовый: содержимое склеивается с окружением через пробел.
        """
        for span in self.soup.find_all("span"):
            attr_val = span.get("simple-email-parse-attr")
            if attr_val and str(attr_val).startswith("quote_header"):
                span.name = "div"

        spans = self.soup.find_all("span")
        spans = sorted(spans, key=lambda tag: len(list(tag.parents)), reverse=True)

        for span in spans:
            if span.decomposed:
                continue

            if span.find("div"):
                span.unwrap()
                continue

            has_content = False
            if span.get_text(strip=True):
                has_content = True
            else:
                for child in span.children:
                    if isinstance(child, bs4.Tag):
                        has_content = True
                        break

            if not has_content:
                span.decompose()
                continue

            span.insert_before(" ")
            span.insert_after(" ")
            span.unwrap()

        return self

    def _get_significant_sibling(self, node, direction="next", ignore_br=False):
        """
        Возвращает следующего или предыдущего соседа, игнорируя пустые текстовые узлы.
        :param ignore_br: Если True, также пропускает теги <br>.
        """
        curr = node
        while True:
            curr = curr.next_sibling if direction == "next" else curr.previous_sibling
            if not curr:
                return None

            if isinstance(curr, bs4.NavigableString) and not curr.strip():
                continue

            if ignore_br and isinstance(curr, bs4.Tag) and curr.name == "br":
                continue

            return curr

    def process_headers(self) -> "HtmlProcessor":
        candidates: list[bs4.Tag | bs4.NavigableString] = []
        seen_ids: set[int] = set()

        def add_candidate(node):
            if node and id(node) not in seen_ids:
                if isinstance(node, bs4.NavigableString) and not node.strip():
                    return
                seen_ids.add(id(node))
                candidates.append(node)

        for hr in self.soup.find_all("hr"):
            sibling = self._get_significant_sibling(hr, "next", ignore_br=True)
            add_candidate(sibling)

        for bq in self.soup.find_all("blockquote"):
            first_child = None
            for child in bq.contents:
                if isinstance(child, bs4.Tag):
                    if child.name == "br":
                        continue
                    first_child = child
                    break
                if isinstance(child, bs4.NavigableString) and child.strip():
                    first_child = child
                    break
            add_candidate(first_child)

            prev_sibling = self._get_significant_sibling(bq, "prev", ignore_br=True)

            if prev_sibling:
                add_candidate(prev_sibling)
            else:
                parent = bq.parent
                if parent and parent.name in ["div", "span"]:
                    parent_first_child = None
                    for child in parent.contents:
                        if isinstance(child, bs4.NavigableString) and not child.strip():
                            continue
                        if isinstance(child, bs4.Tag) and child.name == "br":
                            continue

                        parent_first_child = child
                        break

                    if parent_first_child == bq:
                        parent_prev = self._get_significant_sibling(parent, "prev", ignore_br=True)
                        add_candidate(parent_prev)

        for tag_name in ["div", "p", "span"]:
            for tag in self.soup.find_all(tag_name):
                add_candidate(tag)

        def get_depth(node):
            if isinstance(node, bs4.Tag):
                return len(list(node.parents))
            return len(list(node.parents)) + 1 if node.parent else 0

        candidates.sort(key=get_depth, reverse=True)

        for node in candidates:
            if isinstance(node, bs4.Tag) and node.decomposed:
                continue
            if node.parent is None:
                continue

            for adapter in header_adapters.DEFAULT_ADAPTERS:
                if adapter.match(node):
                    adapter.mark(node)
                    break

        return self

    def process_forwarded_messages(self) -> "HtmlProcessor":
        """
        Обрабатывает пересылаемые сообщения (Fwd).
        """
        changed = True
        while changed:
            changed = False
            dividers = self.soup.find_all(attrs={"simple-email-parse-attr": "divider"})

            for divider in dividers:
                if divider.decomposed:
                    continue

                next_elem = self._get_significant_sibling(divider, "next", ignore_br=True)

                if not next_elem or not isinstance(next_elem, bs4.Tag):
                    continue

                attr = next_elem.get("simple-email-parse-attr", "")
                is_header = attr == "quote_header_oneline"

                if not is_header and next_elem.name == "div":
                    first_child = next_elem.find()
                    if first_child and first_child.get("simple-email-parse-attr") == "quote_header_oneline":
                        is_header = True

                if not is_header:
                    continue

                end_marker = None
                content_nodes = []

                curr = divider.next_sibling
                while curr:
                    if isinstance(curr, bs4.Tag) and curr.get("simple-email-parse-attr") == "end_divider":
                        end_marker = curr
                        break
                    content_nodes.append(curr)
                    curr = curr.next_sibling

                bq = self.soup.new_tag("blockquote")
                divider.insert_before(bq)

                for node in content_nodes:
                    bq.append(node)

                divider.decompose()
                if end_marker:
                    end_marker.decompose()

                changed = True
                break

        return self

    def _is_removable_node(self, node: bs4.PageElement) -> bool:
        """
        Проверяет, является ли узел 'мусорным', который можно удалить при распаковке.
        """
        if isinstance(node, bs4.NavigableString):
            return not node.strip()

        if isinstance(node, bs4.Tag):
            if node.name == "br":
                return True
            if node.name == "div":
                for child in node.contents:
                    if not self._is_removable_node(child):
                        return False
                return True

        return False

    def _unwrap_quotes(self):
        """
        Вспомогательный метод для распаковки оберток вокруг blockquote.
        Распаковывает родителя, если blockquote является единственным значимым контентом.
        """
        changed = True
        while changed:
            changed = False
            for bq in self.soup.find_all("blockquote"):
                parent = bq.parent
                if not parent or parent.name not in ("div", "blockquote"):
                    continue

                siblings = parent.contents
                siblings_to_remove = []
                can_unwrap = True

                for sibling in siblings:
                    if sibling is bq:
                        continue

                    if self._is_removable_node(sibling):
                        siblings_to_remove.append(sibling)
                    else:
                        can_unwrap = False
                        break

                if can_unwrap:
                    for s in siblings_to_remove:
                        if isinstance(s, (bs4.Tag, bs4.NavigableString)):
                            s.extract()
                    parent.unwrap()
                    changed = True

    def improve_blockquote(self) -> "HtmlProcessor":
        """
        Улучшает структуру блоков цитат.
        0. Превращает <div simple-email-parse-attr="quote"> в <blockquote> и удаляет атрибут.
        1. Распаковывает хедеры из лишних оберток.
        2. Распаковывает цитаты из лишних оберток (чтобы хедер мог их "увидеть").
        3. Переносит div-хедер (quote_header_*) внутрь следующего blockquote.
        4. Снова распаковывает цитаты (чтобы убрать обертки, ставшие пустыми после переноса хедера).
        """
        for div in self.soup.find_all("div", attrs={"simple-email-parse-attr": "quote"}):
            div.name = "blockquote"
            del div["simple-email-parse-attr"]

        headers = self.soup.find_all(attrs={"simple-email-parse-attr": re.compile(r"^quote_header_")})
        for header in headers:
            while True:
                parent = header.parent
                if not parent or parent.name in ("body", "html", "blockquote"):
                    break

                siblings = parent.contents
                siblings_to_remove = []
                can_unwrap = True

                for sibling in siblings:
                    if sibling is header:
                        continue
                    if self._is_removable_node(sibling):
                        siblings_to_remove.append(sibling)
                    else:
                        can_unwrap = False
                        break

                if can_unwrap:
                    for s in siblings_to_remove:
                        if isinstance(s, (bs4.Tag, bs4.NavigableString)):
                            s.extract()
                    parent.unwrap()
                else:
                    break

        self._unwrap_quotes()

        headers = self.soup.find_all(attrs={"simple-email-parse-attr": re.compile(r"^quote_header_")})

        for header in headers:
            if header.decomposed:
                continue

            next_elem = header.next_sibling
            while next_elem:
                if self._is_removable_node(next_elem):
                    next_elem = next_elem.next_sibling
                    continue
                break

            if isinstance(next_elem, bs4.Tag) and next_elem.name == "blockquote":
                bq_children = [
                    c for c in next_elem.contents if not (isinstance(c, bs4.NavigableString) and not c.strip())
                ]

                if not bq_children:
                    next_elem.insert(0, header)
                    continue

                first_child = bq_children[0]
                is_already_header = False
                if isinstance(first_child, bs4.Tag):
                    attr_val = first_child.get("simple-email-parse-attr", "")
                    if str(attr_val).startswith("quote_header_"):
                        is_already_header = True

                if not is_already_header:
                    next_elem.insert(0, header)

        self._unwrap_quotes()

        return self

    def unwrap_div(self) -> "HtmlProcessor":
        """
        Упрощает структуру div-блоков, обеспечивая плоскую структуру.
        Выполняется в цикле (while changed).

        Правила:
        1. Wrap Orphans: Если найдены "сироты" (текст, таблицы) вне div/blockquote/header -> оборачиваем их в div.
        2. Flattening: Если div содержит структурные блоки (div, blockquote) как ПРЯМЫХ детей -> unwrap.
        3. Backward Merge: Сливаем div с предыдущим div или затягиваем контент.
        4. Forward Suck: Затягиваем следующий контент.
        """

        def _is_quote_header(tag: bs4.PageElement) -> bool:
            if not isinstance(tag, bs4.Tag):
                return False
            attr = tag.get("simple-email-parse-attr", "")
            return str(attr).startswith("quote_header")

        def _is_structural_block(tag: bs4.PageElement) -> bool:
            """
            Возвращает True, если тег является жестким структурным блоком.
            Таблицы (TABLE) считаются контентом (сиротами), если они не внутри div.
            """
            if not isinstance(tag, bs4.Tag):
                return False
            if _is_quote_header(tag):
                return True
            separators = {"div", "blockquote", "hr", "center", "form", "header", "footer", "ul", "ol"}
            return tag.name in separators

        def _has_structural_children(tag: bs4.Tag) -> bool:
            for child in tag.children:
                if _is_structural_block(child):
                    return True
            return False

        def _ends_with_br(tag: bs4.Tag) -> bool:
            if not tag.contents:
                return False
            last = tag.contents[-1]
            if isinstance(last, bs4.Tag) and last.name == "br":
                return True
            if isinstance(last, bs4.Tag):
                return _ends_with_br(last)
            return False

        def _starts_with_br(tag: bs4.Tag) -> bool:
            if not tag.contents:
                return False
            first = tag.contents[0]
            if isinstance(first, bs4.Tag) and first.name == "br":
                return True
            return False

        def _wrap_orphans_in_container(container: bs4.Tag) -> bool:
            """
            Ищет последовательности не-блочных элементов и оборачивает их в div.
            """
            modified = False
            orphans = []
            children = list(container.contents)

            for child in children:
                is_empty_text = isinstance(child, bs4.NavigableString) and not child.strip()

                if _is_structural_block(child):
                    if orphans:
                        new_div = self.soup.new_tag("div")
                        orphans[0].insert_before(new_div)
                        for o in orphans:
                            new_div.append(o)
                        orphans = []
                        modified = True
                else:
                    if is_empty_text and not orphans:
                        continue
                    orphans.append(child)

            if orphans:
                new_div = self.soup.new_tag("div")
                orphans[0].insert_before(new_div)
                for o in orphans:
                    new_div.append(o)
                modified = True

            return modified

        changed = True
        loop_counter = 0
        MAX_LOOPS = 100

        while changed and loop_counter < MAX_LOOPS:
            changed = False
            loop_counter += 1

            containers = [self.soup] + self.soup.find_all("blockquote")
            for container in containers:
                if _wrap_orphans_in_container(container):
                    changed = True

            if changed:
                continue

            divs = self.soup.find_all("div")
            divs = sorted(divs, key=lambda tag: len(list(tag.parents)), reverse=True)

            for div in divs:
                if div.decomposed:
                    continue

                if _is_quote_header(div):
                    continue

                if _has_structural_children(div):
                    div.unwrap()
                    changed = True
                    continue

                prev = self._get_significant_sibling(div, "prev", ignore_br=False)
                if prev:
                    if isinstance(prev, bs4.Tag) and prev.name == "div" and not _is_quote_header(prev):
                        needs_br = True
                        if _ends_with_br(prev) or _starts_with_br(div):
                            needs_br = False

                        if needs_br:
                            prev.append(self.soup.new_tag("br"))

                        for child in list(div.contents):
                            prev.append(child)

                        div.decompose()
                        changed = True
                        continue

                    if not _is_quote_header(prev) and not _is_structural_block(prev):
                        is_prev_br = isinstance(prev, bs4.Tag) and prev.name == "br"
                        needs_br = False
                        if not is_prev_br and not _starts_with_br(div):
                            needs_br = True

                        prev.extract()
                        if needs_br:
                            div.insert(0, self.soup.new_tag("br"))
                        div.insert(0, prev)

                        changed = True
                        continue

                next_node = self._get_significant_sibling(div, "next", ignore_br=False)
                if next_node:
                    if not _is_quote_header(next_node) and not _is_structural_block(next_node):
                        is_next_br = isinstance(next_node, bs4.Tag) and next_node.name == "br"
                        needs_br = False
                        if not is_next_br and not _ends_with_br(div):
                            needs_br = True

                        next_node.extract()
                        if needs_br:
                            div.append(self.soup.new_tag("br"))
                        div.append(next_node)

                        changed = True
                        continue

        return self

    def ensure_blockquote(self) -> "HtmlProcessor":
        """
        Оборачивает блоки, идущие после quote_header, в blockquote, если они еще не там.
        Жадный алгоритм: захватывает все элементы до следующего хедера или конца контейнера.
        """
        headers = self.soup.find_all(attrs={"simple-email-parse-attr": re.compile(r"^quote_header_")})

        for header in headers:
            if header.decomposed:
                continue

            parent = header.parent
            if not parent:
                continue

            is_first_child = False
            for child in parent.contents:
                if isinstance(child, bs4.NavigableString) and not child.strip():
                    continue
                if child is header:
                    is_first_child = True
                break

            if parent.name == "blockquote" and is_first_child:
                continue

            bq = self.soup.new_tag("blockquote")
            header.insert_before(bq)
            bq.append(header)

            while True:
                next_sibling = bq.next_sibling
                if not next_sibling:
                    break

                if isinstance(next_sibling, bs4.Tag):
                    attr = next_sibling.get("simple-email-parse-attr", "")
                    if str(attr).startswith("quote_header_"):
                        break

                bq.append(next_sibling)

        return self

    def nest_neighboring_quotes(self) -> "HtmlProcessor":
        """
        Проходит по всем blockquote снизу вверх.
        Если перед цитатой стоит другая цитата (сосед), то текущая цитата
        И ВСЕ ЕЁ ПОСЛЕДУЮЩИЕ СОСЕДИ перемещаются внутрь предыдущей (в конец).
        """
        quotes = self.soup.find_all("blockquote")

        for quote in reversed(quotes):
            if quote.decomposed:
                continue

            prev = self._get_significant_sibling(quote, "prev", ignore_br=False)

            if prev and isinstance(prev, bs4.Tag) and prev.name == "blockquote":
                nodes_to_move = [quote]
                curr_sibling = quote.next_sibling
                while curr_sibling:
                    nodes_to_move.append(curr_sibling)
                    curr_sibling = curr_sibling.next_sibling

                for node in nodes_to_move:
                    prev.append(node)

        return self

    def move_remnants(self) -> "HtmlProcessor":
        """
        Проходит сверху вниз.
        Если после цитаты есть соседи ("остатки"), переносит их в div ПЕРЕД цитатой,
        объединяя с содержимым этого div'а.
        Затем рекурсивно заходит внутрь цитаты.
        """
        curr_container = self.soup

        def _is_quote_header(tag: bs4.PageElement) -> bool:
            if not isinstance(tag, bs4.Tag):
                return False
            attr = tag.get("simple-email-parse-attr", "")
            return str(attr).startswith("quote_header")

        while True:
            quote = None
            for child in curr_container.children:
                if isinstance(child, bs4.Tag) and child.name == "blockquote":
                    quote = child
                    break

            if not quote:
                break

            target_div = None
            prev = quote.previous_sibling
            while prev:
                if isinstance(prev, bs4.Tag) and prev.name == "div":
                    if not _is_quote_header(prev):
                        target_div = prev
                    break
                if isinstance(prev, bs4.NavigableString) and not prev.strip():
                    prev = prev.previous_sibling
                    continue
                break

            if not target_div:
                target_div = self.soup.new_tag("div")
                quote.insert_before(target_div)

            remnants = []
            next_node = quote.next_sibling
            while next_node:
                remnants.append(next_node)
                next_node = next_node.next_sibling

            if remnants:

                def ends_with_br(tag):
                    if not tag.contents:
                        return False
                    last = tag.contents[-1]
                    return isinstance(last, bs4.Tag) and last.name == "br"

                if target_div.contents and not ends_with_br(target_div):
                    target_div.append(self.soup.new_tag("br"))

                for node in remnants:
                    node = node.extract()

                    if isinstance(node, bs4.Tag) and node.name == "div":
                        if not node.contents:
                            continue

                        if target_div.contents and not ends_with_br(target_div):
                            target_div.append(self.soup.new_tag("br"))

                        for child in list(node.contents):
                            target_div.append(child)
                    else:
                        is_br = isinstance(node, bs4.Tag) and node.name == "br"

                        if not is_br and target_div.contents and not ends_with_br(target_div):
                            target_div.append(self.soup.new_tag("br"))

                        target_div.append(node)

            curr_container = quote

        return self

    def convert_br_to_newlines(self) -> "HtmlProcessor":
        """
        Преобразует <br> в \n и нормализует пробелы/переносы.
        Rule:
        1. <br> -> \n
        2. SHY (\xad) -> "" (удаляется)
        3. &nbsp; -> ' ' (и схлопывание пробелов)
        4. Пробелы вокруг \n удаляются
        5. 2+ \n -> \n\n
        """
        space_regex = re.compile(r"[ \t\xa0]+")
        newline_space_regex = re.compile(r" *\n *")
        multi_newline_regex = re.compile(r"\n{2,}")

        containers = self.soup.find_all(["div", "blockquote", "p", "li", "td", "th"])

        for container in containers:
            if container.decomposed:
                continue

            new_contents = []
            buffer = ""

            children = list(container.contents)

            for child in children:
                if isinstance(child, bs4.Tag) and child.name in self.BLOCK_TAGS | self.TABLE_TAGS | {
                    "blockquote"
                }:
                    if buffer:
                        new_contents.append(bs4.NavigableString(buffer))
                        buffer = ""
                    new_contents.append(child)
                    continue

                if isinstance(child, bs4.Tag) and child.name == "br":
                    buffer += "\n"
                    continue

                if isinstance(child, bs4.NavigableString):
                    buffer += str(child)
                    continue

                if buffer:
                    new_contents.append(bs4.NavigableString(buffer))
                    buffer = ""
                new_contents.append(child)

            if buffer:
                new_contents.append(bs4.NavigableString(buffer))

            final_contents = []
            for item in new_contents:
                if isinstance(item, bs4.NavigableString):
                    text = str(item)

                    text = text.replace("\xad", "")
                    text = space_regex.sub(" ", text)
                    text = newline_space_regex.sub("\n", text)
                    text = multi_newline_regex.sub("\n\n", text)

                    if text:
                        final_contents.append(bs4.NavigableString(text))
                else:
                    final_contents.append(item)

            container.clear()
            for item in final_contents:
                container.append(item)

        return self

    def process(self):
        (
            self.clear_html()
            .simplify_tags()
            .wrap_orphan_text_nodes()
            .process_headers()
            .unwrap_span()
            .process_forwarded_messages()
            .improve_blockquote()
            .unwrap_div()
            .ensure_blockquote()
            .nest_neighboring_quotes()
            .move_remnants()
            .convert_br_to_newlines()
        )


if __name__ == "__main__":
    processor = HtmlProcessor("tests/data/email_16.htm", remove_img=True)
    processor.process()
    print(processor.soup)
