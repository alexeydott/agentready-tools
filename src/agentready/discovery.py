"""Bounded, deterministic discovery sources for audit planning."""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, is_dataclass
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

from .fetcher import FetchError, FetchRequest

if TYPE_CHECKING:
    from .crawler import CrawlConfig, CrawlScope
    from .egress import EgressPolicy
    from .fetcher import FetcherBoundary, FetchTransport

logger = logging.getLogger(__name__)


class DiscoverySource(Protocol):
    def discover(self, *, limit: int = 1000) -> tuple[str, ...]: ...


def discovery_plan_hash(source: DiscoverySource, *, limit: int = 1000) -> str:
    """Return a stable non-secret identity for a bounded discovery configuration."""
    _validate_limit(limit)
    if isinstance(source, SingleUrlSource):
        payload = {"type": "single", "url": source.url, "limit": limit}
    elif isinstance(source, UrlListSource):
        payload = {"type": "list", "urls": list(source.urls), "limit": limit}
    elif isinstance(source, SitemapSource):
        payload = {
            "type": "sitemap",
            "base_url": source.base_url,
            "same_origin_only": source.same_origin_only,
            "xml_hash": hashlib.sha256(source.xml.encode("utf-8")).hexdigest(),
            "limit": limit,
        }
    elif isinstance(source, RobotsSitemapSource):
        payload = {
            "type": "robots-sitemap",
            "base_url": source.base_url,
            "sitemap_urls": list(source.sitemap_urls),
            "same_origin_only": source.same_origin_only,
            "max_bytes": source.max_bytes,
            "max_depth": source.max_depth,
            "max_files": source.max_files,
            "limit": limit,
        }
    elif isinstance(source, CrawlSource):
        payload = {
            "type": "crawl",
            "scope": asdict(source.scope) if is_dataclass(source.scope) else repr(source.scope),
            "config": asdict(source.config) if is_dataclass(source.config) else repr(source.config),
            "policy": repr(source.policy),
            "limit": limit,
        }
    else:
        raise TypeError(f"unsupported discovery source: {type(source).__name__}")
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validate_limit(limit: int) -> None:
    if limit <= 0 or limit > 100_000:
        raise ValueError("discovery limit must be between 1 and 100000")


def _same_origin(url: str, origin: str) -> bool:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" == origin


@dataclass(frozen=True, slots=True)
class SingleUrlSource:
    url: str

    def discover(self, *, limit: int = 1000) -> tuple[str, ...]:
        _validate_limit(limit)
        if not self.url.strip():
            raise ValueError("discovery URL must not be empty")
        result = (self.url.strip(),)
        logger.info("discovery complete source=single limit=%d count=%d", limit, len(result))
        return result


@dataclass(frozen=True, slots=True)
class UrlListSource:
    urls: tuple[str, ...]

    def discover(self, *, limit: int = 1000) -> tuple[str, ...]:
        _validate_limit(limit)
        result: list[str] = []
        seen: set[str] = set()
        for url in self.urls:
            value = url.strip()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
            if len(result) >= limit:
                break
        discovered = tuple(result)
        logger.info("discovery complete source=list limit=%d count=%d", limit, len(discovered))
        return discovered


@dataclass(frozen=True, slots=True)
class SitemapSource:
    xml: str
    base_url: str
    same_origin_only: bool = True
    max_bytes: int = 5 * 1024 * 1024

    def discover(self, *, limit: int = 1000) -> tuple[str, ...]:
        _validate_limit(limit)
        if not self.base_url.strip():
            raise ValueError("sitemap base URL must not be empty")
        if len(self.xml.encode("utf-8")) > self.max_bytes:
            raise ValueError("sitemap exceeds configured size limit")
        if "<!doctype" in self.xml.lower() or "<!entity" in self.xml.lower():
            raise ValueError("DOCTYPE and ENTITY declarations are not allowed")
        root = ElementTree.fromstring(self.xml)
        origin = f"{urlsplit(self.base_url).scheme}://{urlsplit(self.base_url).netloc}"
        result: list[str] = []
        seen: set[str] = set()
        for node in root.iter():
            if node.tag.rsplit("}", 1)[-1] != "loc" or not node.text:
                continue
            value = urljoin(self.base_url, node.text.strip())
            if self.same_origin_only and not _same_origin(value, origin):
                continue
            if value not in seen:
                seen.add(value)
                result.append(value)
            if len(result) >= limit:
                break
        discovered = tuple(result)
        logger.info("discovery complete source=sitemap limit=%d count=%d", limit, len(discovered))
        return discovered

    @classmethod
    def from_bytes(
        cls,
        payload: bytes,
        base_url: str,
        *,
        compressed: bool = False,
        same_origin_only: bool = True,
        max_bytes: int = 5 * 1024 * 1024,
    ) -> SitemapSource:
        raw = gzip.decompress(payload) if compressed else payload
        if len(raw) > max_bytes:
            raise ValueError("sitemap exceeds configured size limit")
        return cls(raw.decode("utf-8"), base_url, same_origin_only, max_bytes)

    def discover_nested(
        self,
        documents: dict[str, str],
        *,
        limit: int = 1000,
        max_depth: int = 3,
        max_files: int = 100,
    ) -> tuple[str, ...]:
        """Resolve bounded sitemap indexes from caller-provided fetched documents."""
        _validate_limit(limit)
        if max_depth <= 0 or max_depth > 10 or max_files <= 0 or max_files > 1000:
            raise ValueError("sitemap recursion limits are outside the allowed range")
        result: list[str] = []
        visited: set[str] = set()
        pending: list[tuple[str, int]] = [(self.base_url, 0)]
        while pending and len(visited) < max_files and len(result) < limit:
            url, depth = pending.pop(0)
            if url in visited or depth > max_depth:
                continue
            visited.add(url)
            xml = documents.get(url)
            if xml is None:
                continue
            source = SitemapSource(xml, url, self.same_origin_only, self.max_bytes)
            locations = source.discover(limit=limit - len(result))
            root = ElementTree.fromstring(xml)
            is_index = root.tag.rsplit("}", 1)[-1] == "sitemapindex"
            if is_index and depth < max_depth:
                pending.extend((location, depth + 1) for location in locations)
            else:
                for location in locations:
                    if location not in result:
                        result.append(location)
        return tuple(result[:limit])

    async def discover_from_fetcher(
        self,
        fetcher: FetcherBoundary,
        *,
        limit: int = 1000,
        max_depth: int = 3,
        max_files: int = 100,
    ) -> tuple[str, ...]:
        """Fetch and resolve a bounded sitemap tree through the shared Fetcher."""
        _validate_limit(limit)
        if max_depth <= 0 or max_depth > 10 or max_files <= 0 or max_files > 1000:
            raise ValueError("sitemap recursion limits are outside the allowed range")
        pending: list[tuple[str, int]] = [(self.base_url, 0)]
        visited: set[str] = set()
        result: list[str] = []
        while pending and len(visited) < max_files and len(result) < limit:
            url, depth = pending.pop(0)
            if url in visited or depth > max_depth:
                continue
            if self.same_origin_only and not _same_origin(url, _origin(self.base_url)):
                continue
            response = await fetcher.get(
                FetchRequest(
                    url,
                    purpose="discovery-sitemap",
                    cache_mode="run-deduplicate",
                )
            )
            visited.add(url)
            if response.status_code < 200 or response.status_code >= 300:
                raise ValueError(f"sitemap fetch failed with HTTP {response.status_code}")
            compressed = "gzip" in response.headers.get("content-encoding", "").lower() or url.lower().endswith(".gz")
            source = SitemapSource.from_bytes(
                response.body,
                url,
                compressed=compressed,
                same_origin_only=self.same_origin_only,
                max_bytes=self.max_bytes,
            )
            root = ElementTree.fromstring(source.xml)
            locations = source.discover(limit=limit - len(result))
            if root.tag.rsplit("}", 1)[-1] == "sitemapindex" and depth < max_depth:
                pending.extend((location, depth + 1) for location in locations)
            else:
                for location in locations:
                    if location not in result:
                        result.append(location)
        logger.info(
            "discovery complete source=sitemap-fetch limit=%d count=%d files=%d",
            limit,
            len(result),
            len(visited),
        )
        return tuple(result[:limit])


@dataclass(frozen=True, slots=True)
class RobotsSitemapSource:
    """Discover bounded sitemap trees named by robots.txt and explicit URLs."""

    base_url: str
    sitemap_urls: tuple[str, ...] = ()
    same_origin_only: bool = True
    max_bytes: int = 5 * 1024 * 1024
    max_depth: int = 3
    max_files: int = 100

    async def discover_from_fetcher(
        self,
        fetcher: FetcherBoundary,
        *,
        limit: int = 1000,
    ) -> tuple[str, ...]:
        collected = await self.collect_from_fetcher(fetcher, limit=limit)
        if collected.robots.fetch_state not in {"available", "supplied"}:
            robots = collected.robots
            detail = f"HTTP {robots.status_code}" if robots.status_code is not None else robots.error_kind or robots.fetch_state
            raise ValueError(f"robots fetch failed with {detail}")
        errors = [document for document in collected.sitemap_documents if document.fetch_state not in {"available", "supplied"}]
        if errors:
            first = errors[0]
            detail = f"HTTP {first.status_code}" if first.status_code is not None else first.error_kind or first.fetch_state
            raise ValueError(f"sitemap fetch failed with {detail}")
        return collected.urls

    async def collect_from_fetcher(
        self,
        fetcher: FetcherBoundary,
        *,
        limit: int = 1000,
    ) -> RobotsSitemapDiscoveryResult:
        _validate_limit(limit)
        if not self.base_url.strip():
            raise ValueError("robots base URL must not be empty")
        if self.max_depth <= 0 or self.max_depth > 10 or self.max_files <= 0 or self.max_files > 1000:
            raise ValueError("robots sitemap recursion limits are outside the allowed range")
        origin = _origin(self.base_url)
        robots_url = urljoin(self.base_url, "/robots.txt")
        try:
            response = await fetcher.get(
                FetchRequest(
                    robots_url,
                    purpose="discovery-robots",
                    cache_mode="run-deduplicate",
                )
            )
            robots_observation = RobotsDocumentObservation(
                source_url=robots_url,
                final_url=getattr(response, "url", robots_url),
                status_code=response.status_code,
                fetch_state=_fetch_state(response.status_code),
                body=response.body,
            )
        except FetchError as exc:
            robots_observation = RobotsDocumentObservation(
                source_url=robots_url,
                fetch_state="unreachable",
                error_kind=exc.kind.value,
            )
            return RobotsSitemapDiscoveryResult(robots_observation, (), ())
        if response.status_code >= 400 and response.status_code != 404:
            robots_observation = RobotsDocumentObservation(
                source_url=robots_url,
                final_url=getattr(response, "url", robots_url),
                status_code=response.status_code,
                fetch_state=_fetch_state(response.status_code),
                body=None,
            )
            logger.info(
                "robots fetch unavailable source=robots-sitemap status=%s state=%s",
                response.status_code,
                robots_observation.fetch_state,
            )
            return RobotsSitemapDiscoveryResult(robots_observation, (), ())
        discovered_roots = [
            urljoin(robots_url, line.split(":", 1)[1].strip())
            for line in response.body.decode("utf-8", errors="replace").splitlines()
            if line.split(":", 1)[0].strip().lower() == "sitemap" and ":" in line
        ]
        discovered_roots.extend(urljoin(self.base_url, value) for value in self.sitemap_urls)
        roots = tuple(
            url for url in dict.fromkeys(discovered_roots)
            if not self.same_origin_only or _same_origin(url, origin)
        )[: self.max_files]
        result: list[str] = []
        documents: list[SitemapDocumentObservation] = []
        for root in roots:
            if len(result) >= limit:
                break
            urls, observed = await _collect_sitemap_tree(
                fetcher,
                root,
                origin=origin,
                same_origin_only=self.same_origin_only,
                max_bytes=self.max_bytes,
                limit=limit - len(result),
                max_depth=self.max_depth,
                max_files=self.max_files,
            )
            documents.extend(observed)
            for url in urls:
                if url not in result:
                    result.append(url)
        logger.info(
            "discovery complete source=robots-sitemap limit=%d count=%d roots=%d",
            limit,
            len(result),
            len(roots),
        )
        return RobotsSitemapDiscoveryResult(robots_observation, tuple(documents), tuple(result[:limit]))


@dataclass(frozen=True, slots=True)
class RobotsDocumentObservation:
    source_url: str
    final_url: str | None = None
    status_code: int | None = None
    fetch_state: str = "not_fetched"
    body: bytes | None = None
    error_kind: str | None = None


@dataclass(frozen=True, slots=True)
class SitemapDocumentObservation:
    source_url: str
    source_kind: str
    fetch_state: str
    body: bytes | None = None
    final_url: str | None = None
    status_code: int | None = None
    error_kind: str | None = None
    compressed: bool = False


@dataclass(frozen=True, slots=True)
class RobotsSitemapDiscoveryResult:
    robots: RobotsDocumentObservation
    sitemap_documents: tuple[SitemapDocumentObservation, ...]
    urls: tuple[str, ...]


async def _collect_sitemap_tree(
    fetcher: FetcherBoundary,
    root_url: str,
    *,
    origin: str,
    same_origin_only: bool,
    max_bytes: int,
    limit: int,
    max_depth: int,
    max_files: int,
) -> tuple[tuple[str, ...], tuple[SitemapDocumentObservation, ...]]:
    pending: list[tuple[str, int, str]] = [(root_url, 0, "robots_declared")]
    visited: set[str] = set()
    result: list[str] = []
    documents: list[SitemapDocumentObservation] = []
    while pending and len(visited) < max_files and len(result) < limit:
        url, depth, source_kind = pending.pop(0)
        if url in visited or depth > max_depth:
            continue
        if same_origin_only and not _same_origin(url, origin):
            continue
        try:
            response = await fetcher.get(FetchRequest(url, purpose="discovery-sitemap", cache_mode="run-deduplicate"))
        except FetchError as exc:
            visited.add(url)
            documents.append(SitemapDocumentObservation(url, source_kind, "unreachable", error_kind=exc.kind.value))
            continue
        visited.add(url)
        fetch_state = _fetch_state(response.status_code)
        compressed = "gzip" in response.headers.get("content-encoding", "").lower() or url.lower().endswith(".gz")
        documents.append(
            SitemapDocumentObservation(
                url,
                source_kind,
                fetch_state,
                body=response.body if fetch_state == "available" else None,
                final_url=getattr(response, "url", url),
                status_code=response.status_code,
                compressed=compressed if fetch_state == "available" else False,
            )
        )
        if fetch_state != "available":
            continue
        source = SitemapSource.from_bytes(
            response.body,
            url,
            compressed=compressed,
            same_origin_only=same_origin_only,
            max_bytes=max_bytes,
        )
        root = ElementTree.fromstring(source.xml)
        locations = source.discover(limit=limit - len(result))
        if root.tag.rsplit("}", 1)[-1] == "sitemapindex" and depth < max_depth:
            pending.extend((location, depth + 1, "sitemap_index") for location in locations)
        else:
            for location in locations:
                if location not in result:
                    result.append(location)
    return tuple(result[:limit]), tuple(documents)


def _fetch_state(status_code: int | None) -> str:
    if status_code is None or status_code >= 500 or status_code == 429:
        return "unreachable"
    if status_code == 404:
        return "not_found"
    if 400 <= status_code < 500:
        return "error"
    return "available"


@dataclass(frozen=True, slots=True)
class CrawlSource:
    """Discover URLs through the canonical bounded crawler."""

    scope: CrawlScope
    config: CrawlConfig
    policy: EgressPolicy
    transport: FetchTransport | None = None

    def discover(self, *, limit: int = 1000) -> tuple[str, ...]:
        _validate_limit(limit)
        from .crawler import AsyncCrawler

        result = asyncio.run(
            AsyncCrawler(
                self.scope,
                config=self.config,
                policy=self.policy,
                transport=self.transport,
            ).crawl()
        )
        discovered = tuple(page.url for page in result.pages[:limit])
        logger.info("discovery complete source=crawl limit=%d count=%d", limit, len(discovered))
        return discovered


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
