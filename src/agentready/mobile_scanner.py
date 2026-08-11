"""Orchestration for multi-page mobile-friendliness audits."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence

from .browser_pool import BrowserPool, BrowserPoolBoundary, CapabilityUnavailableError
from .egress import EgressPolicy
from .http import HttpClient
from .mobile_models import MobileCheckResult, MobilePageReport, MobileReport
from .mobile_render import MOBILE_RENDER_CHECKS
from .mobile_scoring import rank_mobile_recommendations, score_mobile_checks
from .models import utc_now_iso
from .target import ensure_public_url, parse_target

logger = logging.getLogger(__name__)

MobileCheck = type(MOBILE_RENDER_CHECKS[0]) if MOBILE_RENDER_CHECKS else object


async def _audit_page(
    url: str,
    *,
    render: bool,
    timeout: float,
    verify: bool,
    allow_private: bool,
    max_redirects: int,
    max_bytes: int,
    recommendation_limit: int,
    browser_pool: BrowserPoolBoundary | None = None,
    render_status: str | None = None,
) -> MobilePageReport:
    from .mobile_checks import MOBILE_STATIC_CHECKS

    target = parse_target(url)
    if not allow_private:
        ensure_public_url(target.url)
    started = utc_now_iso()
    logger.info("Mobile audit started: url=%s render=%s", target.url, render)
    started_perf = time.perf_counter()
    checks: list[MobileCheckResult] = []
    with HttpClient(
        timeout=timeout,
        verify=verify,
        allow_private=allow_private,
        max_redirects=max_redirects,
        max_bytes=max_bytes,
    ) as client:
        checks.extend(check(target.url, client) for check in MOBILE_STATIC_CHECKS)
    if render:
        if render_status is not None:
            rendered_checks = [
                MobileCheckResult(
                    id=check.__name__.replace("check_", "").replace("_async", "").replace("_", "-"),
                    title=check.__name__.replace("check_", "").replace("_async", "").replace("_", " ").title(),
                    category="layout",
                    status="skip" if render_status == "playwright not installed" else "error",
                    scored=False if render_status == "playwright not installed" else True,
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
    results: list[MobileCheckResult] = []
    for check in MOBILE_RENDER_CHECKS:
        try:
            results.append(await check(url, browser_pool))
        except Exception as exc:  # noqa: BLE001
            logger.error("Rendered mobile check failed: check=%s error=%s", check.__name__, exc)
            results.append(
                MobileCheckResult(
                    id=check.__name__.replace("check_", "").replace("_async", "").replace("_", "-"),
                    title=check.__name__.replace("check_", "").replace("_async", "").replace("_", " ").title(),
                    category="layout",
                    status="error",
                    scored=True,
                    details=str(exc),
                    duration_ms=0,
                )
            )


async def _audit_mobile_async(
    urls: Sequence[str],
    *,
    render: bool,
    timeout: float,
    verify: bool,
    allow_private: bool,
    max_redirects: int,
    max_bytes: int,
    recommendation_limit: int,
    language: str,
) -> MobileReport:
    pool: BrowserPoolBoundary | None = None
    render_status: str | None = None
    if render:
        pool = BrowserPool(
            EgressPolicy(
                block_private=not allow_private,
                max_redirects=max_redirects,
                max_response_bytes=max_bytes,
            )
        )
        try:
            await pool.start()
        except CapabilityUnavailableError as exc:
            if exc.capability == "Playwright browser support":
                pool = None
                render_status = "playwright not installed"
            else:
                render_status = str(exc)
                await pool.close()
                pool = None
    try:
        pages = [
            await _audit_page(
                url,
                render=render,
                timeout=timeout,
                verify=verify,
                allow_private=allow_private,
                max_redirects=max_redirects,
                max_bytes=max_bytes,
                recommendation_limit=recommendation_limit,
                browser_pool=pool,
                render_status=render_status,
            )
            for url in urls
        ]
        all_checks = [check for page in pages for check in page.checks]
        score, categories = score_mobile_checks(all_checks)
        recommendations = rank_mobile_recommendations(all_checks, limit=recommendation_limit)
        return MobileReport(
            schema="agentready.mobile.v1",
            targets=list(urls),
            pages=pages,
            score=score,
            categories=categories,
            recommendations=recommendations,
            started_at=utc_now_iso(),
            finished_at=utc_now_iso(),
            language=language,
        )
    finally:
        if pool is not None:
            await pool.close()


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
) -> MobileReport:
    logger.info("Mobile audit started: urls=%d render=%s", len(urls), render)
    report = asyncio.run(_audit_mobile_async(
        urls,
        render=render,
        timeout=timeout,
        verify=verify,
        allow_private=allow_private,
        max_redirects=max_redirects,
        max_bytes=max_bytes,
        recommendation_limit=recommendation_limit,
        language=language,
    ))
    logger.info("Mobile audit finished: urls=%d aggregate_score=%d", len(urls), report.score)
    return report
