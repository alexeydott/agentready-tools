"""Bounded sitemap/crawl inventory reconciliation and export helpers."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
import csv
import hashlib
import io
import logging
from typing import TYPE_CHECKING, Any
from xml.etree.ElementTree import Element, SubElement, tostring

from .sitemap import SitemapLimits, classify_sitemap_scope, parse_sitemap_collection

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .query_service import QueryService, QuerySpec


@dataclass(frozen=True, slots=True)
class SitemapReconciliation:
    sitemap_only: tuple[str, ...]
    crawl_only: tuple[str, ...]
    common: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SitemapClassification:
    """Bounded URL classifications derived from sitemap and crawl facts."""

    sitemap_only: tuple[str, ...] = ()
    crawl_only: tuple[str, ...] = ()
    broken: tuple[str, ...] = ()
    redirects: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    noindex: tuple[str, ...] = ()
    noncanonical: tuple[str, ...] = ()
    out_of_scope: tuple[str, ...] = ()
    orphan_candidate: tuple[str, ...] = ()

    @property
    def categories(self) -> dict[str, tuple[str, ...]]:
        return {
            "sitemap_only": self.sitemap_only,
            "crawl_only": self.crawl_only,
            "broken": self.broken,
            "redirects": self.redirects,
            "blocked": self.blocked,
            "noindex": self.noindex,
            "noncanonical": self.noncanonical,
            "out_of_scope": self.out_of_scope,
            "orphan_candidate": self.orphan_candidate,
        }


@dataclass(frozen=True, slots=True)
class SitemapReconciliationReport:
    """Deterministic, exportable reconciliation projection over stored facts."""

    sitemap_id: str
    classifications: SitemapClassification
    sitemap_urls: tuple[str, ...]
    source_count: int

    def page(self, category: str, *, cursor: str | None = None, limit: int = 100) -> dict[str, object]:
        if category not in self.classifications.categories:
            raise ValueError("unsupported sitemap classification")
        if limit <= 0 or limit > 1000:
            raise ValueError("query limit must be between 1 and 1000")
        values = self.classifications.categories[category]
        if cursor is not None:
            values = tuple(item for item in values if item > cursor)
        selected = values[: limit + 1]
        items = selected[:limit]
        return {"category": category, "items": list(items), "next_cursor": items[-1] if len(selected) > limit else None, "total": len(values)}

    def export(self, category: str, format: str = "json") -> str:
        page = self.page(category, limit=1000)
        items = page["items"]
        if format == "json":
            import json
            return json.dumps({"sitemap_id": self.sitemap_id, **page}, ensure_ascii=False, sort_keys=True)
        if format == "csv":
            output = io.StringIO()
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(("category", "url"))
            writer.writerows((category, item) for item in items)
            return output.getvalue()
        raise ValueError("unsupported export format")


def classify_sitemap_records(
    sitemap_urls: tuple[str, ...] | list[str],
    records: Mapping[str, Mapping[str, Any]],
    *,
    limit: int = 100_000,
) -> SitemapClassification:
    """Classify sitemap URLs using already-collected bounded crawl facts."""
    if limit <= 0 or limit > 100_000:
        raise ValueError("classification limit must be between 1 and 100000")
    sitemap = set(sitemap_urls[:limit])
    crawled = set(records)
    sitemap_only = sorted(sitemap - crawled)
    crawl_only = sorted(crawled - sitemap)
    broken: list[str] = []
    redirects: list[str] = []
    blocked: list[str] = []
    noindex: list[str] = []
    noncanonical: list[str] = []
    for url in sorted(sitemap & crawled):
        facts = records[url]
        status = int(facts.get("status_code", 0) or 0)
        if status >= 400:
            broken.append(url)
        elif 300 <= status < 400:
            redirects.append(url)
        if bool(facts.get("blocked")):
            blocked.append(url)
        if bool(facts.get("noindex")):
            noindex.append(url)
        canonical = facts.get("canonical")
        if isinstance(canonical, str) and canonical.rstrip("/") != url.rstrip("/"):
            noncanonical.append(url)
    return SitemapClassification(
        tuple(sitemap_only),
        tuple(crawl_only),
        tuple(broken),
        tuple(redirects),
        tuple(blocked),
        tuple(noindex),
        tuple(noncanonical),
        (),
        tuple(sitemap_only),
    )


def build_reconciliation_report(
    documents: Iterable[bytes | str],
    records: Mapping[str, Mapping[str, Any]],
    *,
    origin: str,
    limit: int = 100_000,
    sitemap_id: str | None = None,
) -> SitemapReconciliationReport:
    """Parse supplied sitemap documents and reconcile against stored crawl facts.

    Documents are parsed locally; nested indexes must be supplied as bounded
    documents by the caller. Cross-origin URLs are excluded from classification.
    """
    if not origin.strip():
        raise ValueError("origin must not be empty")
    payloads = tuple(item.encode("utf-8") if isinstance(item, str) else item for item in documents)
    parsed = parse_sitemap_collection(payloads, limits=SitemapLimits(max_urls_total=limit))
    raw_urls = tuple(url for result in parsed for url in result.urls)
    scoped = classify_sitemap_scope(raw_urls, origin)
    urls = tuple(sorted(dict.fromkeys(scoped.same_origin)))
    classification = classify_sitemap_records(urls, records, limit=limit)
    classification = replace(classification, out_of_scope=tuple(sorted(scoped.cross_origin_unknown)))
    generated_id = sitemap_id or hashlib.sha256("\n".join(urls).encode("utf-8")).hexdigest()[:16]
    logger.info("sitemap reconciliation sitemap_id=%s sources=%d classifications=%s", generated_id, len(payloads), {key: len(value) for key, value in classification.categories.items()})
    return SitemapReconciliationReport(generated_id, classification, urls, len(payloads))


def reconcile_sitemap_urls(
    sitemap_urls: tuple[str, ...] | list[str],
    crawled_urls: tuple[str, ...] | list[str],
    *,
    limit: int = 100_000,
) -> SitemapReconciliation:
    if limit <= 0 or limit > 100_000:
        raise ValueError("reconciliation limit must be between 1 and 100000")
    sitemap = set(sitemap_urls[:limit])
    crawl = set(crawled_urls[:limit])
    return SitemapReconciliation(
        tuple(sorted(sitemap - crawl)),
        tuple(sorted(crawl - sitemap)),
        tuple(sorted(sitemap & crawl)),
    )


def chunk_sitemap_urls(urls: tuple[str, ...] | list[str], *, chunk_size: int = 50_000) -> tuple[tuple[str, ...], ...]:
    if chunk_size <= 0 or chunk_size > 50_000:
        raise ValueError("sitemap chunk size must be between 1 and 50000")
    unique = tuple(dict.fromkeys(urls))
    return tuple(tuple(unique[index:index + chunk_size]) for index in range(0, len(unique), chunk_size))


def generate_sitemap_documents(
    urls: tuple[str, ...] | list[str],
    *,
    chunk_size: int = 50_000,
) -> tuple[str, ...]:
    """Render bounded sitemap XML documents from an inventory URL projection."""
    documents: list[str] = []
    for chunk in chunk_sitemap_urls(urls, chunk_size=chunk_size):
        root = Element("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
        for url in chunk:
            url_node = SubElement(root, "url")
            SubElement(url_node, "loc").text = url
        documents.append(tostring(root, encoding="unicode", short_empty_elements=True))
    return tuple(documents)


def generate_sitemap_from_query(
    query_service: QueryService,
    query: QuerySpec,
    *,
    chunk_size: int = 50_000,
    limit: int = 100_000,
) -> tuple[str, ...]:
    """Export a bounded sitemap directly from a typed QuerySpec projection."""
    if limit <= 0 or limit > 100_000:
        raise ValueError("sitemap export limit must be between 1 and 100000")
    urls: list[str] = []
    cursor: str | None = None
    while len(urls) < limit:
        page = query_service.execute(replace(query, cursor=cursor, limit=min(query.limit, limit - len(urls))))
        for item in page.items:
            url = getattr(item, "url_key", None) or getattr(item, "url", None)
            if isinstance(url, str):
                urls.append(url)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    return generate_sitemap_documents(urls, chunk_size=chunk_size)
