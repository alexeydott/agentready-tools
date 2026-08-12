"""Bounded, non-networking XML sitemap and sitemap-index parser."""
from __future__ import annotations

import gzip
import io
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


class SitemapEvaluation(StrEnum):
    COMPLETE = "complete"
    PARTIAL_SAFETY_LIMIT = "partial_safety_limit"
    PLATFORM_VIOLATION = "platform_violation"
    MALFORMED = "malformed"


@dataclass(frozen=True, slots=True)
class SitemapLimits:
    max_files: int = 1000
    max_nesting_depth: int = 3
    max_urls_total: int = 50000
    max_compressed_bytes: int = 10 * 1024 * 1024
    max_uncompressed_bytes: int = 50 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class SitemapResult:
    kind: str | None
    urls: tuple[str, ...]
    child_sitemaps: tuple[str, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    evaluation: SitemapEvaluation
    compressed_bytes: int
    uncompressed_bytes: int


class SitemapScopeClass(StrEnum):
    SAME_ORIGIN = "same_origin"
    CROSS_ORIGIN_UNKNOWN = "cross_origin_unknown"
    CROSS_ORIGIN_VERIFIED = "cross_origin_verified"


@dataclass(frozen=True, slots=True)
class SitemapScopeResult:
    same_origin: tuple[str, ...]
    cross_origin_unknown: tuple[str, ...]
    cross_origin_verified: tuple[str, ...]
    warnings: tuple[str, ...]


def parse_sitemap(data: bytes, *, limits: SitemapLimits | None = None, compressed: bool = False, depth: int = 0) -> SitemapResult:
    limits = limits or SitemapLimits()
    if depth > limits.max_nesting_depth:
        return SitemapResult(None, (), (), ("maximum sitemap nesting depth reached",), (), SitemapEvaluation.PARTIAL_SAFETY_LIMIT, 0, 0)
    if len(data) > limits.max_compressed_bytes:
        return SitemapResult(None, (), (), (), ("compressed sitemap exceeds safety limit",), SitemapEvaluation.PARTIAL_SAFETY_LIMIT, len(data), 0)
    try:
        payload = _bounded_decompress(data, limits.max_uncompressed_bytes) if compressed else data
    except (OSError, ValueError) as exc:
        return SitemapResult(None, (), (), (), (str(exc),), SitemapEvaluation.MALFORMED, len(data), 0)
    if len(payload) > limits.max_uncompressed_bytes:
        return SitemapResult(None, (), (), (), ("uncompressed sitemap exceeds safety limit",), SitemapEvaluation.PARTIAL_SAFETY_LIMIT, len(data), len(payload))
    lowered = payload[:4096].lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered or b"<![" in lowered:
        return SitemapResult(None, (), (), (), ("DTD and external entities are forbidden",), SitemapEvaluation.MALFORMED, len(data), len(payload))
    try:
        root, values = _iter_loc_values(payload, limits.max_urls_total)
    except (ET.ParseError, ValueError) as exc:
        return SitemapResult(None, (), (), (), (str(exc),), SitemapEvaluation.MALFORMED, len(data), len(payload))
    local_root = root
    if local_root == "urlset":
        kind, urls, children = "urlset", tuple(values), ()
    elif local_root == "sitemapindex":
        kind, urls, children = "sitemapindex", (), tuple(values)
    else:
        return SitemapResult(None, (), (), (), (f"unexpected root element: {local_root}",), SitemapEvaluation.MALFORMED, len(data), len(payload))
    platform_warning = len(urls) > 50000 or len(children) > 50000
    evaluation = SitemapEvaluation.PLATFORM_VIOLATION if platform_warning else SitemapEvaluation.COMPLETE
    logger.debug("[WP5.3] parsed sitemap kind=%s urls=%d children=%d bytes=%d", kind, len(urls), len(children), len(payload))
    return SitemapResult(kind, urls, children, ("platform URL limit exceeded",) if platform_warning else (), (), evaluation, len(data), len(payload))


def parse_sitemap_collection(
    documents: Iterable[bytes],
    *,
    limits: SitemapLimits | None = None,
    compressed: bool = False,
) -> tuple[SitemapResult, ...]:
    """Parse a bounded set of sitemap documents without fetching or recursing."""
    limits = limits or SitemapLimits()
    results: list[SitemapResult] = []
    for index, document in enumerate(documents):
        if index >= limits.max_files:
            results.append(
                SitemapResult(
                    None, (), (), ("maximum sitemap file count reached",), (),
                    SitemapEvaluation.PARTIAL_SAFETY_LIMIT, 0, 0,
                )
            )
            break
        results.append(parse_sitemap(document, limits=limits, compressed=compressed))
    logger.debug("[WP5.3] parsed sitemap collection files=%d", len(results))
    return tuple(results)


def classify_sitemap_scope(
    sitemap_urls: list[str] | tuple[str, ...],
    origin: str,
    *,
    verified_origins: set[str] | frozenset[str] = frozenset(),
) -> SitemapScopeResult:
    base_origin = _origin(origin)
    same: list[str] = []
    unknown: list[str] = []
    verified: list[str] = []
    for url in dict.fromkeys(sitemap_urls):
        target_origin = _origin(url)
        if target_origin == base_origin:
            same.append(url)
        elif target_origin in verified_origins:
            verified.append(url)
        else:
            unknown.append(url)
    warnings = tuple(
        f"cross-origin sitemap URL lacks ownership evidence: {url}" for url in unknown[:20]
    )
    logger.info("[WP5.4] sitemap scope same=%d unknown=%d verified=%d", len(same), len(unknown), len(verified))
    return SitemapScopeResult(tuple(same), tuple(unknown), tuple(verified), warnings)


def _bounded_decompress(data: bytes, maximum: int) -> bytes:
    output = bytearray()
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        while chunk := stream.read(min(1024 * 1024, maximum - len(output) + 1)):
            output.extend(chunk)
            if len(output) > maximum:
                raise ValueError("gzip sitemap exceeds uncompressed safety limit")
    return bytes(output)


def _iter_loc_values(payload: bytes, maximum: int) -> tuple[str, list[str]]:
    root: str | None = None
    values: list[str] = []
    for event, node in ET.iterparse(io.BytesIO(payload), events=("start", "end")):
        if event == "start" and root is None:
            root = _local_name(node.tag)
        if event == "end" and _local_name(node.tag) == "loc":
            value = (node.text or "").strip()
            if value:
                values.append(value)
                if len(values) > maximum:
                    raise ValueError("sitemap URL safety limit reached")
            node.clear()
    if root is None:
        raise ET.ParseError("empty XML document")
    return root, values


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"
