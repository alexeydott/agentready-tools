from typing import ClassVar

import pytest

from agentready.agentfindings import build_findings
from agentready.browser_pool import CapabilityUnavailableError
from agentready.seo_checks import SEO_CHECKS_BY_ID, SeoHtmlParser
from agentready.seo_crawler import (
    CRAWL_CHECK_METADATA,
    CrawledPage,
    check_broken_links,
    check_duplicate_metadata,
    check_insecure_links_pages,
    check_internal_nofollow,
    check_link_counts,
    check_redirect_chains,
    crawl_site,
)


class FakeResponse:
    def __init__(self, html: str, url: str = "https://example.com/", status: int = 200):
        self.status_code = status
        self.content_type = "text/html"
        self.text = html
        self.body = html.encode()
        self.headers: dict[str, str] = {}
        self.url = url
        self.redirected_from: list[str] = []

    def evidence(self, action: str, **kwargs):
        from agentready.models import Evidence

        return Evidence(action=action, url=self.url)


class FakeClient:
    def __init__(self, html: str, url: str = "https://example.com/"):
        self._response = FakeResponse(html, url)

    def get(self, url: str, **kwargs):
        return FakeResponse(self._response.text, url)


def run_check(check_id: str, html: str, url: str = "https://example.com/"):
    return SEO_CHECKS_BY_ID[check_id](url, FakeClient(html, url))


GOOD_HTML = """
<html lang="en"><head>
<title>A sufficiently long descriptive page title here</title>
<meta name="description" content="A descriptive summary of the page that is long enough to be useful in snippets and search results pages.">
</head><body><h1>Main heading</h1><p>Real content here.</p></body></html>
"""


def test_title_length_pass_and_warn():
    assert run_check("title-length", GOOD_HTML).status == "pass"
    short = run_check("title-length", "<title>Short</title><p>x</p>")
    assert short.status == "warn" and "too short" in short.details
    long_title = "<title>" + "x" * 80 + "</title><p>y</p>"
    long = run_check("title-length", long_title)
    assert long.status == "warn" and "too long" in long.details
    assert long.evidence[0].metrics["page"] == "https://example.com/"
    assert long.evidence[0].metrics["resource"] == "https://example.com/"
    assert long.evidence[0].metrics["length"] == 80


def test_description_length_bounds():
    assert run_check("description-length", GOOD_HTML).status == "pass"
    short = run_check("description-length", '<meta name="description" content="tiny"><p>x</p>')
    assert short.status == "warn"


def test_multiple_metadata_detects_duplicate_tags():
    html = "<title>One</title><title>Two</title><p>x</p>"
    result = run_check("multiple-metadata", html)
    assert result.status == "fail" and "2 title tags" in result.details


def test_metadata_collisions_detects_identical_title_h1():
    html = "<title>Same Text</title><h1>Same Text</h1><p>x</p>"
    result = run_check("metadata-collisions", html)
    assert result.status == "warn" and "identical to H1" in result.details


def test_metadata_special_chars_detects_emoji():
    html = "<title>Great page 🚀</title><p>x</p>"
    result = run_check("metadata-special-chars", html)
    assert result.status == "warn" and "emoji" in result.details


def test_image_alt_counts_missing_alt():
    html = '<img src="a.png"><img src="b.png" alt="descriptive">'
    result = run_check("image-alt", html)
    assert result.status == "warn" and "1 of 2" in result.details
    assert result.evidence[0].metrics["image_count"] == 2
    assert result.evidence[0].metrics["missing_count"] == 1
    assert len(result.evidence[0].metrics["images"]) == 1
    assert result.evidence[0].metrics["images"][0]["page"] == "https://example.com/"
    assert result.evidence[0].metrics["images"][0]["resource"] == "https://example.com/a.png"
    assert run_check("image-alt", "<p>no images</p>").status == "skip"


def test_problem_evidence_lists_only_insecure_resources_and_links():
    mixed = run_check("mixed-content", '<img src="http://example.com/a.png"><script src="https://example.com/app.js"></script>')
    assert mixed.status == "fail"
    assert mixed.evidence[0].metrics["resource_count"] == 2
    assert mixed.evidence[0].metrics["insecure_count"] == 1
    assert mixed.evidence[0].metrics["insecure_resources"] == ["http://example.com/a.png"]

    links = run_check("insecure-links", '<a href="http://example.com/b">bad</a><a href="https://example.com/good">good</a>')
    assert links.status == "warn"
    assert links.evidence[0].metrics["link_count"] == 2
    assert links.evidence[0].metrics["insecure_count"] == 1
    assert len(links.evidence[0].metrics["insecure_links"]) == 1


def test_crawl_insecure_links_lists_affected_page_urls_and_counts():
    insecure_parser = SeoHtmlParser()
    insecure_parser.feed('<a href="http://example.com/old">old</a><a href="/safe">safe</a>')
    insecure_parser.close()
    clean_parser = SeoHtmlParser()
    clean_parser.feed('<a href="https://example.com/safe">safe</a>')
    clean_parser.close()
    result = check_insecure_links_pages(
        [
            CrawledPage("https://example.com/", 200, insecure_parser, [], 1),
            CrawledPage("https://example.com/clean", 200, clean_parser, [], 1),
        ],
        "https://example.com/",
    )
    assert result.status == "warn"
    assert "https://example.com/" in result.details
    assert len(result.evidence) == 1
    assert result.evidence[0].url == "https://example.com/"
    assert result.evidence[0].metrics["affected_page_count"] == 1
    assert result.evidence[0].metrics["insecure_count"] == 1
    assert result.evidence[0].metrics["insecure_links"][0]["url"] == "http://example.com/old"


def test_crawl_insecure_links_localizes_details_and_metadata():
    from agentready.seo_i18n import seo_detail, seo_summary

    assert "небезопасными HTTP-ссылками" in seo_detail(
        "1 page(s) with insecure HTTP links: https://example.com/ (1)", "ru"
    )
    assert "обойдённых" in seo_detail("no insecure HTTP links across 2 crawled pages", "ru")
    assert "обойдённых проблемных страницах" in seo_summary("insecure-links-pages", "fallback", "ru")


def test_seo_ai_findings_include_page_or_resource_url():
    from agentready.seo_models import SeoCategoryScore, SeoReport

    result = run_check("image-alt", '<img src="/img/problem.jpg">', "https://example.com/products")
    report = SeoReport(
        schema="agentready.seo.v2",
        target="https://example.com/products",
        origin="https://example.com",
        checks=[result],
        score=0,
        categories=[SeoCategoryScore("content", 0, 1, 0)],
        recommendations=[],
        started_at="now",
        finished_at="now",
    )
    evidence = build_findings(report)["findings"][0]["evidence"]
    assert evidence == ["page/resource: https://example.com/products; inspect image attributes"]


def test_mixed_content_and_insecure_links():
    html = '<img src="http://cdn.example.com/x.png"><a href="http://example.com/other">x</a>'
    assert run_check("mixed-content", html).status == "fail"
    assert run_check("insecure-links", html).status == "warn"
    # Non-HTTPS pages skip these checks
    assert run_check("mixed-content", html, url="http://example.com/").status == "skip"


def test_https_scheme_and_url_format():
    assert run_check("https-scheme", GOOD_HTML).status == "pass"
    assert run_check("https-scheme", GOOD_HTML, url="http://example.com/").status == "fail"
    assert run_check("url-format", GOOD_HTML).status == "pass"
    assert run_check("url-format", GOOD_HTML, url="https://example.com/MixedCase").status == "warn"


def test_meta_refresh_detected():
    html = '<meta http-equiv="refresh" content="5; url=https://example.com/new">'
    assert run_check("meta-refresh", html).status == "fail"
    assert run_check("meta-refresh", GOOD_HTML).status == "pass"


def test_content_size_and_quality():
    result = run_check("content-size", GOOD_HTML)
    assert result.status in {"pass", "warn"}
    lorem = "<p>lorem ipsum dolor sit amet</p>" * 20
    assert run_check("content-quality", lorem).status == "fail"
    assert run_check("content-quality", GOOD_HTML).status == "pass"


def test_microdata_and_hreflang():
    assert run_check("microdata", '<div itemscope itemtype="https://schema.org/Article">x</div>').status == "pass"
    assert run_check("microdata", GOOD_HTML).status == "warn"
    assert run_check("hreflang", GOOD_HTML).status == "skip"
    bad = '<link rel="alternate" hreflang="xx!?" href="/fr"><link rel="alternate" hreflang="en" href="https://example.com/">'
    result = run_check("hreflang", bad)
    assert result.status == "warn"


def test_crawl_checks_with_synthetic_pages():
    ok_page = CrawledPage("https://example.com/", 200, None, [], 10)
    broken = CrawledPage("https://example.com/404", 404, None, [], 10)
    assert check_broken_links([ok_page], "https://example.com/").status == "pass"
    assert check_broken_links([ok_page, broken], "https://example.com/").status == "fail"

    chained = CrawledPage("https://example.com/final", 200, None, ["https://example.com/a", "https://example.com/b"], 10)
    assert check_redirect_chains([ok_page, chained], "https://example.com/").status == "warn"

    from agentready.seo_checks import SeoHtmlParser

    def page_with(title: str, description: str, url: str, links=None, nofollow=None):
        parser = SeoHtmlParser()
        parser.title = title
        parser.description = description
        page = CrawledPage(url, 200, parser, [], 10)
        if links is not None:
            page.links = links
        if nofollow is not None:
            page.nofollow_links = nofollow
        return page

    a = page_with("Same", "Same desc", "https://example.com/a")
    b = page_with("Same", "Same desc", "https://example.com/b")
    assert check_duplicate_metadata([a, b], "https://example.com/").status == "fail"
    unique = page_with("A", "desc a", "https://example.com/a")
    unique_b = page_with("B", "desc b", "https://example.com/b")
    assert check_duplicate_metadata([unique, unique_b], "https://example.com/").status == "pass"

    nf = page_with("T", "D", "https://example.com/a", nofollow=["/x"])
    assert check_internal_nofollow([nf], "https://example.com/").status == "warn"
    heavy = page_with("T", "D", "https://example.com/a", links=["/p"] * 200)
    assert check_link_counts([heavy], "https://example.com/").status == "warn"


def test_crawl_metadata_is_localized():
    assert len(CRAWL_CHECK_METADATA) == 6
    for item in CRAWL_CHECK_METADATA:
        assert item["title"]["en"] and item["title"]["ru"]
        assert item["description"]["en"] and item["description"]["ru"]


def test_crawl_site_stays_same_origin(monkeypatch):
    pages_seen = []

    class CrawlResponse:
        def __init__(self, url):
            self.url = url
            self.status_code = 200
            self.content_type = "text/html"
            self.text = '<a href="/internal">i</a><a href="https://other.example/x">x</a>'
            self.body = self.text.encode()
            self.redirected_from = []


    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            pages_seen.append(url)
            return CrawlResponse(url)

    monkeypatch.setattr("agentready.seo_crawler.HttpClient", FakeHttpClient)
    pages = crawl_site("https://example.com/", max_pages=5)
    assert all(page.url.startswith("https://example.com") for page in pages)
    assert len(pages) == 2  # start + /internal, external link not followed


@pytest.mark.xfail(strict=True, reason="WP2: legacy crawler must preserve trailing-slash URL identity")
def test_legacy_crawler_preserves_trailing_slash_identity(monkeypatch):
    class CrawlResponse:
        def __init__(self, url):
            self.url = url
            self.status_code = 200
            self.content_type = "text/html"
            self.text = "<title>Slash</title>"
            self.body = self.text.encode()
            self.redirected_from = []

    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            return CrawlResponse(url)

    monkeypatch.setattr("agentready.seo_crawler.HttpClient", FakeHttpClient)
    pages = crawl_site("https://example.com/foo/", max_pages=1)
    assert pages[0].url == "https://example.com/foo/"


@pytest.mark.xfail(strict=True, reason="WP2: resolve legacy links against the final response URL")
def test_legacy_crawler_resolves_relative_links_from_redirected_response(monkeypatch):
    seen: list[str] = []

    class CrawlResponse:
        def __init__(self, requested):
            self.url = "https://example.com/dir/" if requested == "https://example.com/start" else requested
            self.status_code = 200
            self.content_type = "text/html"
            self.text = '<a href="child">child</a>' if requested == "https://example.com/start" else "<title>Child</title>"
            self.body = self.text.encode()
            self.redirected_from = []

    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            seen.append(url)
            return CrawlResponse(url)

    monkeypatch.setattr("agentready.seo_crawler.HttpClient", FakeHttpClient)
    crawl_site("https://example.com/start", max_pages=2)
    assert seen == ["https://example.com/start", "https://example.com/dir/child"]


@pytest.mark.xfail(strict=True, reason="WP2: internal nofollow must exclude external targets")
def test_internal_nofollow_excludes_external_targets():
    parser = SeoHtmlParser()
    parser.feed('<a href="/internal" rel="nofollow">internal</a><a href="https://other.example/out" rel="nofollow">external</a>')
    parser.close()
    page = CrawledPage("https://example.com/", 200, parser, [], 1)
    assert check_internal_nofollow([page], "https://example.com/").status == "pass"


def test_rendered_crawl_reuses_one_browser_pool(monkeypatch):
    from contextlib import asynccontextmanager

    class CrawlResponse:
        def __init__(self, url):
            self.url = url
            self.status_code = 200
            self.content_type = "text/html"
            self.text = "<html><body>JS links</body></html>"
            self.body = self.text.encode()
            self.redirected_from = []

    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            return CrawlResponse(url)

    class FakePage:
        async def eval_on_selector_all(self, selector, script):
            assert selector == "a[href]"
            assert "nofollow" in script
            return [{"href": "https://example.com/rendered", "nofollow": True}]

    class FakeBrowserPool:
        instances: ClassVar[list["FakeBrowserPool"]] = []

        def __init__(self, policy):
            self.started = 0
            self.closed = 0
            self.pages = 0
            FakeBrowserPool.instances.append(self)

        async def start(self):
            self.started += 1

        async def close(self):
            self.closed += 1

        @asynccontextmanager
        async def page(self, **kwargs):
            self.pages += 1
            yield FakePage()

        async def goto(self, page, url, **kwargs):
            assert url == "https://example.com"

    monkeypatch.setattr("agentready.seo_crawler.HttpClient", FakeHttpClient)
    monkeypatch.setattr("agentready.seo_crawler.BrowserPool", FakeBrowserPool)
    pages = crawl_site("https://example.com/", max_pages=1, render=True)

    assert len(pages) == 1
    pool = FakeBrowserPool.instances[0]
    assert pool.started == 1
    assert pool.closed == 1
    assert pool.pages == 1
    assert pages[0].links == ["https://example.com/rendered"]
    assert pages[0].nofollow_links == ["https://example.com/rendered"]


def test_rendered_crawl_preserves_static_results_when_browser_optional_dependency_is_missing(monkeypatch, caplog):
    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            return FakeResponse("<html><body>No static links</body></html>", url=url)

    class MissingBrowserPool:
        closed = 0

        def __init__(self, policy):
            pass

        async def start(self):
            raise CapabilityUnavailableError(
                "Playwright browser support",
                "Install the optional browser extra.",
            )

        async def close(self):
            MissingBrowserPool.closed += 1

    monkeypatch.setattr("agentready.seo_crawler.HttpClient", FakeHttpClient)
    monkeypatch.setattr("agentready.seo_crawler.BrowserPool", MissingBrowserPool)
    with caplog.at_level("DEBUG", logger="agentready.seo_crawler"):
        pages = crawl_site("https://example.com/", max_pages=1, render=True)

    assert len(pages) == 1
    assert pages[0].links == []
    assert MissingBrowserPool.closed == 1
    assert "optional browser extra" in caplog.text
