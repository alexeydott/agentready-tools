from __future__ import annotations

import ast
import asyncio
import builtins
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Self

import pytest

from agentready.browser_pool import (
    BrowserPool,
    BrowserPoolConfig,
    CapabilityUnavailableError,
)
from agentready.crawler import AsyncCrawler, CrawlConfig, CrawlScope
from agentready.egress import EgressPolicy

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
        return "<title>Rendered</title>"


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
