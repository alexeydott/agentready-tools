"""Mobile v2 projection over facts collected by ``AuditService``."""
from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any, Protocol

from .browser_pool import BrowserPoolBoundary
from .mobile_models import MobileCheckResult, MobilePageReport, MobileReport
from .mobile_render import MOBILE_RENDER_CHECKS, audit_rendered_mobile_page
from .mobile_scoring import rank_mobile_recommendations, score_mobile_checks
from .models import utc_now_iso
from .target import ensure_public_url, parse_target

logger = logging.getLogger(__name__)

MOBILE_SCHEMA = "agentready.mobile.v2"

MobileCheck = type(MOBILE_RENDER_CHECKS[0]) if MOBILE_RENDER_CHECKS else object


class MobileReplayClient(Protocol):
    """Analyzer-only view of the collected HTTP representation."""

    def get(self, url: str, headers: dict[str, str] | None = None, *, use_cache: bool = True) -> Any:
        ...


async def _audit_page(
    url: str,
    *,
    render: bool,
    allow_private: bool,
    recommendation_limit: int,
    browser_pool: BrowserPoolBoundary | None = None,
    render_status: str | None = None,
    client: MobileReplayClient | None = None,
) -> MobilePageReport:
    from .mobile_checks import MOBILE_STATIC_CHECKS

    target = parse_target(url)
    if not allow_private:
        ensure_public_url(target.url)
    started = utc_now_iso()
    logger.info("Mobile audit started: url=%s render=%s", target.url, render)
    started_perf = time.perf_counter()
    checks: list[MobileCheckResult] = []
    if client is None:
        raise RuntimeError("mobile analysis requires AuditService collected facts")
    checks.extend(check(target.url, client) for check in MOBILE_STATIC_CHECKS)
    if render:
        if render_status is not None:
            rendered_checks = [
                MobileCheckResult(
                    id=check.__name__.replace("check_", "").replace("_async", "").replace("_", "-"),
                    title=check.__name__.replace("check_", "").replace("_async", "").replace("_", " ").title(),
                    category="layout",
                    status="skip" if render_status == "playwright not installed" else "error",
                    scored=render_status != "playwright not installed",
                    details=render_status,
                    duration_ms=0,
                )
                for check in MOBILE_RENDER_CHECKS
            ]
        elif browser_pool is None:
            raise RuntimeError("rendered mobile checks require a BrowserPool")
        else:
            rendered_checks = await _run_render_checks(target.url, browser_pool)
        checks.extend(rendered_checks)
    score, categories = score_mobile_checks(checks)
    recommendations = rank_mobile_recommendations(checks, limit=recommendation_limit)
    report = MobilePageReport(
        url=target.url,
        rendered=render,
        checks=checks,
        score=score,
        categories=categories,
        recommendations=recommendations,
        started_at=started,
        finished_at=utc_now_iso(),
    )
    logger.info(
        "Mobile audit page finished: url=%s score=%d checks=%d duration_ms=%d",
        target.url, score, len(checks), round((time.perf_counter() - started_perf) * 1000),
    )
    return report


async def _run_render_checks(url: str, browser_pool: BrowserPoolBoundary) -> list[MobileCheckResult]:
    try:
        return await audit_rendered_mobile_page(url, browser_pool)
    except Exception as exc:  # noqa: BLE001
        logger.error("[FIX:mobile-browser-replay] rendered collection failed url=%s error=%s", url, exc)
        return [
                MobileCheckResult(
                    id=check.__name__.replace("check_", "").replace("_async", "").replace("_", "-"),
                    title=check.__name__.replace("check_", "").replace("_async", "").replace("_", " ").title(),
                    category="layout",
                    status="error",
                    scored=True,
                    details=str(exc),
                    duration_ms=0,
                )
            for check in MOBILE_RENDER_CHECKS
        ]


def audit_mobile(
    urls: Sequence[str],
    *,
    render: bool = False,
    timeout: float = 5.0,
    verify: bool = True,
    allow_private: bool = True,
    max_redirects: int = 5,
    max_bytes: int = 5 * 1024 * 1024,
    recommendation_limit: int = 10,
    language: str = "en",
    transport: Any | None = None,
) -> MobileReport:
    from .audit_service import AuditRequest, AuditService

    if not urls:
        raise ValueError("at least one mobile audit target is required")
    targets = [parse_target(url).url for url in urls]
    if not allow_private:
        for target in targets:
            ensure_public_url(target)
    logger.info("Mobile audit started: urls=%d render=%s", len(urls), render)
    started_at = utc_now_iso()
    pages = []
    service = AuditService()
    for target in targets:
        result = service.run(
            AuditRequest(
                target=target,
                mode="mobile",
                profile="quick",
                max_pages=1,
                timeout=timeout,
                render=render,
                language=language,
                allow_private=allow_private,
                recommendation_limit=recommendation_limit,
                verify=verify,
                max_redirects=max_redirects,
                max_bytes=max_bytes,
                transport=transport,
            )
        )
        if result.mobile_report is None:
            raise RuntimeError("AuditService returned no mobile projection")
        pages.extend(result.mobile_report.pages)
    all_checks = [check for page in pages for check in page.checks]
    score, categories = score_mobile_checks(all_checks)
    recommendations = rank_mobile_recommendations(all_checks, limit=recommendation_limit)
    report = MobileReport(
        schema=MOBILE_SCHEMA,
        targets=targets,
        pages=pages,
        score=score,
        categories=categories,
        recommendations=recommendations,
        started_at=started_at,
        finished_at=utc_now_iso(),
        language=language,
    )
    logger.info("[FIX:mobile-collection] mobile adapter delegated pages=%d", len(pages))
    logger.info("Mobile audit finished: urls=%d aggregate_score=%d", len(urls), report.score)
    return report
