from __future__ import annotations

import asyncio

import httpx
from agentready.browser_pool import BrowserPool, BrowserPoolConfig
from agentready.crawl_profiles import resolve_profile
from agentready.crawler import (
    AsyncCrawler,
    CrawlConfig,
    CrawlItem,
    CrawlItemState,
    CrawlScope,
    Frontier,
)
from agentready.egress import EgressPolicy
from agentready.page_parser import parse_page


def test_frontier_is_deduplicated_and_priority_ordered() -> None:
    frontier = Frontier()
    assert frontier.add(CrawlItem("https://example.test/late", 1, priority=200))
    assert not frontier.add(CrawlItem("https://example.test/late", 1, priority=200))
    assert frontier.add(CrawlItem("https://example.test/early", 1, priority=10))
    item = frontier.pop()
    assert item is not None and item.url.endswith("/early")
    frontier.set_state(item.url, CrawlItemState.PARSED)
    assert frontier.discovered == 2


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
    page = parse_page(b"<title> Home </title><a href='/next'>next</a><img src='/a.png'><p>Hello</p>")
    assert page.title == "Home"
    assert page.links == ("/next",)
    assert page.resources == ("/a.png",)
    assert "Hello" in page.text


def test_profiles_have_hard_caps() -> None:
    profile = resolve_profile("deep", hard_caps=CrawlConfig(max_pages=1000, max_depth=8, concurrency=2, per_origin_concurrency=1, timeout=10, max_duration=60))
    assert profile.config.max_pages == 1000
    assert profile.config.max_depth == 8
    assert profile.config.concurrency == 2
    assert profile.config.per_origin_concurrency == 1


def test_crawler_has_deterministic_order_and_partial_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        routes = {
            "https://example.test": b"<a href='/b'>b</a><a href='/a'>a</a>",
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
        except RuntimeError as exc:
            assert "optional browser extra" in str(exc)
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

    import pytest

    asyncio.run(run())
