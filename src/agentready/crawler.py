"""Deterministic bounded site crawler with explicit scope and coverage semantics."""
from __future__ import annotations

import asyncio
import fnmatch
import heapq
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx

from .audit_core.store import PageRecord, SiteStore
from .egress import EgressPolicy
from .fetcher import FetchError, FetchRequest, Fetcher
from .page_parser import ParsedPage, parse_page

logger = logging.getLogger(__name__)


class CrawlItemState(StrEnum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    FETCHING = "fetching"
    FETCHED = "fetched"
    PARSED = "parsed"
    SKIPPED_POLICY = "skipped_policy"
    FAILED = "failed"


class CrawlClassification(StrEnum):
    COMPLETE_WITHIN_SCOPE = "complete_within_scope"
    PARTIAL_LIMIT = "partial_limit"
    PARTIAL_ERROR = "partial_error"


@dataclass(frozen=True, slots=True)
class CrawlItem:
    url: str
    depth: int
    discovered_from: str | None = None
    discovery_method: str = "seed"
    priority: int = 100


@dataclass(frozen=True, slots=True)
class CrawlScope:
    seed_origins: tuple[str, ...]
    allowed_origins: tuple[str, ...] = ()
    include_rules: tuple[str, ...] = ()
    exclude_rules: tuple[str, ...] = ()

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in (self.allowed_origins or self.seed_origins):
            return False
        if self.include_rules and not any(fnmatch.fnmatch(url, rule) for rule in self.include_rules):
            return False
        return not any(fnmatch.fnmatch(url, rule) for rule in self.exclude_rules)


@dataclass(frozen=True, slots=True)
class CrawlCoverage:
    discovered: int
    queued_remaining: int
    fetched: int
    parsed_html: int
    skipped_policy: int
    failed: int
    max_pages_hit: bool
    max_depth_hit: bool
    deadline_hit: bool
    frontier_exhausted: bool

    @property
    def classification(self) -> CrawlClassification:
        return (
            CrawlClassification.COMPLETE_WITHIN_SCOPE
            if self.frontier_exhausted and not self.failed
            else CrawlClassification.PARTIAL_ERROR
            if self.failed
            else CrawlClassification.PARTIAL_LIMIT
        )


@dataclass(frozen=True, slots=True)
class CrawledPage:
    url: str
    depth: int
    status_code: int | None
    parsed: ParsedPage | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CrawlResult:
    pages: tuple[CrawledPage, ...]
    coverage: CrawlCoverage


class Frontier:
    """Priority frontier with deterministic URL de-duplication and state tracking."""

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, CrawlItem]] = []
        self._sequence = 0
        self._items: dict[str, CrawlItemState] = {}

    def add(self, item: CrawlItem) -> bool:
        if item.url in self._items:
            return False
        self._items[item.url] = CrawlItemState.QUEUED
        heapq.heappush(self._heap, (item.priority, self._sequence, item))
        self._sequence += 1
        return True

    def pop(self) -> CrawlItem | None:
        if not self._heap:
            return None
        _, _, item = heapq.heappop(self._heap)
        self._items[item.url] = CrawlItemState.FETCHING
        return item

    def set_state(self, url: str, state: CrawlItemState) -> None:
        if url in self._items:
            self._items[url] = state

    def state(self, url: str) -> CrawlItemState | None:
        return self._items.get(url)

    @property
    def queued(self) -> int:
        return sum(state == CrawlItemState.QUEUED for state in self._items.values())

    @property
    def discovered(self) -> int:
        return len(self._items)


@dataclass(frozen=True, slots=True)
class CrawlConfig:
    max_pages: int = 2000
    max_depth: int = 12
    concurrency: int = 8
    per_origin_concurrency: int = 4
    min_request_interval_ms: int = 100
    timeout: float = 30.0
    max_duration: float = 1800.0

    def __post_init__(self) -> None:
        if self.max_pages <= 0 or self.max_depth < 0 or self.concurrency <= 0 or self.per_origin_concurrency <= 0:
            raise ValueError("crawl limits must be positive, except max_depth")
        if self.min_request_interval_ms < 0 or self.timeout <= 0 or self.max_duration <= 0:
            raise ValueError("crawl timing limits must be positive")


class AsyncCrawler:
    def __init__(
        self,
        scope: CrawlScope,
        *,
        config: CrawlConfig | None = None,
        policy: EgressPolicy | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        store: SiteStore | None = None,
    ) -> None:
        self.scope = scope
        self.config = config or CrawlConfig()
        self.policy = policy or EgressPolicy(
            max_response_bytes=5 * 1024 * 1024,
            allowed_origins=frozenset(scope.allowed_origins or scope.seed_origins),
        )
        self.transport = transport
        self.store = store

    async def crawl(self) -> CrawlResult:
        started = time.monotonic()
        deadline = started + self.config.max_duration
        frontier = Frontier()
        for seed in sorted({_normalize(url) for url in self.scope.seed_origins}):
            frontier.add(CrawlItem(seed, 0))
        pages: dict[str, CrawledPage] = {}
        fetched = parsed_html = skipped_policy = failed = 0
        max_depth_hit = False
        deadline_hit = False
        queue: asyncio.Queue[CrawlItem | None] = asyncio.Queue()
        queue_lock = asyncio.Lock()
        origin_semaphores: dict[str, asyncio.Semaphore] = {}
        origin_last_request: dict[str, float] = {}
        result_lock = asyncio.Lock()
        reserved_fetches = 0

        async def refill() -> None:
            async with queue_lock:
                while queue.qsize() < self.config.concurrency and frontier.queued:
                    item = frontier.pop()
                    if item is not None:
                        await queue.put(item)

        async def worker(fetcher: Fetcher) -> None:
            nonlocal fetched, parsed_html, skipped_policy, failed, max_depth_hit, deadline_hit, reserved_fetches
            while True:
                item = await queue.get()
                if item is None:
                    queue.task_done()
                    return
                try:
                    async with result_lock:
                        if reserved_fetches >= self.config.max_pages:
                            frontier.set_state(item.url, CrawlItemState.SKIPPED_POLICY)
                            continue
                        reserved_fetches += 1
                    if time.monotonic() >= deadline:
                        deadline_hit = True
                        frontier.set_state(item.url, CrawlItemState.FAILED)
                        continue
                    if not self.scope.allows(item.url):
                        skipped_policy += 1
                        frontier.set_state(item.url, CrawlItemState.SKIPPED_POLICY)
                        continue
                    origin = f"{urlsplit(item.url).scheme}://{urlsplit(item.url).netloc}"
                    semaphore = origin_semaphores.setdefault(origin, asyncio.Semaphore(self.config.per_origin_concurrency))
                    async with semaphore:
                        previous = origin_last_request.get(origin)
                        if previous is not None:
                            await asyncio.sleep(max(0, self.config.min_request_interval_ms / 1000 - (time.monotonic() - previous)))
                        origin_last_request[origin] = time.monotonic()
                        try:
                            response = await fetcher.get(FetchRequest(item.url, purpose="crawl"))
                        except FetchError as exc:
                            failed += 1
                            frontier.set_state(item.url, CrawlItemState.FAILED)
                            pages[item.url] = CrawledPage(item.url, item.depth, None, None, str(exc))
                            continue
                    fetched += 1
                    parsed: ParsedPage | None = None
                    if response.status_code == 200 and response.headers.get("content-type", "").split(";", 1)[0] in {"text/html", "application/xhtml+xml"}:
                        parsed = parse_page(response.body)
                        parsed_html += 1
                        frontier.set_state(item.url, CrawlItemState.PARSED)
                        for link in parsed.links:
                            child = _normalize(urljoin(response.url, link))
                            if item.depth + 1 > self.config.max_depth:
                                max_depth_hit = True
                            elif self.scope.allows(child):
                                frontier.add(CrawlItem(child, item.depth + 1, item.url, "html-link"))
                    else:
                        frontier.set_state(item.url, CrawlItemState.FETCHED)
                    pages[item.url] = CrawledPage(response.url, item.depth, response.status_code, parsed)
                    if self.store is not None:
                        self.store.put_page(PageRecord("crawl", item.url, item.url, response.url, item.depth, response.status_code, response.headers.get("content-type")))
                finally:
                    queue.task_done()
                    await refill()

        async with Fetcher(policy=self.policy, timeout=self.config.timeout, transport=self.transport) as fetcher:
            await refill()
            workers = [asyncio.create_task(worker(fetcher)) for _ in range(self.config.concurrency)]
            try:
                while not queue.empty() or frontier.queued:
                    if len(pages) >= self.config.max_pages:
                        break
                    await asyncio.sleep(0)
                    await refill()
                for _ in workers:
                    await queue.put(None)
                await queue.join()
                for task in workers:
                    await task
            finally:
                for task in workers:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
        coverage = CrawlCoverage(
            discovered=frontier.discovered,
            queued_remaining=frontier.queued,
            fetched=fetched,
            parsed_html=parsed_html,
            skipped_policy=skipped_policy,
            failed=failed,
            max_pages_hit=len(pages) >= self.config.max_pages,
            max_depth_hit=max_depth_hit,
            deadline_hit=deadline_hit,
            frontier_exhausted=frontier.queued == 0 and not deadline_hit,
        )
        ordered = tuple(pages[url] for url in sorted(pages))
        logger.info("[WP4.1] crawl complete discovered=%d fetched=%d failed=%d", coverage.discovered, fetched, failed)
        return CrawlResult(ordered, coverage)


def _normalize(url: str) -> str:
    return urldefrag(url.strip())[0].rstrip("/") or url
