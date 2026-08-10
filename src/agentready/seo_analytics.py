"""Analytics-based SEO checks (GA4 + Search Console).

These checks need Google service-account credentials and the GA4 property /
Search Console site identifiers. They are not part of the default SEO check
set: ``audit_seo`` appends them only when the caller provides the identifiers.
Without credentials they return ``skip`` results explaining what is missing.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlsplit

from .models import Evidence, Remediation
from .seo_models import SeoCheckResult

logger = logging.getLogger(__name__)

_GA4_DOCS = "https://developers.google.com/analytics/devguides/reporting/data/v1"
_GSC_DOCS = "https://developers.google.com/webmaster-tools/v1/searchanalytics/query"

BOUNCE_RATE_THRESHOLD = 0.9


class AnalyticsContext:
    """Identifiers required to query GA4 / Search Console."""

    __slots__ = ("ga_property", "gsc_site")

    def __init__(self, ga_property: str | None = None, gsc_site: str | None = None) -> None:
        self.ga_property = ga_property
        self.gsc_site = gsc_site

    @property
    def has_ga(self) -> bool:
        return bool(self.ga_property)

    @property
    def has_gsc(self) -> bool:
        return bool(self.gsc_site)


def _result(
    check_id: str,
    title: str,
    status: str,
    details: str,
    started: float,
    evidence: list[Evidence] | None = None,
    remediation: Remediation | None = None,
) -> SeoCheckResult:
    return SeoCheckResult(
        id=check_id,
        title=title,
        category="analytics",
        status=status,  # type: ignore[arg-type]
        scored=True,
        details=details,
        duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
        evidence=evidence or [],
        remediation=remediation,
    )


def _skip(check_id: str, title: str, reason: str, started: float) -> SeoCheckResult:
    return SeoCheckResult(
        id=check_id,
        title=title,
        category="analytics",
        status="skip",
        scored=False,
        details=reason,
        duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
    )


def _page_path(url: str) -> str:
    return urlsplit(url).path or "/"


def check_ga_no_traffic(url: str, ctx: AnalyticsContext) -> SeoCheckResult:
    started = time.perf_counter()
    if not ctx.has_ga:
        return _skip("ga-no-traffic", "GA: page without traffic", "GA4 property not configured", started)
    from .ga_gsc import ga_bounce_rate

    value = ga_bounce_rate(ctx.ga_property or "", _page_path(url))
    if value is None:
        detail = "no GA4 sessions recorded for this page in the last 28 days"
        remediation = Remediation(
            summary="The page gets no measured traffic; review its value, internal linking and indexability.",
            rerun_command=f"agentready seo audit {url!r} --ga-property {ctx.ga_property}",
            references=[_GA4_DOCS],
        )
        return _result("ga-no-traffic", "GA: page without traffic", "fail", detail, started, remediation=remediation)
    return _result("ga-no-traffic", "GA: page without traffic", "pass", "page has recorded GA4 sessions", started)


def check_ga_bounce_rate(url: str, ctx: AnalyticsContext) -> SeoCheckResult:
    started = time.perf_counter()
    if not ctx.has_ga:
        return _skip("ga-bounce-rate", "GA: bounce rate", "GA4 property not configured", started)
    from .ga_gsc import ga_bounce_rate

    value = ga_bounce_rate(ctx.ga_property or "", _page_path(url))
    if value is None:
        return _skip("ga-bounce-rate", "GA: bounce rate", "no GA4 data for this page", started)
    ok = value <= BOUNCE_RATE_THRESHOLD
    detail = f"GA4 bounce rate is {value:.0%}" + ("" if ok else f" (above {BOUNCE_RATE_THRESHOLD:.0%})")
    remediation = Remediation(
        summary="Investigate why most visits bounce: content-intent mismatch, slow load, or weak internal linking.",
        rerun_command=f"agentready seo audit {url!r} --ga-property {ctx.ga_property}",
        references=[_GA4_DOCS],
    ) if not ok else None
    return _result("ga-bounce-rate", "GA: bounce rate", "pass" if ok else "warn", detail, started, remediation=remediation)


def check_gsc_no_clicks(url: str, ctx: AnalyticsContext) -> SeoCheckResult:
    started = time.perf_counter()
    if not ctx.has_gsc:
        return _skip("gsc-no-clicks", "GSC: page without clicks", "Search Console site not configured", started)
    from .ga_gsc import gsc_pages_without_clicks

    rows = gsc_pages_without_clicks(ctx.gsc_site or "")
    page_hits = [row for row in rows if row["page"].rstrip("/") == url.rstrip("/")]
    evidence = [Evidence(action="query Search Console", url=url, finding=f"impressions={row['impressions']}, clicks=0") for row in page_hits[:3]]
    ok = not page_hits
    detail = "page has recorded clicks in Search Console" if ok else f"page has impressions but zero clicks ({page_hits[0]['impressions']} impressions)"
    remediation = Remediation(
        summary="Improve the snippet (title/description) and ranking for queries that show impressions but no clicks.",
        rerun_command=f"agentready seo audit {url!r} --gsc-site {ctx.gsc_site}",
        references=[_GSC_DOCS],
    ) if not ok else None
    return _result("gsc-no-clicks", "GSC: page without clicks", "pass" if ok else "fail", detail, started, evidence, remediation)


def check_gsc_no_impressions(url: str, ctx: AnalyticsContext) -> SeoCheckResult:
    started = time.perf_counter()
    if not ctx.has_gsc:
        return _skip("gsc-no-impressions", "GSC: page without impressions", "Search Console site not configured", started)
    from .ga_gsc import gsc_pages_without_impressions

    known_pages = gsc_pages_without_impressions(ctx.gsc_site or "")
    ok = any(page.rstrip("/") == url.rstrip("/") for page in known_pages)
    detail = "page has impressions in Search Console" if ok else "page has no impressions in the last 28 days"
    remediation = Remediation(
        summary="The page is invisible in search; check indexability, internal links and sitemap coverage.",
        rerun_command=f"agentready seo audit {url!r} --gsc-site {ctx.gsc_site}",
        references=[_GSC_DOCS],
    ) if not ok else None
    return _result("gsc-no-impressions", "GSC: page without impressions", "pass" if ok else "fail", detail, started, remediation=remediation)


def check_ga_nonindexed_traffic(url: str, ctx: AnalyticsContext) -> SeoCheckResult:
    """GA: traffic to a page marked noindex (combined signal)."""
    started = time.perf_counter()
    if not ctx.has_ga:
        return _skip("ga-nonindexed-traffic", "GA: non-indexable page with traffic", "GA4 property not configured", started)
    from .ga_gsc import ga_bounce_rate
    from .seo_checks import check_indexability
    from .http import HttpClient

    with HttpClient() as client:
        indexability = check_indexability(url, client)
    if indexability.status == "pass":
        return _result("ga-nonindexed-traffic", "GA: non-indexable page with traffic", "pass", "page is indexable", started)
    has_traffic = ga_bounce_rate(ctx.ga_property or "", _page_path(url)) is not None
    ok = not has_traffic
    detail = "page is not indexable" + (" but still receives traffic" if has_traffic else " and receives no traffic")
    remediation = Remediation(
        summary="Decide deliberately: index the page or keep it hidden; traffic to a noindex page signals mixed intent.",
        rerun_command=f"agentready seo audit {url!r} --ga-property {ctx.ga_property}",
        references=[_GA4_DOCS],
    ) if not ok else None
    return _result("ga-nonindexed-traffic", "GA: non-indexable page with traffic", "pass" if ok else "warn", detail, started, remediation=remediation)


def check_gsc_nonindexed_impressions(url: str, ctx: AnalyticsContext) -> SeoCheckResult:
    """GSC: impressions for a page marked noindex (combined signal)."""
    started = time.perf_counter()
    if not ctx.has_gsc:
        return _skip("gsc-nonindexed-impressions", "GSC: non-indexable page with impressions", "Search Console site not configured", started)
    from .ga_gsc import gsc_pages_without_clicks
    from .seo_checks import check_indexability
    from .http import HttpClient

    with HttpClient() as client:
        indexability = check_indexability(url, client)
    if indexability.status == "pass":
        return _result("gsc-nonindexed-impressions", "GSC: non-indexable page with impressions", "pass", "page is indexable", started)
    rows = gsc_pages_without_clicks(ctx.gsc_site or "")
    has_impressions = any(row["page"].rstrip("/") == url.rstrip("/") for row in rows)
    ok = not has_impressions
    detail = "page is not indexable" + (" but still receives impressions" if has_impressions else " and has no impressions")
    remediation = Remediation(
        summary="A noindex page still earns impressions; align the indexing directive with the intended visibility.",
        rerun_command=f"agentready seo audit {url!r} --gsc-site {ctx.gsc_site}",
        references=[_GSC_DOCS],
    ) if not ok else None
    return _result("gsc-nonindexed-impressions", "GSC: non-indexable page with impressions", "pass" if ok else "warn", detail, started, remediation=remediation)


ANALYTICS_CHECKS = (
    check_ga_no_traffic,
    check_ga_bounce_rate,
    check_ga_nonindexed_traffic,
    check_gsc_no_clicks,
    check_gsc_no_impressions,
    check_gsc_nonindexed_impressions,
)

ANALYTICS_CHECK_METADATA = (
    {
        "id": "ga-no-traffic",
        "title": {"en": "GA: page without traffic", "ru": "GA: страница без трафика"},
        "category": {"en": "Analytics", "ru": "Аналитика"},
        "description": {
            "en": "Detects pages with no GA4 sessions in the last 28 days. Requires GA4 property and credentials.",
            "ru": "Обнаруживает страницы без сеансов GA4 за последние 28 дней. Требует GA4 property и credentials.",
        },
    },
    {
        "id": "ga-bounce-rate",
        "title": {"en": "GA: bounce rate", "ru": "GA: показатель отказов"},
        "category": {"en": "Analytics", "ru": "Аналитика"},
        "description": {
            "en": "Flags pages whose GA4 bounce rate exceeds 90%. Requires GA4 property and credentials.",
            "ru": "Отмечает страницы с показателем отказов GA4 выше 90%. Требует GA4 property и credentials.",
        },
    },
    {
        "id": "ga-nonindexed-traffic",
        "title": {"en": "GA: non-indexable page with traffic", "ru": "GA: неиндексируемая страница с трафиком"},
        "category": {"en": "Analytics", "ru": "Аналитика"},
        "description": {
            "en": "Detects traffic to pages marked noindex — a mixed-intent signal. Requires GA4 property.",
            "ru": "Обнаруживает трафик на страницы с noindex — сигнал смешанных намерений. Требует GA4 property.",
        },
    },
    {
        "id": "gsc-no-clicks",
        "title": {"en": "GSC: page without clicks", "ru": "GSC: страница без кликов"},
        "category": {"en": "Analytics", "ru": "Аналитика"},
        "description": {
            "en": "Detects pages with impressions but zero clicks. Requires Search Console site and credentials.",
            "ru": "Обнаруживает страницы с показами, но без кликов. Требует сайт Search Console и credentials.",
        },
    },
    {
        "id": "gsc-no-impressions",
        "title": {"en": "GSC: page without impressions", "ru": "GSC: страница без показов"},
        "category": {"en": "Analytics", "ru": "Аналитика"},
        "description": {
            "en": "Detects pages with no impressions in the last 28 days. Requires Search Console site and credentials.",
            "ru": "Обнаруживает страницы без показов за последние 28 дней. Требует сайт Search Console и credentials.",
        },
    },
    {
        "id": "gsc-nonindexed-impressions",
        "title": {"en": "GSC: non-indexable page with impressions", "ru": "GSC: неиндексируемая страница с показами"},
        "category": {"en": "Analytics", "ru": "Аналитика"},
        "description": {
            "en": "Detects impressions for pages marked noindex. Requires Search Console site and credentials.",
            "ru": "Обнаруживает показы у страниц с noindex. Требует сайт Search Console и credentials.",
        },
    },
)
