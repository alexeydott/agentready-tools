"""Orchestration for multi-page mobile-friendliness audits."""
from __future__ import annotations

import logging
import time
from collections.abc import Sequence

from .http import HttpClient
from .mobile_models import MobileCheckResult, MobilePageReport, MobileReport
from .mobile_render import MOBILE_RENDER_CHECKS
from .mobile_scoring import rank_mobile_recommendations, score_mobile_checks
from .models import utc_now_iso
from .target import ensure_public_url, parse_target

logger = logging.getLogger(__name__)

MobileCheck = type(MOBILE_RENDER_CHECKS[0]) if MOBILE_RENDER_CHECKS else object


def _audit_page(
    url: str,
    *,
    render: bool,
    timeout: float,
    verify: bool,
    allow_private: bool,
    max_redirects: int,
    max_bytes: int,
    recommendation_limit: int,
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
        for check in MOBILE_RENDER_CHECKS:
            try:
                checks.append(check(target.url, None))
            except Exception as exc:  # noqa: BLE001
                logger.error("Rendered mobile check failed: check=%s error=%s", check.__name__, exc)
                checks.append(
                    MobileCheckResult(
                        id=check.__name__.replace("check_", "").replace("_", "-"),
                        title=check.__name__.replace("check_", "").replace("_", " ").title(),
                        category="layout",
                        status="error",
                        scored=True,
                        details=str(exc),
                        duration_ms=0,
                    )
                )
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
    started = utc_now_iso()
    logger.info("Mobile audit started: urls=%d render=%s", len(urls), render)
    pages = [
        _audit_page(
            url,
            render=render,
            timeout=timeout,
            verify=verify,
            allow_private=allow_private,
            max_redirects=max_redirects,
            max_bytes=max_bytes,
            recommendation_limit=recommendation_limit,
        )
        for url in urls
    ]
    all_checks = [check for page in pages for check in page.checks]
    score, categories = score_mobile_checks(all_checks)
    recommendations = rank_mobile_recommendations(all_checks, limit=recommendation_limit)
    report = MobileReport(
        schema="agentready.mobile.v1",
        targets=list(urls),
        pages=pages,
        score=score,
        categories=categories,
        recommendations=recommendations,
        started_at=started,
        finished_at=utc_now_iso(),
        language=language,
    )
    logger.info("Mobile audit finished: urls=%d aggregate_score=%d", len(urls), score)
    return report
