import asyncio
import gzip

import httpx
import pytest

from agentready.crawler import CrawlConfig, CrawlScope
from agentready.discovery import (
    CrawlSource,
    RobotsSitemapSource,
    SingleUrlSource,
    SitemapSource,
    UrlListSource,
    discovery_plan_hash,
)
from agentready.egress import EgressPolicy
from agentready.fetcher import Fetcher


def test_single_and_url_list_sources_are_bounded_and_deduplicated():
    assert SingleUrlSource(" https://example.test/ ").discover() == ("https://example.test/",)
    source = UrlListSource(("https://example.test/a", "", "https://example.test/a", "https://example.test/b"))
    assert source.discover(limit=2) == ("https://example.test/a", "https://example.test/b")


def test_sitemap_source_parses_namespaces_and_applies_origin_policy():
    xml = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>/a</loc></url>
      <url><loc>https://example.test/b</loc></url>
      <url><loc>https://other.test/c</loc></url>
    </urlset>"""
    source = SitemapSource(xml, "https://example.test/sitemap.xml")
    assert source.discover() == ("https://example.test/a", "https://example.test/b")
    assert source.discover(limit=1) == ("https://example.test/a",)
    assert SitemapSource.from_bytes(gzip.compress(xml.encode()), "https://example.test/sitemap.xml", compressed=True).discover() == source.discover()


def test_sitemap_source_rejects_external_entity_and_oversized_payloads():
    with pytest.raises(ValueError, match="DOCTYPE"):
        SitemapSource("<!DOCTYPE urlset><urlset/>", "https://example.test/sitemap.xml").discover()
    with pytest.raises(ValueError, match="size"):
        SitemapSource("x", "https://example.test/sitemap.xml", max_bytes=0).discover()


def test_sitemap_source_resolves_bounded_nested_indexes():
    root = SitemapSource(
        "<sitemapindex><sitemap><loc>https://example.test/child.xml</loc></sitemap></sitemapindex>",
        "https://example.test/index.xml",
    )
    documents = {
        "https://example.test/index.xml": root.xml,
        "https://example.test/child.xml": "<urlset><url><loc>https://example.test/page</loc></url></urlset>",
    }
    assert root.discover_nested(documents) == ("https://example.test/page",)


def test_sitemap_source_collects_nested_documents_through_fetcher():
    documents = {
        "https://example.test/index.xml": (
            "<sitemapindex><sitemap><loc>/child.xml</loc></sitemap></sitemapindex>"
        ),
        "https://example.test/child.xml": (
            "<urlset><url><loc>/page</loc></url></urlset>"
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/xml"},
            content=documents[str(request.url)].encode(),
        )

    async def collect() -> tuple[str, ...]:
        policy = EgressPolicy(
            allowed_origins=frozenset({"https://example.test"}),
            max_response_bytes=100_000,
        )
        async with Fetcher(policy=policy, transport=httpx.MockTransport(handler)) as fetcher:
            return await SitemapSource(
                "",
                "https://example.test/index.xml",
            ).discover_from_fetcher(fetcher, limit=5)

    assert asyncio.run(collect()) == ("https://example.test/page",)


def test_robots_sitemap_source_resolves_robots_nested_and_gzip_documents():
    class FakeResponse:
        def __init__(self, body: bytes, headers: dict[str, str] | None = None):
            self.status_code = 200
            self.headers = headers or {}
            self.body = body

    class FakeFetcher:
        def __init__(self, documents):
            self.documents = documents
            self.requested = []

        async def get(self, request, *, use_cache=True):
            self.requested.append(request.url)
            body, headers = self.documents[request.url]
            return FakeResponse(body, headers)

    root = "https://example.test"
    documents = {
        f"{root}/robots.txt": (
            b"User-agent: *\nSitemap: /sitemap-index.xml\nSitemap: https://other.test/ignore.xml\n",
            {"content-type": "text/plain"},
        ),
        f"{root}/sitemap-index.xml": (
            b"<sitemapindex><sitemap><loc>/nested.xml.gz</loc></sitemap></sitemapindex>",
            {"content-type": "application/xml"},
        ),
        f"{root}/nested.xml.gz": (
            gzip.compress(b"<urlset><url><loc>/page</loc></url></urlset>"),
            {"content-type": "application/gzip"},
        ),
    }
    fetcher = FakeFetcher(documents)

    async def collect():
        return await RobotsSitemapSource(root).discover_from_fetcher(fetcher, limit=5)

    assert asyncio.run(collect()) == (f"{root}/page",)
    assert fetcher.requested == [
        f"{root}/robots.txt",
        f"{root}/sitemap-index.xml",
        f"{root}/nested.xml.gz",
    ]


def test_robots_sitemap_source_resolves_explicit_same_origin_sitemap():
    class FakeFetcher:
        async def get(self, request, *, use_cache=True):
            return type(
                "Response",
                (),
                {
                    "status_code": 200,
                    "headers": {"content-type": "application/xml"},
                    "body": b"<urlset><url><loc>/explicit</loc></url></urlset>",
                },
            )()

    async def collect():
        return await RobotsSitemapSource(
            "https://example.test/",
            sitemap_urls=("/explicit.xml", "https://other.test/no.xml"),
        ).discover_from_fetcher(FakeFetcher(), limit=5)

    assert asyncio.run(collect()) == ("https://example.test/explicit",)


def test_discovery_limits_are_validated():
    with pytest.raises(ValueError):
        SingleUrlSource("https://example.test").discover(limit=0)


def test_robots_sitemap_source_persists_5xx_robots_observation_without_raising():
    class FakeResponse:
        def __init__(self, status_code: int):
            self.status_code = status_code
            self.headers = {}
            self.body = b""
            self.url = "https://example.test/robots.txt"

    class FakeFetcher:
        async def get(self, request, *, use_cache=True):
            return FakeResponse(503)

    async def collect():
        return await RobotsSitemapSource("https://example.test/").collect_from_fetcher(FakeFetcher(), limit=5)

    result = asyncio.run(collect())
    assert result.robots.fetch_state == "unreachable"
    assert result.robots.status_code == 503
    assert result.sitemap_documents == ()
    assert result.urls == ()


def test_robots_sitemap_source_discover_from_fetcher_raises_for_5xx_robots():
    class FakeResponse:
        def __init__(self, status_code: int):
            self.status_code = status_code
            self.headers = {}
            self.body = b""
            self.url = "https://example.test/robots.txt"

    class FakeFetcher:
        async def get(self, request, *, use_cache=True):
            return FakeResponse(503)

    async def collect():
        return await RobotsSitemapSource("https://example.test/").discover_from_fetcher(FakeFetcher(), limit=5)

    with pytest.raises(ValueError, match="robots fetch failed"):
        asyncio.run(collect())


def test_collect_sitemap_tree_marks_gzip_bodies_as_compressed():
    class FakeResponse:
        def __init__(self, body: bytes, headers: dict[str, str]):
            self.status_code = 200
            self.headers = headers
            self.body = body
            self.url = "https://example.test/sitemap.xml.gz"

    class FakeFetcher:
        async def get(self, request, *, use_cache=True):
            return FakeResponse(
                gzip.compress(b"<urlset><url><loc>/page</loc></url></urlset>"),
                {"content-encoding": "gzip"},
            )

    async def collect():
        return await RobotsSitemapSource(
            "https://example.test/",
            sitemap_urls=("/sitemap.xml.gz",),
        ).collect_from_fetcher(FakeFetcher(), limit=5)

    result = asyncio.run(collect())
    assert result.urls == ("https://example.test/page",)
    assert len(result.sitemap_documents) == 1
    assert result.sitemap_documents[0].compressed is True


def test_discovery_plan_hash_is_deterministic_and_source_specific():
    first = discovery_plan_hash(UrlListSource(("https://example.test/a",)), limit=10)
    second = discovery_plan_hash(UrlListSource(("https://example.test/a",)), limit=10)
    assert first == second
    assert first != discovery_plan_hash(UrlListSource(("https://example.test/b",)), limit=10)


def test_crawl_source_uses_canonical_bounded_crawler():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b'<a href="/child">child</a>',
        )

    source = CrawlSource(
        CrawlScope(("https://example.test/",), allowed_origins=("https://example.test",)),
        CrawlConfig(max_pages=2, min_request_interval_ms=0),
        EgressPolicy(allowed_origins=frozenset({"https://example.test"})),
        httpx.MockTransport(handler),
    )
    assert source.discover(limit=2) == ("https://example.test/", "https://example.test/child")
