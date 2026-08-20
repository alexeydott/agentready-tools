"""Compatibility helpers for the canonical v2 SEO collection boundary.

The public SEO request is executed by ``AuditService`` and ``AsyncCrawler``.
These helpers remain only for metadata, fixture, and compatibility consumers;
new application code must not instantiate this crawler.

Historical implementation fetched pages breadth-first from the start URL,
staying on the same host.
Static HTML fetching via ``HttpClient`` is the default; ``render=True`` uses a
headless Chromium (Playwright) so JS-driven navigation is also discovered.

Crawl results feed cross-page checks: broken links, redirect chains/loops,
duplicate titles/descriptions/H1 across pages, internal nofollow links, and
pages with excessive link counts.
"""
from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import urldefrag, urljoin, urlsplit

from .browser_pool import BrowserPool, BrowserPoolBoundary
from .egress import EgressPolicy
from .http import FetchError, HttpClient
from .models import Evidence, Remediation
from .seo_checks import SeoHtmlParser
from .seo_models import SeoCheckResult

logger = logging.getLogger(__name__)

_GOOGLE_LINKS = "https://developers.google.com/search/docs/crawling-indexing/links-crawlable"
_GOOGLE_REDIRECTS = "https://developers.google.com/search/docs/crawling-indexing/301-redirects"
_GOOGLE_DUPLICATES = "https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls"

MAX_HTML_BYTES = 512 * 1024


class CrawledPage:
    __slots__ = ("description", "fetch_ms", "h1", "links", "nofollow_links", "redirect_chain", "status", "title", "url")

    def __init__(self, url: str, status: int, parser: SeoHtmlParser | None, redirect_chain: list[str], fetch_ms: int) -> None:
        self.url = url
        self.status = status
        self.title = parser.title if parser else ""
        self.description = parser.description if parser else ""
        self.h1 = parser.h1[0] if parser and parser.h1 else ""
        self.links = [href for href, rel, _ in (parser.links if parser else [])]
        self.nofollow_links = [href for href, rel, _ in (parser.links if parser else []) if "nofollow" in rel.lower()]
        self.redirect_chain = redirect_chain
        self.fetch_ms = fetch_ms


def _normalize(url: str) -> str:
    return urldefrag(url)[0].rstrip("/") or url


def _same_origin(url: str, origin: str) -> bool:
    return urlsplit(url).netloc == urlsplit(origin).netloc


async def _rendered_links(url: str, browser_pool: BrowserPoolBoundary) -> list[tuple[str, bool]]:
    """Extract anchor hrefs from the rendered DOM using headless Chromium."""
    async with browser_pool.page() as page:
        await browser_pool.goto(page, url, wait_until="networkidle", timeout=30000)
        facts = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => ({href: e.href, nofollow: (e.rel || '').toLowerCase().includes('nofollow')}))",
        )
        return [(item["href"], bool(item["nofollow"])) for item in facts]


async def _crawl_site_async(
    start_url: str,
    *,
    max_pages: int = 25,
    timeout: float = 5.0,
    verify: bool = True,
    allow_private: bool = True,
    render: bool = False,
) -> list[CrawledPage]:
    """Breadth-first crawl of same-origin pages starting at ``start_url``."""
    origin = urlsplit(start_url).scheme + "://" + urlsplit(start_url).netloc
    queue: list[str] = [_normalize(start_url)]
    seen: set[str] = set(queue)
    pages: list[CrawledPage] = []
    logger.info("SEO crawl started: origin=%s max_pages=%d render=%s", origin, max_pages, render)
    browser_pool: BrowserPoolBoundary | None = None
    if render:
        browser_pool = BrowserPool(EgressPolicy(block_private=not allow_private, max_response_bytes=MAX_HTML_BYTES))
        try:
            await browser_pool.start()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Rendered link extraction unavailable: %s", exc)
            await browser_pool.close()
            browser_pool = None
    try:
        with HttpClient(timeout=timeout, verify=verify, allow_private=allow_private) as client:
            while queue and len(pages) < max_pages:
                current = queue.pop(0)
                started = time.perf_counter()
                try:
                    response = client.get(current)
                except FetchError as exc:
                    logger.debug("Crawl fetch failed: url=%s error=%s", current, exc)
                    pages.append(CrawledPage(current, 0, None, [], round((time.perf_counter() - started) * 1000)))
                    continue
                fetch_ms = round((time.perf_counter() - started) * 1000)
                parser = None
                if response.status_code == 200 and response.content_type in {"text/html", "application/xhtml+xml"}:
                    parser = SeoHtmlParser()
                    parser.feed(response.text)
                    parser.close()
                page = CrawledPage(response.url, response.status_code, parser, response.redirected_from, fetch_ms)
                pages.append(page)
                hrefs = page.links
                if render and not hrefs and browser_pool is not None:
                    try:
                        rendered_links = await _rendered_links(current, browser_pool)
                        hrefs = [href for href, _ in rendered_links]
                        page.links = hrefs
                        page.nofollow_links = [href for href, nofollow in rendered_links if nofollow]
                        logger.debug("Rendered link extraction: url=%s links=%d", current, len(hrefs))
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("Rendered link extraction failed: url=%s error=%s", current, exc)
                for href in hrefs:
                    absolute = _normalize(urljoin(current, href))
                    if absolute.startswith(origin) and _same_origin(absolute, origin) and absolute not in seen:
                        seen.add(absolute)
                        queue.append(absolute)
    finally:
        if browser_pool is not None:
            await browser_pool.close()
    logger.info("SEO crawl finished: pages=%d queue_left=%d", len(pages), len(queue))
    return pages


def crawl_site(
    start_url: str,
    *,
    max_pages: int = 25,
    timeout: float = 5.0,
    verify: bool = True,
    allow_private: bool = True,
    render: bool = False,
) -> list[CrawledPage]:
    """Breadth-first crawl of same-origin pages starting at ``start_url``."""
    return asyncio.run(_crawl_site_async(
        start_url,
        max_pages=max_pages,
        timeout=timeout,
        verify=verify,
        allow_private=allow_private,
        render=render,
    ))


def _result(
    check_id: str,
    title: str,
    category: str,
    status: str,
    scored: bool,
    details: str,
    started: float,
    evidence: list[Evidence],
    remediation: Remediation | None = None,
) -> SeoCheckResult:
    return SeoCheckResult(
        id=check_id,
        title=title,
        category=category,
        status=status,  # type: ignore[arg-type]
        scored=scored,
        details=details,
        duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
        evidence=evidence,
        remediation=remediation,
    )


def _add_crawl_metrics(evidence: list[Evidence], **metrics: object) -> list[Evidence]:
    if evidence:
        evidence[0].metrics.update(metrics)
    else:
        evidence.append(Evidence(action="inspect insecure links across crawled pages", metrics=metrics))
    return evidence


def check_broken_links(pages: list[CrawledPage], start_url: str) -> SeoCheckResult:
    started = time.perf_counter()
    broken = [
        page
        for page in pages
        if (getattr(page, "status_code", getattr(page, "status", None)) in {None, 0})
        or getattr(page, "status_code", getattr(page, "status", None)) >= 400
    ]
    ok = not broken
    detail = f"all {len(pages)} crawled pages are reachable" if ok else f"{len(broken)} broken page(s): " + ", ".join(f"{p.url} (HTTP {getattr(p, 'status_code', getattr(p, 'status', None)) or 'fetch error'})" for p in broken[:5])
    evidence = [Evidence(action="crawl same-origin pages", url=p.url, status_code=getattr(p, "status_code", getattr(p, "status", None)), finding=f"HTTP {getattr(p, 'status_code', getattr(p, 'status', None))}") for p in broken[:5]]
    remediation = Remediation(
        summary="Fix or remove links to pages returning 4xx/5xx so crawlers do not hit dead ends.",
        rerun_command=f"agentready audit {start_url!r} --mode seo --crawl",
        references=[_GOOGLE_LINKS],
    ) if not ok else None
    return _result("broken-links", "Broken internal links", "crawlability", "pass" if ok else "fail", True, detail, started, evidence, remediation)


def check_redirect_chains(pages: list[CrawledPage], start_url: str) -> SeoCheckResult:
    started = time.perf_counter()
    chained = [page for page in pages if len(getattr(page, "redirect_records", getattr(page, "redirect_chain", ()))) > 1]
    ok = not chained
    detail = "no multi-hop redirect chains" if ok else f"{len(chained)} page(s) reached via redirect chains: " + ", ".join(p.url for p in chained[:5])
    evidence = [Evidence(action="follow redirects", url=p.url, finding=f"{len(getattr(p, 'redirect_records', getattr(p, 'redirect_chain', ())))} redirect hop(s)") for p in chained[:5]]
    remediation = Remediation(
        summary="Point links directly at final URLs; multi-hop redirect chains waste crawl budget and dilute signals.",
        rerun_command=f"agentready audit {start_url!r} --mode seo --crawl",
        references=[_GOOGLE_REDIRECTS],
    ) if not ok else None
    return _result("redirect-chains", "Redirect chains", "crawlability", "pass" if ok else "warn", True, detail, started, evidence, remediation)


def check_duplicate_metadata(pages: list[CrawledPage], start_url: str) -> SeoCheckResult:
    started = time.perf_counter()
    titles: dict[str, list[str]] = {}
    descriptions: dict[str, list[str]] = {}
    for page in pages:
        if page.status != 200:
            continue
        if page.title:
            titles.setdefault(page.title.strip().lower(), []).append(page.url)
        if page.description:
            descriptions.setdefault(page.description.strip().lower(), []).append(page.url)
    dup_titles = {key: urls for key, urls in titles.items() if len(urls) > 1}
    dup_descriptions = {key: urls for key, urls in descriptions.items() if len(urls) > 1}
    issues = []
    if dup_titles:
        issues.append(f"{len(dup_titles)} duplicate title(s) across pages")
    if dup_descriptions:
        issues.append(f"{len(dup_descriptions)} duplicate meta description(s) across pages")
    ok = not issues
    detail = "titles and descriptions are unique across crawled pages" if ok else "; ".join(issues)
    evidence = [Evidence(action="compare page metadata", url=urls[0], finding=f"shared by {len(urls)} pages") for urls in list(dup_titles.values())[:5]]
    remediation = Remediation(
        summary="Give every indexable page a unique title and meta description so pages do not compete with each other.",
        rerun_command=f"agentready audit {start_url!r} --mode seo --crawl",
        references=[_GOOGLE_DUPLICATES],
    ) if not ok else None
    return _result("duplicate-metadata", "Duplicate metadata across pages", "metadata", "pass" if ok else "fail", True, detail, started, evidence, remediation)


def check_internal_nofollow(pages: list[CrawledPage], start_url: str) -> SeoCheckResult:
    started = time.perf_counter()
    flagged = [(page.url, len(getattr(page, "nofollow_links", ()))) for page in pages if getattr(page, "nofollow_links", ())]
    ok = not flagged
    detail = "no internal nofollow links" if ok else f"{sum(count for _, count in flagged)} internal nofollow link(s) on {len(flagged)} page(s)"
    evidence = [Evidence(action="inspect link rel attributes", url=url, finding=f"{count} nofollow internal link(s)") for url, count in flagged[:5]]
    remediation = Remediation(
        summary="Remove rel=nofollow from internal links unless there is a deliberate crawl-policy reason.",
        rerun_command=f"agentready audit {start_url!r} --mode seo --crawl",
        references=[_GOOGLE_LINKS],
    ) if not ok else None
    return _result("internal-nofollow", "Internal nofollow links", "crawlability", "pass" if ok else "warn", True, detail, started, evidence, remediation)


def check_link_counts(pages: list[CrawledPage], start_url: str) -> SeoCheckResult:
    started = time.perf_counter()
    threshold = 150
    heavy = [(page.url, len(page.links)) for page in pages if len(page.links) > threshold]
    ok = not heavy
    detail = f"no page exceeds {threshold} links" if ok else f"{len(heavy)} page(s) with many links: " + ", ".join(f"{url} ({count})" for url, count in heavy[:5])
    evidence = [Evidence(action="count page links", url=url, finding=f"{count} links") for url, count in heavy[:5]]
    remediation = Remediation(
        summary="Split pages with excessive link counts; very long link lists dilute each link's value and usability.",
        rerun_command=f"agentready audit {start_url!r} --mode seo --crawl",
        references=[_GOOGLE_LINKS],
    ) if not ok else None
    return _result("link-counts", "Excessive link counts", "crawlability", "pass" if ok else "warn", True, detail, started, evidence, remediation)


def check_insecure_links_pages(pages: list[CrawledPage], start_url: str) -> SeoCheckResult:
    """Find HTTPS pages in the crawl that link to HTTP targets."""
    started = time.perf_counter()
    affected: list[tuple[CrawledPage, list[str]]] = []
    total_links = 0
    for page in pages:
        if not page.url.startswith("https://") or page.status != 200:
            continue
        insecure = [href for href in page.links if href.startswith("http://")]
        total_links += len(page.links)
        if insecure:
            affected.append((page, insecure))

    insecure_count = sum(len(links) for _, links in affected)
    evidence = [
        Evidence(
            action="inspect insecure links across crawled pages",
            url=page.url,
            finding=f"{len(links)} HTTP link(s) on crawled page",
            metrics={
                "page": page.url,
                "link_count": len(page.links),
                "insecure_count": len(links),
                "insecure_links": [{"url": urljoin(page.url, href)} for href in links],
            },
        )
        for page, links in affected
    ]
    ok = not affected
    detail = (
        f"no insecure HTTP links across {len(pages)} crawled pages"
        if ok
        else f"{len(affected)} page(s) with insecure HTTP links: "
        + ", ".join(f"{page.url} ({len(links)})" for page, links in affected[:5])
    )
    evidence = _add_crawl_metrics(
        evidence,
        page_count=len(pages),
        affected_page_count=len(affected),
        link_count=total_links,
        insecure_count=insecure_count,
    )
    remediation = Remediation(
        summary="Update HTTP links on every affected crawled page to their HTTPS versions.",
        rerun_command=f"agentready audit {start_url!r} --mode seo --crawl",
        references=[_GOOGLE_LINKS],
    ) if not ok else None
    return _result("insecure-links-pages", "HTTPS to HTTP links across crawled pages", "technical", "pass" if ok else "warn", True, detail, started, evidence, remediation)


CRAWL_CHECKS = (
    check_broken_links,
    check_redirect_chains,
    check_duplicate_metadata,
    check_internal_nofollow,
    check_link_counts,
    check_insecure_links_pages,
)

CRAWL_CHECKS_BY_ID = {
    "broken-links": check_broken_links,
    "redirect-chains": check_redirect_chains,
    "duplicate-metadata": check_duplicate_metadata,
    "internal-nofollow": check_internal_nofollow,
    "link-counts": check_link_counts,
    "insecure-links-pages": check_insecure_links_pages,
}

CRAWL_CHECK_METADATA = (
    {
        "id": "broken-links",
        "title": {"en": "Broken internal links", "ru": "Битые внутренние ссылки"},
        "category": {"en": "Crawlability", "ru": "Обход краулерами"},
        "description": {
            "en": "Crawls same-origin pages and reports links leading to 4xx/5xx or unreachable URLs.",
            "ru": "Обходит страницы сайта и сообщает о ссылках, ведущих на 4xx/5xx или недоступные URL.",
        },
    },
    {
        "id": "redirect-chains",
        "title": {"en": "Redirect chains", "ru": "Цепочки редиректов"},
        "category": {"en": "Crawlability", "ru": "Обход краулерами"},
        "description": {
            "en": "Detects pages reached through multi-hop redirect chains during the crawl.",
            "ru": "Обнаруживает страницы, достигаемые через цепочки из нескольких редиректов.",
        },
    },
    {
        "id": "duplicate-metadata",
        "title": {"en": "Duplicate metadata across pages", "ru": "Дубли метаданных между страницами"},
        "category": {"en": "Metadata", "ru": "Метаданные"},
        "description": {
            "en": "Detects identical titles or meta descriptions shared by multiple crawled pages.",
            "ru": "Обнаруживает одинаковые title или meta description у нескольких страниц.",
        },
    },
    {
        "id": "internal-nofollow",
        "title": {"en": "Internal nofollow links", "ru": "Внутренние nofollow-ссылки"},
        "category": {"en": "Crawlability", "ru": "Обход краулерами"},
        "description": {
            "en": "Detects internal links with rel=nofollow that waste crawl signals.",
            "ru": "Обнаруживает внутренние ссылки с rel=nofollow, ослабляющие сигналы обхода.",
        },
    },
    {
        "id": "link-counts",
        "title": {"en": "Excessive link counts", "ru": "Избыточное число ссылок"},
        "category": {"en": "Crawlability", "ru": "Обход краулерами"},
        "description": {
            "en": "Flags pages with very large numbers of outgoing links.",
            "ru": "Отмечает страницы с чрезмерным количеством исходящих ссылок.",
        },
    },
    {
        "id": "insecure-links-pages",
        "title": {
            "en": "HTTPS to HTTP links across crawled pages",
            "ru": "Ссылки HTTPS → HTTP на обойдённых страницах",
        },
        "category": {"en": "Technical availability", "ru": "Техническая доступность"},
        "description": {
            "en": "When crawling is enabled, checks every crawled HTTPS page for links to HTTP targets and lists affected page URLs.",
            "ru": "При включённом обходе проверяет каждую страницу HTTPS на ссылки к HTTP и показывает URL проблемных страниц.",
        },
    },
)
