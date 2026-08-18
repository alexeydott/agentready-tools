"""Deterministic bounded site crawler with explicit scope and coverage semantics."""
from __future__ import annotations

import asyncio
import fnmatch
import heapq
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from urllib.parse import urldefrag, urljoin, urlsplit

from .audit_core.run_context import (
    AuditRunContext,
    RunCoordinator,
    RunSnapshot,
    RunState,
)
from .audit_core.store import (
    PageRecord,
    RedirectFact,
    RunRecord,
    RunUrlRecord,
    RunUrlState,
    SiteStore,
)
from .audit_core.urls import UrlIdentity
from .browser_pool import BrowserPool, BrowserPoolBoundary, BrowserPoolFactory
from .egress import EgressPolicy
from .egress import PassivePublicContext, TrustedLocalCredentialContext
from .fetcher import (
    Fetcher,
    FetcherBoundary,
    FetcherFactory,
    FetchError,
    FetchErrorKind,
    FetchRequest,
    FetchResult,
    FetchTransport,
)
from .page_parser import ParsedPage, Representation, RepresentationSource, parse_page

logger = logging.getLogger(__name__)


def _locally_indexable(status_code: int, content_type: str, meta_robots: tuple[str, ...]) -> bool | None:
    """Return the observable local indexability signal for an HTML response."""
    if status_code != 200 or content_type not in {"text/html", "application/xhtml+xml"}:
        return None
    directives = " ".join(meta_robots).lower().replace(",", " ").split()
    return "noindex" not in directives


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
class CrawlSeeds:
    urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScopePolicy:
    allowed_origins: tuple[str, ...]
    include_rules: tuple[str, ...] = ()
    exclude_rules: tuple[str, ...] = ()
    allow_external_links: bool = False

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.allowed_origins:
            return False
        if self.include_rules and not any(fnmatch.fnmatch(url, rule) for rule in self.include_rules):
            return False
        return not any(fnmatch.fnmatch(url, rule) for rule in self.exclude_rules)

    def reason(self, url: str) -> str:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.allowed_origins:
            return "origin"
        if self.include_rules and not any(fnmatch.fnmatch(url, rule) for rule in self.include_rules):
            return "include"
        if any(fnmatch.fnmatch(url, rule) for rule in self.exclude_rules):
            return "exclude"
        return "allowed"


@dataclass(frozen=True, slots=True)
class CrawlScope:
    seed_urls: tuple[str, ...]
    allowed_origins: tuple[str, ...] = ()
    include_rules: tuple[str, ...] = ()
    exclude_rules: tuple[str, ...] = ()
    follow_links: bool = True

    @classmethod
    def from_parts(cls, seeds: CrawlSeeds, policy: ScopePolicy) -> CrawlScope:
        return cls(seeds.urls, policy.allowed_origins, policy.include_rules, policy.exclude_rules)

    @property
    def seed_origins(self) -> tuple[str, ...]:
        """Compatibility alias for callers that used the pre-v2 name."""
        return self.seed_urls

    @property
    def seeds(self) -> CrawlSeeds:
        return CrawlSeeds(self.seed_urls)

    @property
    def policy(self) -> ScopePolicy:
        return ScopePolicy(
            self.allowed_origins or tuple(_origin(seed) for seed in self.seed_urls),
            self.include_rules,
            self.exclude_rules,
        )

    def allows(self, url: str) -> bool:
        return self.policy.allows(url)


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
            CrawlClassification.PARTIAL_ERROR
            if self.failed
            else CrawlClassification.PARTIAL_LIMIT
            if self.max_pages_hit or self.max_depth_hit or self.deadline_hit or not self.frontier_exhausted
            else CrawlClassification.COMPLETE_WITHIN_SCOPE
        )


@dataclass(frozen=True, slots=True)
class CrawledPage:
    url: str
    depth: int
    status_code: int | None
    parsed: ParsedPage | None
    error: str | None = None
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None
    requested_url: str | None = None


@dataclass(frozen=True, slots=True)
class CrawlResult:
    pages: tuple[CrawledPage, ...]
    coverage: CrawlCoverage
    run: RunSnapshot | None = None


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
        transport: FetchTransport | None = None,
        store: SiteStore | None = None,
        run_context: AuditRunContext | None = None,
        render: bool = False,
        verify: bool = True,
        fetcher_factory: FetcherFactory | None = None,
        browser_pool_factory: BrowserPoolFactory | None = None,
        progress_callback: Callable[[dict[str, int | str]], None] | None = None,
        request_headers: dict[str, str] | None = None,
        security_context: PassivePublicContext | TrustedLocalCredentialContext | None = None,
    ) -> None:
        self.scope = scope
        self.config = config or CrawlConfig()
        self.policy = policy or EgressPolicy(
            max_response_bytes=5 * 1024 * 1024,
            allowed_origins=frozenset(scope.policy.allowed_origins),
        )
        self.transport = transport
        self.store = store
        self.run_context = run_context
        self.render = render
        self.verify = verify
        self.fetcher_factory = fetcher_factory or Fetcher
        self.browser_pool_factory = browser_pool_factory or BrowserPool
        self.progress_callback = progress_callback
        self.request_headers = dict(request_headers or {})
        self.security_context = security_context
        if self.render and self.request_headers:
            raise ValueError("trusted credentials cannot be used with rendered browser audits")

    async def crawl(self) -> CrawlResult:
        started = time.monotonic()
        run_id = self.run_context.run_id if self.run_context is not None else "crawl"
        coordinator = RunCoordinator(self.run_context) if self.run_context is not None else None
        if coordinator is not None:
            coordinator.transition(RunState.RUNNING)
        if self.store is not None:
            self.store.begin_run(
                RunRecord(
                    run_id,
                    self.run_context.config_hash if self.run_context is not None else "crawler",
                    self.run_context.tool_version if self.run_context is not None else "crawler",
                    self.run_context.rule_catalog_version if self.run_context is not None else "crawler",
                )
            )

        def persist_run_state(state: RunState, *, finished_at: str | None = None) -> None:
            if self.store is not None:
                self.store.update_run_state(run_id, state.value, finished_at=finished_at)

        def record_url(url: str, state: RunUrlState, depth: int, *, error_kind: str | None = None) -> None:
            if self.store is not None:
                self.store.put_run_url(RunUrlRecord(run_id, url, state, depth=depth, error_kind=error_kind))

        deadline = started + self.config.max_duration
        frontier = Frontier()
        if self.progress_callback:
            self.progress_callback({"phase": "crawl", "fetched": 0, "discovered": 0})
        for seed in sorted({_normalize(url) for url in self.scope.seeds.urls}):
            if frontier.add(CrawlItem(seed, 0)):
                record_url(seed, RunUrlState.QUEUED, 0)
        pages: dict[str, CrawledPage] = {}
        fetched = parsed_html = skipped_policy = failed = 0
        completed_items = 0
        max_depth_hit = False
        deadline_hit = False
        queue: asyncio.Queue[CrawlItem | None] = asyncio.Queue()
        queue_lock = asyncio.Lock()
        origin_semaphores: dict[str, asyncio.Semaphore] = {}
        origin_last_request: dict[str, float] = {}
        result_lock = asyncio.Lock()
        reserved_fetches = 0
        active_items = 0
        stop_scheduling = asyncio.Event()

        async def refill() -> None:
            if stop_scheduling.is_set():
                return
            async with queue_lock:
                if stop_scheduling.is_set():
                    return
                while queue.qsize() < self.config.concurrency and frontier.queued:
                    item = frontier.pop()
                    if item is not None:
                        await queue.put(item)

        async def worker(fetcher: FetcherBoundary) -> None:
            nonlocal fetched, parsed_html, skipped_policy, failed, completed_items
            nonlocal max_depth_hit, deadline_hit, reserved_fetches, active_items
            while True:
                item = await queue.get()
                if item is None:
                    queue.task_done()
                    return
                async with result_lock:
                    active_items += 1
                try:
                    record_url(item.url, RunUrlState.FETCHING, item.depth)
                    async with result_lock:
                        if reserved_fetches >= self.config.max_pages:
                            frontier.set_state(item.url, CrawlItemState.SKIPPED_POLICY)
                            skipped_policy += 1
                            record_url(item.url, RunUrlState.SKIPPED, item.depth)
                            continue
                        reserved_fetches += 1
                        if self.progress_callback:
                            self.progress_callback({"phase": "crawl", "fetched": fetched, "discovered": frontier.discovered, "queued": frontier.queued})
                    if time.monotonic() >= deadline:
                        deadline_hit = True
                        frontier.set_state(item.url, CrawlItemState.FAILED)
                        record_url(item.url, RunUrlState.FAILED, item.depth, error_kind="deadline")
                        continue
                    if not self.scope.allows(item.url):
                        logger.debug(
                            "crawl scope decision run_id=%s url=%s reason=%s",
                            run_id,
                            _safe_log_url(item.url),
                            self.scope.policy.reason(item.url),
                        )
                        logger.warning(
                            "crawl URL blocked by scope run_id=%s reason=%s",
                            run_id,
                            self.scope.policy.reason(item.url),
                        )
                        skipped_policy += 1
                        frontier.set_state(item.url, CrawlItemState.SKIPPED_POLICY)
                        record_url(item.url, RunUrlState.SKIPPED, item.depth, error_kind="scope")
                        continue
                    origin = f"{urlsplit(item.url).scheme}://{urlsplit(item.url).netloc}"
                    semaphore = origin_semaphores.setdefault(origin, asyncio.Semaphore(self.config.per_origin_concurrency))
                    async with semaphore:
                        previous = origin_last_request.get(origin)
                        if previous is not None:
                            await asyncio.sleep(max(0, self.config.min_request_interval_ms / 1000 - (time.monotonic() - previous)))
                        origin_last_request[origin] = time.monotonic()
                        try:
                            if self.render:
                                response_started = time.monotonic()
                                try:
                                    async with browser_pool.page() as page:  # type: ignore[union-attr]
                                        navigation = await browser_pool.goto(  # type: ignore[union-attr]
                                            page,
                                            item.url,
                                            wait_until="domcontentloaded",
                                        )
                                        response = FetchResult(
                                            url=page.url or item.url,
                                            status_code=getattr(navigation, "status", None) or 200,
                                            headers={"content-type": "text/html"},
                                            body=(await page.content()).encode("utf-8"),
                                            redirects=(),
                                            elapsed_ms=int((time.monotonic() - response_started) * 1000),
                                        )
                                except Exception as exc:
                                    raise FetchError(str(exc), kind=FetchErrorKind.PROTOCOL) from exc
                            else:
                                response = await fetcher.get(
                                    FetchRequest(
                                        item.url,
                                        purpose="crawl",
                                        run_id=run_id,
                                        headers=self.request_headers,
                                        security_context=self.security_context,
                                    )
                                )
                        except FetchError as exc:
                            failed += 1
                            frontier.set_state(item.url, CrawlItemState.FAILED)
                            record_url(item.url, RunUrlState.FAILED, item.depth, error_kind=exc.kind.value)
                            pages[item.url] = CrawledPage(item.url, item.depth, None, None, str(exc))
                            continue
                    if time.monotonic() >= deadline:
                        deadline_hit = True
                    fetched += 1
                    if self.store is not None:
                        logger.debug(
                            "crawl redirect projection run_id=%s source=%s hops=%d",
                            run_id,
                            _safe_log_url(item.url),
                            len(response.redirect_records),
                        )
                        for hop in response.redirect_records:
                            self.store.put_redirect(
                                RedirectFact(
                                    run_id,
                                    hop.from_url,
                                    hop.to_url,
                                    hop.status_code,
                                    hop.location_raw,
                                )
                            )
                    parsed: ParsedPage | None = None
                    representation: Representation | None = None
                    if response.status_code == 200 and response.headers.get("content-type", "").split(";", 1)[0] in {"text/html", "application/xhtml+xml"}:
                        representation = Representation.from_body(
                            response.body,
                            run_id=run_id,
                            url_key=item.url,
                            source=(
                                RepresentationSource.RENDERED_DOM
                                if self.render
                                else RepresentationSource.STATIC_HTML
                            ),
                            content_type=response.headers.get("content-type", "text/html"),
                        )
                        parsed = parse_page(response.body, representation=representation)
                        parsed_html += 1
                        frontier.set_state(item.url, CrawlItemState.PARSED)
                        occurrences = parsed.facts.links if parsed.facts is not None else ()
                        for occurrence in occurrences:
                            link = occurrence.raw_href
                            try:
                                child = _normalize(urljoin(response.url, link))
                            except ValueError:
                                logger.warning(
                                    "crawl link ignored because it is not an absolute HTTP(S) URL "
                                    "run_id=%s source=%s href=%r",
                                    run_id,
                                    _safe_log_url(item.url),
                                    link[:200],
                                )
                                continue
                            if self.store is not None:
                                self.store.put_link(
                                    run_id,
                                    item.url,
                                    link,
                                    target_key=child,
                                    resolved_url=child,
                                    discovery_method="html-link",
                                    ordinal=occurrence.ordinal,
                                    representation_id=occurrence.source_representation_id,
                                    rel=occurrence.rel,
                                    element=occurrence.element,
                                    dom_path=occurrence.dom_path,
                                    anchor_text=occurrence.anchor_text,
                                )
                            if not self.scope.follow_links:
                                continue
                            if item.depth + 1 > self.config.max_depth:
                                max_depth_hit = True
                            elif self.scope.allows(child):
                                if frontier.add(CrawlItem(child, item.depth + 1, item.url, "html-link")):
                                    record_url(child, RunUrlState.QUEUED, item.depth + 1)
                            else:
                                logger.debug(
                                    "crawl scope decision run_id=%s url=%s reason=%s",
                                    run_id,
                                    _safe_log_url(child),
                                    self.scope.policy.reason(child),
                                )
                        if self.store is not None:
                            resources = parsed.facts.resources if parsed.facts is not None else ()
                            for resource in resources:
                                self.store.put_resource(
                                    run_id,
                                    item.url,
                                    resource.url,
                                    resource.resource_type,
                                    ordinal=resource.ordinal,
                                    resolved_url=_normalize_resource(urljoin(response.url, resource.url)),
                                    representation_id=resource.source_representation_id,
                                    element=resource.element,
                                    dom_path=resource.dom_path,
                                )
                    else:
                        frontier.set_state(item.url, CrawlItemState.FETCHED)
                    record_url(
                        item.url,
                        RunUrlState.PARSED if parsed is not None else RunUrlState.FETCHED,
                        item.depth,
                    )
                    pages[item.url] = CrawledPage(
                        response.url,
                        item.depth,
                        response.status_code,
                        parsed,
                        headers=tuple(sorted(response.headers.items())),
                        body=response.body,
                        requested_url=item.url,
                    )
                    completed_items += 1
                    if self.store is not None:
                        facts = parsed.facts if parsed is not None else None
                        canonical = (
                            urljoin(response.url, facts.canonicals[0])
                            if facts is not None and facts.canonicals
                            else None
                        )
                        self.store.put_page(
                            PageRecord(
                                run_id,
                                item.url,
                                item.url,
                                response.url,
                                item.depth,
                                response.status_code,
                                response.headers.get("content-type"),
                                title=parsed.title if parsed is not None else None,
                                canonical=canonical,
                                locally_indexable=(
                                    _locally_indexable(
                                        response.status_code,
                                        response.headers.get("content-type", "").split(";", 1)[0],
                                        facts.meta_robots if facts is not None else (),
                                    )
                                    if parsed is not None
                                    else None
                                ),
                                content_hash=representation.body_hash if representation is not None else None,
                                content=parsed.text if parsed is not None else None,
                            )
                        )
                        logger.debug(
                            "crawl page projection run_id=%s url=%s parsed=%s links=%d resources=%d",
                            run_id,
                            _safe_log_url(item.url),
                            parsed is not None,
                            len(facts.links) if facts is not None else 0,
                            len(facts.resources) if facts is not None else 0,
                        )
                except Exception as exc:  # noqa: BLE001 - isolate one page from the bounded crawl
                    # Fetch failures are handled at the transport boundary above, but
                    # parsing/storage projections can fail after a response was fetched.
                    # Never let one malformed page kill a worker and strand the frontier.
                    failed += 1
                    frontier.set_state(item.url, CrawlItemState.FAILED)
                    record_url(item.url, RunUrlState.FAILED, item.depth, error_kind=type(exc).__name__)
                    pages[item.url] = CrawledPage(item.url, item.depth, None, None, str(exc))
                    logger.exception(
                        "[FIX:crawler-worker] page isolated run_id=%s url=%s error_type=%s",
                        run_id,
                        _safe_log_url(item.url),
                        type(exc).__name__,
                    )
                finally:
                    queue.task_done()
                    async with result_lock:
                        active_items -= 1
                    await refill()

        browser_pool = self.browser_pool_factory(self.policy) if self.render else None
        try:
            if browser_pool is not None:
                await browser_pool.start()
            async with self.fetcher_factory(
                policy=self.policy,
                timeout=self.config.timeout,
                verify=self.verify,
                transport=self.transport,
            ) as fetcher:
                await refill()
                workers = [asyncio.create_task(worker(fetcher)) for _ in range(self.config.concurrency)]
                try:
                    while True:
                        async with result_lock:
                            active = active_items
                        logger.debug(
                            "[WP4.2] scheduler queued=%d active=%d completed=%d skipped=%d failed=%d",
                            frontier.queued,
                            active,
                            completed_items,
                            skipped_policy,
                            failed,
                        )
                        if len(pages) >= self.config.max_pages:
                            break
                        if queue.empty() and frontier.queued == 0 and active == 0:
                            break
                        await asyncio.sleep(0)
                        await refill()
                    async with queue_lock:
                        stop_scheduling.set()
                        while not queue.empty():
                            queued_item = queue.get_nowait()
                            if queued_item is not None:
                                frontier.set_state(queued_item.url, CrawlItemState.SKIPPED_POLICY)
                                skipped_policy += 1
                                record_url(
                                    queued_item.url,
                                    RunUrlState.SKIPPED,
                                    queued_item.depth,
                                    error_kind="max-pages",
                                )
                            queue.task_done()
                    for _ in workers:
                        await queue.put(None)
                    for task in workers:
                        await task
                finally:
                    for task in workers:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*workers, return_exceptions=True)
        except asyncio.CancelledError:
            if coordinator is not None and coordinator.state is RunState.RUNNING:
                coordinator.transition(RunState.INTERRUPTED, error_kind="cancelled")
                persist_run_state(RunState.INTERRUPTED)
            logger.info("audit crawl interrupted run_id=%s", run_id)
            raise
        except Exception as exc:
            if coordinator is not None and coordinator.state is RunState.RUNNING:
                coordinator.transition(RunState.FAILED, error_kind=type(exc).__name__)
                persist_run_state(RunState.FAILED, finished_at=datetime.now(UTC).isoformat())
            logger.error(
                "audit crawl failed run_id=%s error_kind=%s",
                run_id,
                type(exc).__name__,
            )
            raise
        finally:
            if browser_pool is not None:
                await _close_browser_pool(browser_pool)
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
        if self.progress_callback:
            self.progress_callback({"phase": "complete", "fetched": coverage.fetched, "discovered": coverage.discovered, "queued": coverage.queued_remaining})
        logger.info(
            "[WP4.1] crawl complete discovered=%d fetched=%d completed=%d skipped=%d failed=%d",
            coverage.discovered,
            fetched,
            completed_items,
            skipped_policy,
            failed,
        )
        if coverage.classification is not CrawlClassification.COMPLETE_WITHIN_SCOPE:
            logger.warning(
                "[WP4.3] crawl partial classification=%s queued_remaining=%d deadline_hit=%s",
                coverage.classification,
                coverage.queued_remaining,
                coverage.deadline_hit,
            )
        if coordinator is not None:
            terminal_state = (
                RunState.COMPLETED
                if coverage.classification is CrawlClassification.COMPLETE_WITHIN_SCOPE
                else RunState.PARTIAL
            )
            coordinator.transition(terminal_state, error_kind="crawl-partial" if coverage.failed else None)
            persist_run_state(terminal_state, finished_at=coordinator.completed_at)
        return CrawlResult(ordered, coverage, coordinator.snapshot() if coordinator is not None else None)


def _normalize(url: str) -> str:
    value = urldefrag(url.strip())[0]
    return UrlIdentity.parse(value).normalized()


def _normalize_resource(url: str) -> str | None:
    """Normalize fetchable resource URLs while retaining data/blob references."""
    scheme = urlsplit(url).scheme.lower()
    if scheme not in {"http", "https"}:
        logger.debug("[FIX:crawler-resource] skipped non-HTTP resource scheme=%s", scheme or "relative")
        return None
    return _normalize(url)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _safe_log_url(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path or '/'}"


async def _close_browser_pool(browser_pool: BrowserPoolBoundary) -> None:
    """Complete browser cleanup before propagating cancellation."""
    logger.debug("[WP4.3] closing rendered browser pool")
    close_task = asyncio.create_task(browser_pool.close())
    try:
        await asyncio.shield(close_task)
    except asyncio.CancelledError:
        await close_task
        raise
    logger.debug("[WP4.3] rendered browser pool closed")
