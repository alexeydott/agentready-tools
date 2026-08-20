"""Shared bounded page evidence for SEO atomic rules."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from urllib.parse import urljoin

from ..audit_core.collection import FactView
from ..http import FetchError, HttpClient
from ..page_parser import ParsedPage, parse_page
from ..seo_checks import SeoHtmlParser

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SeoPageEvidence:
    url: str
    final_url: str
    status_code: int
    content_type: str
    title: str
    titles: tuple[str, ...]
    description: str
    descriptions: tuple[str, ...]
    h1: tuple[str, ...]
    canonicals: tuple[str, ...]
    hreflangs: tuple[tuple[str, str], ...]
    meta_robots: tuple[str, ...]
    x_robots: str
    jsonld_nodes: tuple[dict[str, object], ...]
    jsonld_errors: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    fetch_error: str | None = None

    @property
    def html(self) -> bool:
        return self.content_type in {"text/html", "application/xhtml+xml"}


def evidence_from_parsed_page(
    page: ParsedPage | FactView,
    *,
    url: str,
    final_url: str,
    status_code: int,
    content_type: str,
    evidence_id: str | None = None,
) -> SeoPageEvidence:
    """Project shared parsed facts into the canonical SEO evidence DTO."""
    parsed = page.page if isinstance(page, FactView) else page
    facts = parsed.facts
    if facts is None:
        raise ValueError("parsed page does not contain shared facts")
    titles = facts.titles
    descriptions = facts.descriptions
    h1 = tuple(item.text for item in facts.headings if item.level == 1)
    canonicals = tuple(urljoin(final_url, item) for item in facts.canonicals)
    hreflangs = tuple((item.lang, urljoin(final_url, item.href)) for item in facts.hreflang)
    x_robots = ", ".join(page.header_values("x-robots-tag")) if isinstance(page, FactView) else ""
    return SeoPageEvidence(
        url=url,
        final_url=final_url,
        status_code=status_code,
        content_type=content_type,
        # ``FactView`` projects a ``CollectedPage`` and deliberately exposes
        # facts, not legacy parser attributes such as ``title``.  Keep the
        # canonical projection safe for both shared page representations.
        title=titles[0] if titles else "",
        titles=titles,
        description=descriptions[0] if descriptions else "",
        descriptions=descriptions,
        h1=h1,
        canonicals=canonicals,
        hreflangs=hreflangs,
        meta_robots=facts.meta_robots,
        x_robots=x_robots,
        jsonld_nodes=facts.jsonld_nodes,
        jsonld_errors=facts.jsonld_errors,
        evidence_ids=(evidence_id or _evidence_id(url, "page"),),
    )


def collect_page_evidence(url: str, client: HttpClient) -> SeoPageEvidence:
    """Fetch and parse one page once so all atomic rules share identical facts."""
    evidence_id = _evidence_id(url, "page")
    try:
        response = client.get(url)
    except FetchError as exc:
        logger.debug("[WP6.2] SEO evidence fetch failed url=%s error=%s", url, exc)
        return SeoPageEvidence(
            url, url, 0, "", "", (), "", (), (), (), (), (), "", (), (), (evidence_id,), str(exc)
        )
    content_type = response.content_type
    if response.status_code != 200 or content_type not in {"text/html", "application/xhtml+xml"}:
        return SeoPageEvidence(
            url, response.url, response.status_code, content_type, "", (), "", (), (), (), (), (), "",
            (), (), (evidence_id,), f"HTTP {response.status_code} {content_type or 'no content-type'}"
        )
    parser = SeoHtmlParser()
    parser.feed(response.text)
    parser.close()
    shared_facts = parse_page(response.body).facts
    if shared_facts is None:
        raise ValueError("shared parser did not produce facts")
    canonicals = tuple(urljoin(response.url, value) for value in parser.canonicals)
    hreflangs = tuple((code, urljoin(response.url, href)) for code, href in parser.hreflangs)
    logger.debug("[WP6.2] SEO evidence collected url=%s jsonld=%d", response.url, len(shared_facts.jsonld_nodes))
    return SeoPageEvidence(
        url=url,
        final_url=response.url,
        status_code=response.status_code,
        content_type=content_type,
        title=parser.title,
        titles=tuple(parser.titles),
        description=parser.description,
        descriptions=tuple(parser.descriptions),
        h1=tuple(parser.h1),
        canonicals=canonicals,
        hreflangs=hreflangs,
        meta_robots=tuple(parser.meta_robots),
        x_robots=parser.x_robots,
        jsonld_nodes=shared_facts.jsonld_nodes,
        jsonld_errors=shared_facts.jsonld_errors,
        evidence_ids=(evidence_id,),
    )


def _evidence_id(url: str, kind: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"seo:{kind}:{digest}"
