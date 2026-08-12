from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace

import httpx
import pytest

from agentready.audit_core import (
    AuditRunContext,
    ContentRetention,
    MemorySiteStore,
    RunUrlState,
    SQLiteSiteStore,
)
from agentready.browser_pool import (
    BrowserPool,
    BrowserPoolConfig,
    CapabilityUnavailableError,
)
from agentready.crawl_profiles import resolve_profile
from agentready.crawler import (
    AsyncCrawler,
    CrawlConfig,
    CrawlItem,
    CrawlItemState,
    CrawlScope,
    CrawlSeeds,
    Frontier,
    ScopePolicy,
)
from agentready.egress import EgressPolicy
from agentready.page_parser import Representation, RepresentationSource, parse_page


def test_frontier_is_deduplicated_and_priority_ordered() -> None:
    frontier = Frontier()
    assert frontier.add(CrawlItem("https://example.test/late", 1, priority=200))
    assert not frontier.add(CrawlItem("https://example.test/late", 1, priority=200))
    assert frontier.add(CrawlItem("https://example.test/early", 1, priority=10))
    item = frontier.pop()
    assert item is not None and item.url.endswith("/early")
    frontier.set_state(item.url, CrawlItemState.PARSED)
    assert frontier.discovered == 2


def test_scope_separates_seed_urls_from_scope_policy() -> None:
    scope = CrawlScope(
        ("https://example.test/docs/start?lang=en",),
        allowed_origins=("https://example.test",),
        include_rules=("https://example.test/docs/*",),
        exclude_rules=("https://example.test/docs/private*",),
    )
    assert scope.seeds == CrawlSeeds(("https://example.test/docs/start?lang=en",))
    assert scope.policy == ScopePolicy(
        ("https://example.test",),
        ("https://example.test/docs/*",),
        ("https://example.test/docs/private*",),
    )
    assert CrawlScope.from_parts(scope.seeds, scope.policy) == scope
    assert scope.allows("https://example.test/docs/next")
    assert not scope.allows("https://example.test/docs/private")
    assert not scope.allows("https://other.example/docs/next")


def test_scope_preserves_seed_path_query_and_trailing_slash_variants() -> None:
    seeds = (
        "https://example.test",
        "https://example.test/",
        "https://example.test/nested/path",
        "https://example.test/nested/path?view=full",
    )
    scope = CrawlScope(seeds, allowed_origins=("https://example.test",))
    assert scope.seeds.urls == seeds


def test_crawler_url_identity_keeps_slash_query_and_fragment_fetch_rules() -> None:
    from agentready.crawler import _normalize

    assert _normalize("HTTPS://Example.test/foo") == "https://example.test/foo"
    assert _normalize("https://example.test/foo/") == "https://example.test/foo/"
    assert _normalize("https://example.test/foo?token=redacted#section") == (
        "https://example.test/foo?token=redacted"
    )


def test_frontier_large_corpus_is_deterministic() -> None:
    def build() -> tuple[str, ...]:
        frontier = Frontier()
        for index in range(10000):
            frontier.add(CrawlItem(f"https://example.test/page-{index:05d}", index % 8, priority=index % 8))
        values = []
        while (item := frontier.pop()) is not None:
            values.append(item.url)
        return tuple(values)

    first = build()
    assert len(first) == 10000
    assert first == build()


def test_parser_fallback_extracts_links_and_resources() -> None:
    body = b"""<html lang="en"><head><title> Home </title>
    <meta name="description" content="Description">
    <link rel="canonical" href="/home"></head><body>
    <a href='/next'>one</a><a href='/next'>two</a>
    <img src='/a.png' alt="A"><img src='/a.png'><p>Hello</p></body></html>"""
    representation = Representation.from_body(
        body,
        representation_id="rep-static",
        run_id="run-1",
        url_key="https://example.test/",
        source=RepresentationSource.STATIC_HTML,
    )
    page = parse_page(body, representation=representation)
    assert page.title == "Home"
    assert page.links == ("/next",)
    assert page.resources == ("/home", "/a.png")
    assert "Hello" in page.text
    assert page.representation == representation
    assert page.facts is not None
    assert [link.anchor_text for link in page.facts.links] == ["one", "two"]
    assert [link.resolved_url for link in page.facts.links] == [
        "https://example.test/next",
        "https://example.test/next",
    ]
    assert [resource.ordinal for resource in page.facts.resources] == [0, 1, 2]
    assert page.facts.descriptions == ("Description",)
    assert page.facts.lang == "en"


def test_profiles_have_hard_caps() -> None:
    profile = resolve_profile("deep", hard_caps=CrawlConfig(max_pages=1000, max_depth=8, concurrency=2, per_origin_concurrency=1, timeout=10, max_duration=60))
    assert profile.config.max_pages == 1000
    assert profile.config.max_depth == 8
    assert profile.config.concurrency == 2
    assert profile.config.per_origin_concurrency == 1


def test_crawler_has_deterministic_order_and_partial_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        routes = {
            "https://example.test/": b"<a href='/b'>b</a><a href='/a'>a</a>",
            "https://example.test/a": b"<title>A</title>",
            "https://example.test/b": b"<title>B</title>",
        }
        return httpx.Response(200, headers={"content-type": "text/html"}, content=routes.get(str(request.url), b""))

    transport = httpx.MockTransport(handler)
    scope = CrawlScope(("https://example.test/",), allowed_origins=("https://example.test",))
    result = asyncio.run(AsyncCrawler(
        scope,
        config=CrawlConfig(max_pages=3, concurrency=2, per_origin_concurrency=1, min_request_interval_ms=0, max_duration=10),
        policy=EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
        transport=transport,
    ).crawl())
    assert [page.url for page in result.pages] == sorted(page.url for page in result.pages)
    assert result.coverage.fetched == 3
    assert result.coverage.max_pages_hit is True


def test_browser_pool_requires_optional_dependency_or_starts() -> None:
    async def run() -> None:
        pool = BrowserPool(EgressPolicy(), config=BrowserPoolConfig(max_contexts=1))
        try:
            await pool.start()
        except CapabilityUnavailableError as exc:
            message = str(exc)
            assert "optional browser extra" in message or "Chromium browser binary" in message
            assert exc.capability
            assert exc.remediation
        else:
            await pool.close()

    asyncio.run(run())


def test_crawler_cancellation_cleans_up_workers() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(1)
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<p>slow</p>")

        crawler = AsyncCrawler(
            CrawlScope(("https://example.test",), allowed_origins=("https://example.test",)),
            config=CrawlConfig(max_pages=1000, concurrency=2, min_request_interval_ms=0, max_duration=10),
            policy=EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
            transport=httpx.MockTransport(handler),
        )
        task = asyncio.create_task(crawler.crawl())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())


@pytest.mark.parametrize("concurrency", [1, 2, 8])
def test_crawler_waits_for_active_root_before_sending_worker_sentinels(concurrency: int) -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).rstrip("/") == "https://example.test":
                await asyncio.sleep(0.001)
                return httpx.Response(
                    200,
                    headers={"content-type": "text/html"},
                    content=b'<a href="/child">child</a>',
                )
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"<title>Child</title>",
            )

        for _ in range(100):
            result = await AsyncCrawler(
                CrawlScope(("https://example.test/",), allowed_origins=("https://example.test",)),
                config=CrawlConfig(
                    max_pages=2,
                    concurrency=concurrency,
                    per_origin_concurrency=concurrency,
                    min_request_interval_ms=0,
                    max_duration=10,
                ),
                policy=EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
                transport=httpx.MockTransport(handler),
            ).crawl()
            assert {page.url for page in result.pages} == {
                "https://example.test/",
                "https://example.test/child",
            }
            assert result.coverage.failed == 0

    asyncio.run(run())


def test_crawler_deadline_is_classified_as_partial() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0.02)
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<p>slow</p>")

        result = await AsyncCrawler(
            CrawlScope(("https://example.test/",), allowed_origins=("https://example.test",)),
            config=CrawlConfig(
                max_pages=10,
                concurrency=2,
                per_origin_concurrency=2,
                min_request_interval_ms=0,
                max_duration=0.001,
            ),
            policy=EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
            transport=httpx.MockTransport(handler),
        ).crawl()
        assert result.coverage.deadline_hit is True
        assert result.coverage.classification.value == "partial_limit"

    asyncio.run(run())


def test_crawler_leaves_no_queued_urls_when_max_pages_stops_scheduling() -> None:
    """Stopping at max_pages must leave every discovered URL in a terminal state.

    Both the worker-side limit check and the scheduler-side queue drain mark
    remaining work as SKIPPED_POLICY; neither may leave stale ``queued`` rows in
    run inventory nor under-report ``skipped_policy`` coverage.
    """

    async def run() -> None:
        store = MemorySiteStore()
        context = AuditRunContext.create(
            "https://example.test",
            {"max_pages": 5},
            tool_version="test",
            rule_catalog_version="rules-1",
            run_id="run-drained",
        )

        async def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).rstrip("/") == "https://example.test":
                links = b"".join(
                    f'<a href="/p{index}">p{index}</a>'.encode() for index in range(12)
                )
                return httpx.Response(200, headers={"content-type": "text/html"}, content=links)
            await asyncio.sleep(0.02)
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<title>child</title>")

        result = await AsyncCrawler(
            CrawlScope(("https://example.test/",), allowed_origins=("https://example.test",)),
            config=CrawlConfig(
                max_pages=5,
                concurrency=4,
                per_origin_concurrency=4,
                min_request_interval_ms=0,
                max_duration=10,
            ),
            policy=EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
            transport=httpx.MockTransport(handler),
            store=store,
            run_context=context,
        ).crawl()

        assert result.coverage.max_pages_hit is True
        assert len(result.pages) == 5
        records = list(store.iter_run_urls("run-drained"))
        assert records
        assert all(record.state is not RunUrlState.QUEUED for record in records)
        skipped = [record for record in records if record.state is RunUrlState.SKIPPED]
        assert skipped, "expected URLs beyond max_pages to be recorded as skipped"
        assert result.coverage.skipped_policy == len(skipped)

    asyncio.run(run())


def test_crawler_propagates_run_id_to_fetch_and_store_records() -> None:
    async def run() -> None:
        store = MemorySiteStore()
        context = AuditRunContext.create(
            "https://example.test",
            {"max_pages": 1},
            tool_version="0.8.1",
            rule_catalog_version="rules-1",
            run_id="run-propagated",
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b'<a href="/child">one</a><a href="/child">two</a><img src="/asset.png"><img src="/asset.png"><p>ok</p>',
            )

        result = await AsyncCrawler(
            CrawlScope(("https://example.test/",), allowed_origins=("https://example.test",)),
            config=CrawlConfig(max_pages=1, min_request_interval_ms=0),
            policy=EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
            transport=httpx.MockTransport(handler),
            store=store,
            run_context=context,
        ).crawl()
        assert result.coverage.fetched == 1
        pages = list(store.iter_pages("run-propagated"))
        assert [page.run_id for page in pages] == ["run-propagated"]
        assert pages[0].title == ""
        assert pages[0].content_hash == hashlib.sha256(
            b'<a href="/child">one</a><a href="/child">two</a><img src="/asset.png"><img src="/asset.png"><p>ok</p>'
        ).hexdigest()
        assert pages[0].locally_indexable is True
        assert ("run-propagated", "https://example.test/", "/child") in store._links
        links = list(store.iter_link_occurrences("run-propagated"))
        assert [link.anchor_text for link in links] == ["one", "two"]
        resources = list(store.iter_resource_occurrences("run-propagated"))
        assert [resource.ordinal for resource in resources] == [0, 1]
        assert store._runs["run-propagated"].state == "partial"
        assert store._runs["run-propagated"].finished_at is not None

    asyncio.run(run())


def test_crawler_persists_redirect_inventory_from_fetch_result() -> None:
    from agentready.fetcher import FetchResult, RedirectHop

    class FakeFetcher:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, request, *, use_cache=True):
            return FetchResult(
                url=request.url,
                status_code=200,
                headers={"content-type": "text/html"},
                body=b"<title>Final</title>",
                redirects=("https://example.test/old",),
                elapsed_ms=1,
                redirect_records=(RedirectHop(
                    from_url="https://example.test/old",
                    status_code=301,
                    location_raw="/",
                    to_url="https://example.test/",
                    cross_origin=False,
                    downgrade_https_to_http=False,
                ),),
            )

    async def run() -> None:
        store = MemorySiteStore()
        context = AuditRunContext.create(
            "https://example.test/",
            {"max_pages": 1},
            tool_version="test",
            rule_catalog_version="rules-1",
            run_id="run-redirect-golden",
        )
        await AsyncCrawler(
            CrawlScope(("https://example.test/",), allowed_origins=("https://example.test",)),
            config=CrawlConfig(max_pages=1, min_request_interval_ms=0),
            policy=EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
            fetcher_factory=FakeFetcher,
            store=store,
            run_context=context,
        ).crawl()
        assert list(store.iter_redirects("run-redirect-golden"))

    asyncio.run(run())


def test_crawler_projects_page_facts_and_redirects_with_memory_sqlite_parity(tmp_path) -> None:
    body = (
        b'<html><head><title>Home</title><meta name="robots" content="noindex,follow">'
        b'<link rel="canonical" href="/preferred"></head><body>'
        b'<a href="/child">Child</a><img src="/hero.png" alt="Hero"><p>Hello world</p></body></html>'
    )

    class FakeFetcher:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, request, *, use_cache=True):
            from agentready.fetcher import FetchResult, RedirectHop

            return FetchResult(
                url=request.url,
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body=body,
                redirects=("https://example.test/old",),
                elapsed_ms=1,
                redirect_records=(RedirectHop(
                    from_url="https://example.test/old",
                    status_code=301,
                    location_raw="/",
                    to_url="https://example.test/",
                    cross_origin=False,
                    downgrade_https_to_http=False,
                ),),
            )

    async def run(store, run_id: str) -> None:
        context = AuditRunContext.create(
            "https://example.test/",
            {"max_pages": 1},
            tool_version="test",
            rule_catalog_version="rules-1",
            run_id=run_id,
        )
        await AsyncCrawler(
            CrawlScope(("https://example.test/",), allowed_origins=("https://example.test",)),
            config=CrawlConfig(max_pages=1, min_request_interval_ms=0),
            policy=EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
            fetcher_factory=FakeFetcher,
            store=store,
            run_context=context,
        ).crawl()

    memory = MemorySiteStore(retention=ContentRetention.FULL_CONTENT)
    sqlite = SQLiteSiteStore(tmp_path / "crawler-projection.sqlite", retention=ContentRetention.FULL_CONTENT)
    try:
        asyncio.run(run(memory, "run-memory"))
        asyncio.run(run(sqlite, "run-sqlite"))
        memory_page = next(memory.iter_pages("run-memory"))
        sqlite_page = next(sqlite.iter_pages("run-sqlite"))
        assert memory_page.title == "Home"
        assert memory_page.canonical == "https://example.test/preferred"
        assert memory_page.locally_indexable is False
        assert memory_page.content_hash == hashlib.sha256(body).hexdigest()
        assert "Hello world" in (memory_page.content or "")
        assert next(iter(memory.iter_redirects("run-memory"))).from_url == "https://example.test/old"
        assert next(iter(memory.iter_link_occurrences("run-memory"))).resolved_url == "https://example.test/child"
        resources = list(memory.iter_resource_occurrences("run-memory"))
        assert next(resource for resource in resources if resource.resource_url == "/hero.png").resolved_url == "https://example.test/hero.png"
        assert memory_page == replace(sqlite_page, run_id="run-memory")
    finally:
        sqlite.close()
