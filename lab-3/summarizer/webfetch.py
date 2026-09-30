# -*- coding: utf-8 -*-
"""Загрузка документа по ссылке и извлечение из HTML связного текста.

Позволяет реферировать произвольную веб-страницу, не сохраняя её вручную
в файл: пользователь указывает URL, система скачивает страницу, отбрасывает
разметку, скрипты, меню и сноски и получает текст, разбитый на абзацы.

Модуль использует только стандартную библиотеку (urllib + html.parser).
"""
from __future__ import annotations

import gzip
import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) YAZIS-lab3-summarizer/1.0 "
              "(educational project)")
MAX_BYTES = 6 * 1024 * 1024        # ограничение на размер загружаемой страницы
TIMEOUT = 25

#: теги, содержимое которых не является текстом документа
SKIP_TAGS = {"script", "style", "noscript", "svg", "head", "nav", "header",
             "footer", "aside", "form", "button", "select", "textarea",
             "iframe", "figure", "figcaption", "template"}

#: блочные теги, завершающие абзац
BLOCK_TAGS = {"p", "li", "dd", "dt", "blockquote", "pre", "section", "article",
              "div", "tr", "td", "h1", "h2", "h3", "h4", "h5", "h6", "br"}

#: имена классов/идентификаторов служебных блоков. Сравнение строгое, по
#: целому значению class-токена: частичное совпадение приводило к тому, что
#: блок «tm-page__main_has-sidebar» (основной текст статьи!) считался боковой
#: панелью, а «vector-toc-available» на теле страницы Wikipedia — оглавлением.
#: Короткие обрывки меню, которые при этом просачиваются, отсеиваются позже
#: в clean_paragraphs по длине и пунктуации.
SKIP_CLASSES = {
    "infobox", "navbox", "navigation", "nav", "sidebar", "menu", "footer",
    "header", "breadcrumb", "breadcrumbs", "banner", "advert", "ads",
    "cookie", "cookies", "comment", "comments", "related", "share", "social",
    "toc", "toctitle", "metadata", "mw-editsection", "reference", "references",
    "reflist", "noprint", "catlinks", "hatnote", "thumbcaption",
    "shortdescription", "siteSub", "sitesub", "searchbox", "portal",
    "subscribe", "paywall", "popup", "modal", "tooltip", "pagination",
    "mw-navigation", "mw-footer", "mw-jump-link", "mw-references-wrap",
}

#: теги, которые никогда не пропускаются целиком, каким бы ни был их class
NEVER_SKIP_TAGS = {"html", "body", "main", "article"}

#: строчные теги: их пропуск не должен разрывать абзац (иначе сноска [7]
#: внутри предложения разрезала бы его на два)
INLINE_TAGS = {"a", "span", "sup", "sub", "em", "i", "b", "strong", "small",
               "cite", "abbr", "code", "kbd", "q", "mark", "time", "label",
               "u", "s", "font", "big", "var", "samp"}

#: одиночные теги без закрывающей пары — в них нельзя «войти»
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}

_REFERENCE_RE = re.compile(r"\[\s*(?:\d{1,3}|\w{1,4}\s*\d{0,3})\s*\]")
_SPACES_RE = re.compile(r"[ \t ​]+")


class WebFetchError(Exception):
    """Ошибка загрузки страницы, понятная пользователю."""


# ----------------------------------------------------------------------
class _TextExtractor(HTMLParser):
    """Собирает из HTML абзацы связного текста."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self.title: str = ""
        self._buffer: list[str] = []
        self._skip_depth = 0
        self._skip_stack: list[str] = []
        self._in_title = False
        self._headings: list[str] = []

    # --- служебное --------------------------------------------------
    def _flush(self) -> None:
        text = _SPACES_RE.sub(" ", "".join(self._buffer)).strip()
        self._buffer.clear()
        if text:
            self.paragraphs.append(text)

    @staticmethod
    def _is_service(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        """Похож ли элемент на навигацию, сноски или иной служебный блок."""
        if tag in NEVER_SKIP_TAGS:
            return False
        for key, value in attrs:
            if key not in ("class", "id", "role") or not value:
                continue
            if any(token in SKIP_CLASSES for token in value.lower().split()):
                return True
        return False

    # --- обработчики html.parser ------------------------------------
    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "title" and not self.title:
            self._in_title = True       # <title> лежит внутри пропускаемого <head>
            return
        if tag in VOID_TAGS:
            # одиночные теги не открывают область пропуска, иначе разбор
            # «залипнет» на первой же картинке со служебным классом
            if tag == "br" and not self._skip_depth:
                self._flush()
            return
        if self._skip_depth:
            if tag in SKIP_TAGS or self._is_service(tag, attrs):
                self._skip_stack.append(tag)
                self._skip_depth += 1
            elif self._skip_stack and tag == self._skip_stack[-1]:
                self._skip_stack.append(tag)
                self._skip_depth += 1
            return
        if tag in SKIP_TAGS or self._is_service(tag, attrs):
            if tag not in INLINE_TAGS:
                self._flush()          # блочный служебный элемент завершает абзац
            self._skip_stack.append(tag)
            self._skip_depth = 1
            return
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if tag == "title":
            self._in_title = False
            return
        if self._skip_depth:
            if self._skip_stack and self._skip_stack[-1] == tag:
                self._skip_stack.pop()
                self._skip_depth -= 1
            return
        if tag in BLOCK_TAGS:
            self._flush()
        if tag in ("h1", "h2", "h3"):
            if self.paragraphs:
                self._headings.append(self.paragraphs[-1])

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if self._skip_depth:
            return
        self._buffer.append(data)

    def close(self) -> None:          # noqa: D102
        super().close()
        self._flush()


# ----------------------------------------------------------------------
def _validate_url(url: str) -> str:
    """Проверяет схему и адрес, отсекая локальные и служебные хосты."""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise WebFetchError("поддерживаются только ссылки http и https")
    if not parsed.hostname:
        raise WebFetchError("в ссылке не указан адрес сайта")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise WebFetchError(f"не удалось определить адрес узла: {parsed.hostname}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast):
            raise WebFetchError("загрузка страниц из локальной сети запрещена")

    # кириллица и другие не-ASCII символы в ссылке кодируются по RFC 3986,
    # иначе HTTP-запрос нельзя отправить (заголовок должен быть ASCII)
    safe = parsed._replace(
        netloc=parsed.netloc.encode("idna").decode("ascii")
        if any(ord(ch) > 127 for ch in parsed.netloc) else parsed.netloc,
        path=urllib.parse.quote(parsed.path, safe="/%:@!$&'()*+,;=~"),
        query=urllib.parse.quote(parsed.query, safe="/%:@!$&'()*+,;=~?"),
        fragment="",
    )
    return safe.geturl()


def _decode(raw: bytes, headers) -> str:
    encoding = None
    content_type = headers.get("Content-Type", "")
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    if match:
        encoding = match.group(1)
    if not encoding:
        head = raw[:4096].decode("ascii", "ignore")
        match = re.search(r'charset=["\']?([\w-]+)', head, re.I)
        encoding = match.group(1) if match else "utf-8"
    try:
        return raw.decode(encoding, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def clean_paragraphs(paragraphs: list[str]) -> str:
    """Отбрасывает служебные обрывки и склеивает текст документа."""
    result: list[str] = []
    seen: set[str] = set()
    for text in paragraphs:
        text = _REFERENCE_RE.sub("", text).strip()
        text = html.unescape(text)
        if len(text) < 40 and not text.endswith((".", "!", "?", "…")):
            continue
        if text.count("|") > 3 or text.count("•") > 3:
            continue                            # похоже на меню или таблицу
        key = text[:120]
        if key in seen:
            continue                            # повторяющиеся блоки навигации
        seen.add(key)
        result.append(text)
    return "\n\n".join(result)


def fetch_url(url: str) -> dict:
    """Скачивает страницу и возвращает {'title', 'text', 'url', 'chars'}."""
    safe_url = _validate_url(url)
    request = urllib.request.Request(safe_url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
        "Accept-Language": "ru,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            final_url = response.geturl()
            _validate_url(final_url)
            content_type = response.headers.get("Content-Type", "")
            if content_type and not any(t in content_type.lower() for t in
                                        ("text/html", "text/plain", "xhtml", "xml")):
                raise WebFetchError(f"страница имеет неподдерживаемый тип: {content_type}")
            raw = response.read(MAX_BYTES + 1)
            encoding = (response.headers.get("Content-Encoding") or "").lower()
            headers = response.headers
    except urllib.error.HTTPError as exc:
        raise WebFetchError(f"сервер ответил кодом {exc.code} ({exc.reason})") from exc
    except urllib.error.URLError as exc:
        raise WebFetchError(f"не удалось соединиться с сайтом: {exc.reason}") from exc
    except TimeoutError as exc:
        raise WebFetchError("сайт не ответил за отведённое время") from exc

    if len(raw) > MAX_BYTES:
        raise WebFetchError("страница слишком большая (более 6 МБ)")
    if encoding == "gzip":
        raw = gzip.decompress(raw)
    elif encoding == "deflate":
        raw = zlib.decompress(raw, -zlib.MAX_WBITS)

    document = _decode(raw, headers)

    if "html" not in (headers.get("Content-Type", "") or "").lower() \
            and "<html" not in document[:2000].lower():
        text = clean_paragraphs([p for p in re.split(r"\n\s*\n", document)])
        title = urllib.parse.urlparse(final_url).path.rsplit("/", 1)[-1] or final_url
    else:
        parser = _TextExtractor()
        parser.feed(document)
        parser.close()
        text = clean_paragraphs(parser.paragraphs)
        title = re.split(r"[—|·\-–]\s", parser.title.strip())[0].strip() if parser.title else ""
        if not title:
            title = urllib.parse.urlparse(final_url).path.rsplit("/", 1)[-1] or final_url
        title = urllib.parse.unquote(title.replace("_", " ")).strip()

    if len(text) < 400:
        raise WebFetchError("на странице не найдено связного текста "
                            "(возможно, содержимое подгружается скриптами)")
    return {"title": title[:200], "text": text, "url": final_url, "chars": len(text)}
