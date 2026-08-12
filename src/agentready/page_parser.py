"""Shared parsed-page representation and typed HTML facts."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from html.parser import HTMLParser
from urllib.parse import urljoin


class RepresentationSource(StrEnum):
    STATIC_HTML = "static-html"
    RENDERED_DOM = "rendered-dom"
    MARKDOWN = "markdown"
    JSON = "json"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Representation:
    representation_id: str
    run_id: str
    url_key: str
    source: str
    content_type: str
    body_hash: str
    byte_size: int
    observed_at: str

    @classmethod
    def from_body(
        cls,
        body: bytes,
        *,
        representation_id: str | None = None,
        run_id: str = "",
        url_key: str = "",
        source: str = RepresentationSource.STATIC_HTML,
        content_type: str = "text/html",
        observed_at: str | None = None,
    ) -> Representation:
        digest = hashlib.sha256(body).hexdigest()
        return cls(
            representation_id or f"{source}:{digest}",
            run_id,
            url_key,
            str(source),
            content_type,
            digest,
            len(body),
            observed_at or datetime.now(UTC).isoformat(),
        )


@dataclass(frozen=True, slots=True)
class LinkOccurrence:
    source_representation_id: str
    ordinal: int
    raw_href: str
    resolved_url: str | None = None
    anchor_text: str = ""
    rel: str = ""
    element: str = "a"
    dom_path: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceOccurrence:
    source_representation_id: str
    ordinal: int
    url: str
    resource_type: str
    resolved_url: str | None = None
    element: str = ""
    dom_path: str | None = None

    @property
    def raw_url(self) -> str:
        return self.url


@dataclass(frozen=True, slots=True)
class ImageFact:
    src: str
    alt: str | None = None
    title: str | None = None
    srcset: str | None = None
    loading: str | None = None
    width: int | None = None
    height: int | None = None
    status_code: int | None = None
    content_length: int | None = None
    content_type: str | None = None


@dataclass(frozen=True, slots=True)
class HeadingFact:
    level: int
    text: str


@dataclass(frozen=True, slots=True)
class HreflangFact:
    lang: str
    href: str


@dataclass(frozen=True, slots=True)
class FormFact:
    action: str | None = None
    method: str | None = None


@dataclass(frozen=True, slots=True)
class StructuredDataMarker:
    kind: str
    ordinal: int


@dataclass(frozen=True, slots=True)
class ParsedFacts:
    titles: tuple[str, ...] = ()
    descriptions: tuple[str, ...] = ()
    headings: tuple[HeadingFact, ...] = ()
    meta_robots: tuple[str, ...] = ()
    canonicals: tuple[str, ...] = ()
    hreflang: tuple[HreflangFact, ...] = ()
    base_href: str | None = None
    lang: str | None = None
    links: tuple[LinkOccurrence, ...] = ()
    images: tuple[ImageFact, ...] = ()
    resources: tuple[ResourceOccurrence, ...] = ()
    forms: tuple[FormFact, ...] = ()
    jsonld_markers: tuple[StructuredDataMarker, ...] = ()
    microdata_markers: tuple[StructuredDataMarker, ...] = ()
    visible_text: str = ""
    raw_text_signature_inputs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedPage:
    """Compatibility page projection plus the single typed facts contract."""

    title: str
    links: tuple[str, ...]
    resources: tuple[str, ...]
    text: str
    parser_backend: str
    representation: Representation | None = None
    facts: ParsedFacts | None = None


@dataclass
class _LinkBuilder:
    raw_href: str
    rel: str
    text: list[str]


class _FallbackParser(HTMLParser):
    def __init__(self, representation_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.representation_id = representation_id
        self.titles: list[str] = []
        self.descriptions: list[str] = []
        self.headings: list[HeadingFact] = []
        self.meta_robots: list[str] = []
        self.canonicals: list[str] = []
        self.hreflang: list[HreflangFact] = []
        self.base_href: str | None = None
        self.lang: str | None = None
        self.links: list[LinkOccurrence] = []
        self.images: list[ImageFact] = []
        self.resources: list[ResourceOccurrence] = []
        self.forms: list[FormFact] = []
        self.jsonld_markers: list[StructuredDataMarker] = []
        self.microdata_markers: list[StructuredDataMarker] = []
        self.text: list[str] = []
        self._title_depth = 0
        self._title_parts: list[str] = []
        self._heading: tuple[int, list[str]] | None = None
        self._link: _LinkBuilder | None = None
        self._jsonld_depth = 0
        self._jsonld_ordinal = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if values.get("lang") and self.lang is None and tag == "html":
            self.lang = values["lang"].strip() or None
        if tag == "title":
            self._title_depth += 1
            if self._title_depth == 1:
                self._title_parts = []
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading = (int(tag[1]), [])
        if tag == "meta":
            name = values.get("name", "").lower()
            if name in {"description"} and values.get("content"):
                self.descriptions.append(values["content"].strip())
            elif name in {"robots", "googlebot", "bingbot"} and values.get("content"):
                self.meta_robots.append(values["content"].strip())
        if tag == "link" and values.get("href"):
            rel = values.get("rel", "").lower().split()
            href = values["href"].strip()
            if "canonical" in rel:
                self.canonicals.append(href)
            if "alternate" in rel and values.get("hreflang"):
                self.hreflang.append(HreflangFact(values["hreflang"].strip(), href))
        if tag == "base" and values.get("href") and self.base_href is None:
            self.base_href = values["href"].strip()
        if tag == "a" and values.get("href"):
            self._link = _LinkBuilder(values["href"], values.get("rel", ""), [])
        if tag == "img" and values.get("src"):
            self.images.append(ImageFact(
                values["src"], values.get("alt") or None, values.get("title") or None,
                values.get("srcset") or None, values.get("loading") or None,
                _dimension(values.get("width")), _dimension(values.get("height")),
            ))
        if tag in {"img", "script", "iframe", "link", "source"}:
            candidate = values.get("src") or values.get("href")
            if candidate:
                self.resources.append(ResourceOccurrence(
                    self.representation_id,
                    len(self.resources),
                    candidate,
                    tag,
                    element=tag,
                ))
        if tag == "form":
            self.forms.append(FormFact(values.get("action") or None, values.get("method") or None))
        if "itemtype" in values or "itemprop" in values:
            self.microdata_markers.append(StructuredDataMarker("microdata", len(self.microdata_markers)))
        if tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self._jsonld_depth = 1
            self._jsonld_ordinal += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
            if self._title_depth == 0:
                value = _clean_text(" ".join(self._title_parts))
                if value:
                    self.titles.append(value)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._heading is not None:
            level, text = self._heading
            self.headings.append(HeadingFact(level, _clean_text(" ".join(text))))
            self._heading = None
        if tag == "a" and self._link is not None:
            self.links.append(LinkOccurrence(
                self.representation_id,
                len(self.links),
                self._link.raw_href,
                anchor_text=_clean_text(" ".join(self._link.text)),
                rel=self._link.rel,
            ))
            self._link = None
        if tag == "script" and self._jsonld_depth:
            self.jsonld_markers.append(StructuredDataMarker("json-ld", len(self.jsonld_markers)))
            self._jsonld_depth = 0

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._title_depth:
            self._title_parts.append(data)
        if self._heading is not None:
            self._heading[1].append(data)
        if self._link is not None:
            self._link.text.append(data)


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _dimension(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _facts_from_parser(parser: _FallbackParser) -> ParsedFacts:
    visible_text = _clean_text(" ".join(parser.text))
    return ParsedFacts(
        titles=tuple(parser.titles),
        descriptions=tuple(parser.descriptions),
        headings=tuple(parser.headings),
        meta_robots=tuple(parser.meta_robots),
        canonicals=tuple(parser.canonicals),
        hreflang=tuple(parser.hreflang),
        base_href=parser.base_href,
        lang=parser.lang,
        links=tuple(parser.links),
        images=tuple(parser.images),
        resources=tuple(parser.resources),
        forms=tuple(parser.forms),
        jsonld_markers=tuple(parser.jsonld_markers),
        microdata_markers=tuple(parser.microdata_markers),
        visible_text=visible_text,
        raw_text_signature_inputs=(visible_text,),
    )


def _page_from_facts(facts: ParsedFacts, representation: Representation, backend: str) -> ParsedPage:
    base_url = representation.url_key
    if facts.base_href and base_url:
        base_url = urljoin(base_url, facts.base_href)
    if base_url:
        facts = replace(
            facts,
            links=tuple(
                replace(link, resolved_url=link.resolved_url or urljoin(base_url, link.raw_href))
                for link in facts.links
            ),
            resources=tuple(
                replace(resource, resolved_url=resource.resolved_url or urljoin(base_url, resource.url))
                for resource in facts.resources
            ),
        )
    titles = tuple(dict.fromkeys(facts.titles))
    links = tuple(dict.fromkeys(link.raw_href for link in facts.links))
    resources = tuple(dict.fromkeys(resource.url for resource in facts.resources))
    return ParsedPage(
        title=titles[0] if titles else "",
        links=links,
        resources=resources,
        text=facts.visible_text,
        parser_backend=backend,
        representation=representation,
        facts=facts,
    )


def _parse_with_fallback(body: bytes, representation: Representation, backend: str = "stdlib-htmlparser") -> ParsedPage:
    parser = _FallbackParser(representation.representation_id)
    parser.feed(body.decode("utf-8", errors="replace"))
    return _page_from_facts(_facts_from_parser(parser), representation, backend)


def _parse_with_selectolax(body: bytes, representation: Representation) -> ParsedPage:
    from selectolax.lexbor import LexborHTMLParser

    document = LexborHTMLParser(body)
    titles = tuple(_clean_text(node.text()) for node in document.css("title"))
    descriptions = tuple(
        node.attributes.get("content", "").strip()
        for node in document.css('meta[name="description"]')
        if node.attributes.get("content", "").strip()
    )
    robots = tuple(
        node.attributes.get("content", "").strip()
        for node in document.css("meta")
        if node.attributes.get("name", "").lower() in {"robots", "googlebot", "bingbot"}
        and node.attributes.get("content", "").strip()
    )
    headings = tuple(
        HeadingFact(int(node.tag[1]), _clean_text(node.text()))
        for node in document.css("h1,h2,h3,h4,h5,h6")
    )
    links = tuple(
        LinkOccurrence(
            representation.representation_id,
            ordinal,
            node.attributes.get("href", ""),
            anchor_text=_clean_text(node.text()),
            rel=node.attributes.get("rel", ""),
        )
        for ordinal, node in enumerate(document.css("a[href]"))
    )
    images = tuple(
        ImageFact(
            node.attributes.get("src", ""),
            node.attributes.get("alt") or None,
            node.attributes.get("title") or None,
            node.attributes.get("srcset") or None,
            node.attributes.get("loading") or None,
            _dimension(node.attributes.get("width")),
            _dimension(node.attributes.get("height")),
        )
        for node in document.css("img[src]")
    )
    resources = tuple(
        ResourceOccurrence(
            representation.representation_id,
            ordinal,
            node.attributes.get("src") or node.attributes.get("href", ""),
            node.tag,
            element=node.tag,
        )
        for ordinal, node in enumerate(document.css("img[src],script[src],iframe[src],link[href],source[src]"))
    )
    canonicals = tuple(
        node.attributes.get("href", "")
        for node in document.css('link[rel~="canonical"][href]')
    )
    hreflang = tuple(
        HreflangFact(node.attributes.get("hreflang", ""), node.attributes.get("href", ""))
        for node in document.css('link[rel~="alternate"][hreflang][href]')
    )
    forms = tuple(
        FormFact(node.attributes.get("action") or None, node.attributes.get("method") or None)
        for node in document.css("form")
    )
    microdata = tuple(
        StructuredDataMarker("microdata", ordinal)
        for ordinal, node in enumerate(document.css("[itemtype],[itemprop]"))
    )
    jsonld = tuple(
        StructuredDataMarker("json-ld", ordinal)
        for ordinal, node in enumerate(document.css('script[type="application/ld+json"]'))
    )
    visible_text = _clean_text(document.text())
    facts = ParsedFacts(
        titles=titles,
        descriptions=descriptions,
        headings=headings,
        meta_robots=robots,
        canonicals=canonicals,
        hreflang=hreflang,
        base_href=(document.css_first("base[href]").attributes.get("href") if document.css_first("base[href]") else None),
        lang=(document.css_first("html").attributes.get("lang") if document.css_first("html") else None),
        links=links,
        images=images,
        resources=resources,
        forms=forms,
        jsonld_markers=jsonld,
        microdata_markers=microdata,
        visible_text=visible_text,
        raw_text_signature_inputs=(visible_text,),
    )
    return _page_from_facts(facts, representation, "selectolax-lexbor")


def parse_page(
    body: bytes,
    *,
    representation: Representation | None = None,
) -> ParsedPage:
    """Parse once and return both the typed facts and the compatibility projection."""
    representation = representation or Representation.from_body(body)
    try:
        return _parse_with_selectolax(body, representation)
    except ImportError:
        return _parse_with_fallback(body, representation)
