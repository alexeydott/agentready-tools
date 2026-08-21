from __future__ import annotations

import ast
import asyncio
import builtins
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Self

import pytest
import httpx

from agentready.audit_core.collection import CollectedPage, FactView, replay_collected_pages
from agentready.audit_core.run_context import AuditRunContext
from agentready.audit_core.store import ContentRetention, SQLiteSiteStore
from agentready.browser_pool import (
    BrowserPool,
    BrowserPoolConfig,
    CapabilityUnavailableError,
)
from agentready.crawler import AsyncCrawler, CrawlConfig, CrawlScope
from agentready.egress import EgressPolicy
from agentready.http import CollectedHttpClient
from agentready.mobile_checks import MOBILE_STATIC_CHECKS

ROOT = Path(__file__).parents[1]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".", 1)[0])
    return names


def test_v2_collection_orchestration_keeps_http_boundary_in_fetcher() -> None:
    assert "httpx" not in _imports(ROOT / "src" / "agentready" / "crawler.py")
    assert "httpx" not in _imports(ROOT / "src" / "agentready" / "audit_service.py")
    assert "httpx" in _imports(ROOT / "src" / "agentready" / "fetcher.py")


def test_collected_page_and_fact_view_are_immutable_analyzer_inputs() -> None:
    page = CollectedPage("https://example.test/", 0, 200, None, None)
    view = FactView(page)
    assert view.url == page.url
    assert view.facts is None
    with pytest.raises(AttributeError):
        view.page = page  # type: ignore[misc]


def test_v2_crawler_keeps_playwright_boundary_in_browser_pool() -> None:
    assert "playwright" not in _imports(ROOT / "src" / "agentready" / "crawler.py")
    assert "playwright" in _imports(ROOT / "src" / "agentready" / "browser_pool.py")


def test_renderers_keep_playwright_boundary_in_browser_pool() -> None:
    for path in (
        ROOT / "src" / "agentready" / "mobile_render.py",
        ROOT / "src" / "agentready" / "seo_crawler.py",
    ):
        assert "playwright" not in _imports(path)
        assert "sync_playwright" not in path.read_text(encoding="utf-8")


def test_transport_adapters_delegate_v2_execution_to_audit_service() -> None:
    for path in (
        ROOT / "src" / "agentready" / "cli.py",
        ROOT / "src" / "agentready" / "server.py",
        ROOT / "src" / "agentready" / "mcp_server.py",
    ):
        imports = _imports(path)
        assert "audit_service" in imports
        assert "httpx" not in imports
        assert "playwright" not in imports


def test_readiness_and_mobile_adapters_use_the_shared_collection_cache():
    audit_source = (ROOT / "src" / "agentready" / "audit_service.py").read_text(encoding="utf-8")
    mobile_source = (ROOT / "src" / "agentready" / "mobile_scanner.py").read_text(encoding="utf-8")
    assert "CachedHttpTransport" in audit_source
    assert "fact_views=fact_views" in audit_source
    assert "AuditService" in mobile_source
    assert "HttpClient" not in mobile_source
    assert "BrowserPool(" not in mobile_source


def test_collected_http_client_replays_analyzer_page_without_second_fetch() -> None:
    class FailOnFetch:
        def get(self, *_: object, **__: object) -> object:
            raise AssertionError("analyzer attempted a duplicate network fetch")

    url = "https://example.test/"
    view = FactView(
        CollectedPage(
            url,
            0,
            200,
            None,
            None,
            headers=(("content-type", "text/html; charset=utf-8"),),
            body=b"<html><title>Collected</title></html>",
            requested_url=url,
        )
    )
    client = CollectedHttpClient(FailOnFetch(), (view,))  # type: ignore[arg-type]

    fetched = client.get(url, headers={"Accept": "text/html"})

    assert fetched.text == "<html><title>Collected</title></html>"
    assert fetched.status_code == 200
    assert client.timeout == 5.0


def test_multiple_mobile_analyzers_reuse_one_collected_representation() -> None:
    url = "https://example.test/"
    view = FactView(
        CollectedPage(
            url,
            0,
            200,
            None,
            None,
            headers=(("content-type", "text/html; charset=utf-8"),),
            body=(
                b"<html><head><meta name='viewport' content='width=device-width, initial-scale=1'>"
                b"<style>@media (max-width: 600px) { body { width: auto; } }</style></head>"
                b"<body><button>Run</button></body></html>"
            ),
            requested_url=url,
        )
    )
    client = CollectedHttpClient(None, (view,))

    results = [check(url, client) for check in MOBILE_STATIC_CHECKS]

    assert len(results) == len(MOBILE_STATIC_CHECKS)
    assert {result.id for result in results} == {
        "viewport-meta",
        "responsive-css",
        "fixed-width-elements",
        "touch-targets",
        "font-readability",
        "mobile-indexability",
    }


def test_browser_pool_reports_missing_optional_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def block_playwright(name: str, *args: object, **kwargs: object) -> object:
        if name == "playwright.async_api" or name.startswith("playwright."):
            raise ImportError("blocked for capability test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_playwright)

    async def run() -> None:
        pool = BrowserPool(EgressPolicy(), config=BrowserPoolConfig(max_contexts=1))
        with pytest.raises(CapabilityUnavailableError) as error:
            await pool.start()
        assert error.value.capability == "Playwright browser support"
        assert "optional browser extra" in error.value.remediation

    asyncio.run(run())


class _FakeFetcher:
    def __init__(self, **_: object) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


class _FailingFetcher(_FakeFetcher):
    async def __aenter__(self) -> Self:
        raise RuntimeError("fetcher setup failed")


class _FakePage:
    url = "https://example.test/"

    async def content(self) -> str:
        return "<title>Rendered</title><a href='/rendered'>Rendered link</a>"


class _FakeBrowserPool:
    def __init__(self, *, block_navigation: bool = False) -> None:
        self.block_navigation = block_navigation
        self.started = False
        self.closed = False
        self.navigation_started = asyncio.Event()
        self.page_closed = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    @asynccontextmanager
    async def page(self, *, user_agent: str | None = None):
        del user_agent
        try:
            yield _FakePage()
        finally:
            self.page_closed = True

    async def goto(self, page: _FakePage, url: str, **kwargs: object) -> SimpleNamespace:
        del page, url, kwargs
        self.navigation_started.set()
        if self.block_navigation:
            await asyncio.Event().wait()
        return SimpleNamespace(status=200)


def _crawler(
    pool: _FakeBrowserPool,
    *,
    fetcher_factory: object = _FakeFetcher,
) -> AsyncCrawler:
    return AsyncCrawler(
        CrawlScope(("https://example.test/",), allowed_origins=("https://example.test",)),
        config=CrawlConfig(max_pages=1, concurrency=1, min_request_interval_ms=0, max_duration=10),
        policy=EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
        render=True,
        fetcher_factory=fetcher_factory,  # type: ignore[arg-type]
        browser_pool_factory=lambda _: pool,
    )


def test_rendered_crawler_closes_browser_pool_after_success() -> None:
    async def run() -> _FakeBrowserPool:
        pool = _FakeBrowserPool()
        result = await _crawler(pool).crawl()
        assert result.coverage.fetched == 1
        return pool

    pool = asyncio.run(run())
    assert pool.started
    assert pool.page_closed
    assert pool.closed


def test_rendered_crawler_closes_browser_pool_after_error() -> None:
    async def run() -> _FakeBrowserPool:
        pool = _FakeBrowserPool()
        with pytest.raises(RuntimeError, match="fetcher setup failed"):
            await _crawler(pool, fetcher_factory=_FailingFetcher).crawl()
        return pool

    pool = asyncio.run(run())
    assert pool.started
    assert pool.closed


def test_rendered_crawler_closes_browser_pool_after_cancellation() -> None:
    async def run() -> _FakeBrowserPool:
        pool = _FakeBrowserPool(block_navigation=True)
        task = asyncio.create_task(_crawler(pool).crawl())
        await pool.navigation_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return pool

    pool = asyncio.run(run())
    assert pool.page_closed
    assert pool.closed


def test_pair_rendered_preserves_static_and_rendered_representations() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<title>Static</title>",
        )

    async def run() -> tuple[object, _FakeBrowserPool]:
        pool = _FakeBrowserPool()
        crawler = AsyncCrawler(
            CrawlScope(("https://example.test/",), allowed_origins=("https://example.test",)),
            config=CrawlConfig(max_pages=1, concurrency=1, min_request_interval_ms=0, max_duration=10),
            policy=EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
            transport=httpx.MockTransport(handler),
            pair_rendered=True,
            browser_pool_factory=lambda _: pool,
        )
        result = await crawler.crawl()
        return result, pool

    result, pool = asyncio.run(run())
    page = result.pages[0]
    assert page.parsed is not None
    assert page.parsed.facts is not None
    assert page.parsed.facts.titles == ("Static",)
    assert page.rendered is not None
    assert page.rendered.parsed is not None
    assert page.rendered.parsed.facts is not None
    assert page.rendered.parsed.facts.titles == ("Rendered",)
    assert page.parsed.representation is not page.rendered.parsed.representation
    assert pool.closed


@pytest.mark.parametrize(
    "retention",
    [ContentRetention.METADATA_ONLY, ContentRetention.SAMPLES, ContentRetention.FULL_CONTENT],
)
def test_pair_rendered_persists_replays_and_compares_representations(tmp_path: Path, retention: ContentRetention) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<title>Static</title><a href='/static'>Static link</a>",
        )

    async def run() -> tuple[str, SQLiteSiteStore]:
        store = SQLiteSiteStore(tmp_path / f"paired-replay-{retention.value}.sqlite", retention=retention)
        context = AuditRunContext.create(
            "https://example.test/",
            {"max_pages": 1, "pair_rendered": True},
            tool_version="test",
            rule_catalog_version="rules",
            run_id="run-paired-replay",
        )
        pool = _FakeBrowserPool()
        await AsyncCrawler(
            CrawlScope(("https://example.test/",), allowed_origins=("https://example.test",)),
            config=CrawlConfig(max_pages=1, concurrency=1, min_request_interval_ms=0, max_duration=10),
            policy=EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
            transport=httpx.MockTransport(handler),
            store=store,
            run_context=context,
            pair_rendered=True,
            browser_pool_factory=lambda _: pool,
        ).crawl()
        return context.run_id, store

    run_id, store = asyncio.run(run())
    try:
        representations = tuple(store.iter_representations(run_id, "https://example.test/"))
        assert {item.source for item in representations} == {"static-html", "rendered-dom"}
        if retention is ContentRetention.METADATA_ONLY:
            assert all(item.body is None for item in representations)
        assert all(item.facts for item in representations)
        occurrences = tuple(store.iter_link_occurrences(run_id))
        assert {item.representation_id for item in occurrences} == {item.representation_id for item in representations}

        replayed = replay_collected_pages(store, run_id)
        view = FactView(replayed[0])
        comparison = view.representation_comparison
        assert comparison is not None
        assert comparison.title_changed is True
        assert comparison.added_links == ("https://example.test/rendered",)
        assert comparison.removed_links == ("https://example.test/static",)
    finally:
        store.close()
