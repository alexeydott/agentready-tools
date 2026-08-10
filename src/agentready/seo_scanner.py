from __future__ import annotations

import logging
import json
import time
from collections.abc import Callable, Sequence

from .http import HttpClient
from .seo_models import SeoCheckResult, SeoReport
from .seo_recommendations import rank_recommendations
from .seo_scoring import score_checks
from .target import ensure_public_url, parse_target
from .models import utc_now_iso

logger = logging.getLogger(__name__)

SeoCheck = Callable[[str, HttpClient], SeoCheckResult]


def compare_seo_baseline(report: SeoReport, path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        baseline = json.load(handle)
    if baseline.get("schema") != "agentready.seo.v1":
        raise ValueError("baseline is not an agentready.seo.v1 SEO report")
    warnings: list[str] = []
    if isinstance(baseline.get("score"), int) and report.score < baseline["score"]:
        warnings.append(f"SEO score regressed from {baseline['score']} to {report.score}")
    old = {item.get("id"): item.get("status") for item in baseline.get("checks", []) if isinstance(item, dict)}
    for check in report.checks:
        if old.get(check.id) == "pass" and check.status in {"fail", "error"}:
            warnings.append(f"SEO check regressed: {check.id}")
    return warnings


def audit_seo(
    url: str,
    *,
    checks: Sequence[SeoCheck] | None = None,
    timeout: float = 5.0,
    verify: bool = True,
    allow_private: bool = True,
    max_redirects: int = 5,
    max_bytes: int = 5 * 1024 * 1024,
    recommendation_limit: int = 10,
    language: str = "en",
    crawl: bool = False,
    max_pages: int = 25,
    render: bool = False,
    crawl_checks: Sequence | None = None,
    ga_property: str | None = None,
    gsc_site: str | None = None,
) -> SeoReport:
    target = parse_target(url)
    if not allow_private:
        ensure_public_url(target.url)
    started = utc_now_iso()
    if checks is None:
        from .seo_checks import SEO_CHECKS

        checks = SEO_CHECKS
    logger.info("SEO audit started: origin=%s checks=%d crawl=%s", target.origin, len(checks), crawl)
    started_perf = time.perf_counter()
    with HttpClient(
        timeout=timeout,
        verify=verify,
        allow_private=allow_private,
        max_redirects=max_redirects,
        max_bytes=max_bytes,
    ) as client:
        results = [check(target.url, client) for check in checks]
    if crawl:
        from .seo_crawler import CRAWL_CHECKS, crawl_site

        pages = crawl_site(
            target.url,
            max_pages=max_pages,
            timeout=timeout,
            verify=verify,
            allow_private=allow_private,
            render=render,
        )
        selected_crawl = CRAWL_CHECKS if crawl_checks is None else crawl_checks
        results.extend(check(pages, target.url) for check in selected_crawl)
    if ga_property or gsc_site:
        from .seo_analytics import ANALYTICS_CHECKS, AnalyticsContext

        context = AnalyticsContext(ga_property=ga_property, gsc_site=gsc_site)
        for check in ANALYTICS_CHECKS:
            try:
                results.append(check(target.url, context))
            except Exception as exc:  # noqa: BLE001
                logger.error("Analytics check failed: check=%s error=%s", check.__name__, exc)
                results.append(
                    SeoCheckResult(
                        id=check.__name__.replace("check_", "").replace("_", "-"),
                        title=check.__name__.replace("check_", "").replace("_", " ").title(),
                        category="analytics",
                        status="error",
                        scored=True,
                        details=str(exc),
                    )
                )
    score, categories = score_checks(results)
    recommendations = rank_recommendations(results, limit=recommendation_limit)
    report = SeoReport(
        schema="agentready.seo.v1",
        target=target.url,
        origin=target.origin,
        checks=results,
        score=score,
        categories=categories,
        recommendations=recommendations,
        started_at=started,
        finished_at=utc_now_iso(),
        language=language,
    )
    logger.info(
        "SEO audit finished: origin=%s score=%d checks=%d duration_ms=%d",
        target.origin, score, len(results), round((time.perf_counter() - started_perf) * 1000),
    )
    return report
