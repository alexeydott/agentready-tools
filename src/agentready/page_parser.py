"""Shared parsed-page representation with optional Lexbor/selectolax acceleration."""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True, slots=True)
class ParsedPage:
    title: str
    links: tuple[str, ...]
    resources: tuple[str, ...]
    text: str
    parser_backend: str


class _FallbackParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = []
        self.links: list[str] = []
        self.resources: list[str] = []
        self.text: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")
        if tag in {"img", "script", "iframe", "link", "source"}:
            candidate = values.get("src") or values.get("href")
            if candidate:
                self.resources.append(candidate)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title.append(data)
        self.text.append(data)


def parse_page(body: bytes) -> ParsedPage:
    try:
        from selectolax.lexbor import LexborHTMLParser
    except ImportError:
        parser = _FallbackParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        return ParsedPage(
            title=" ".join("".join(parser.title).split()),
            links=tuple(dict.fromkeys(parser.links)),
            resources=tuple(dict.fromkeys(parser.resources)),
            text=" ".join(" ".join(parser.text).split()),
            parser_backend="stdlib-htmlparser",
        )
    document = LexborHTMLParser(body)
    title_node = document.css_first("title")
    links = tuple(dict.fromkeys(node.attributes.get("href", "") for node in document.css("a[href]")))
    resources = tuple(dict.fromkeys(
        node.attributes.get("src") or node.attributes.get("href", "")
        for node in document.css("img[src],script[src],iframe[src],link[href],source[src]")
    ))
    return ParsedPage(
        title=" ".join((title_node.text() if title_node else "").split()),
        links=tuple(link for link in links if link),
        resources=tuple(resource for resource in resources if resource),
        text=" ".join(document.text().split()),
        parser_backend="selectolax-lexbor",
    )
