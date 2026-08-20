from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from .seo_models import SeoReport

logger = logging.getLogger(__name__)

SEO_SCHEMA = "agentready.seo.v2"

def compare_seo_baseline(report: SeoReport, path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        baseline = json.load(handle)
    if baseline.get("schema") != SEO_SCHEMA:
        raise ValueError(f"baseline is not an {SEO_SCHEMA} SEO report")
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
    checks: Sequence[object] | None = None,
    timeout: float = 5.0,
    verify: bool = True,
    allow_private: bool = True,
    max_redirects: int = 5,
    max_bytes: int = 5 * 1024 * 1024,
    recommendation_limit: int = 10,
    limits: dict[str, int | float] | None = None,
    language: str = "en",
    profile: str = "standard",
    crawl: bool = False,
    max_pages: int = 25,
    full_discovered: bool = False,
    render: bool = False,
    crawl_checks: Sequence[object] | None = None,
    ga_property: str | None = None,
    gsc_site: str | None = None,
) -> SeoReport:
    """Run every public SEO request through the canonical AuditService path."""
    from .audit_service import AuditRequest, AuditService
    from .seo_checks import SEO_CHECKS_BY_ID
    from .seo_crawler import CRAWL_CHECKS_BY_ID

    by_callable = {value: key for key, value in (*SEO_CHECKS_BY_ID.items(), *CRAWL_CHECKS_BY_ID.items())}
    selected = tuple(by_callable.get(check, getattr(check, "__name__", "")) for check in checks or ())
    selected += tuple(by_callable.get(check, getattr(check, "__name__", "")) for check in crawl_checks or ())
    logger.info("[FIX:seo-canonical] public SEO request checks=%d providers=%s", len(selected), bool(ga_property or gsc_site))

    result = AuditService().run(
        AuditRequest(
            target=url,
            mode="seo",
            profile=profile,
            max_pages=max_pages,
            timeout=timeout,
            render=render,
            language=language,
            crawl=crawl,
            full_discovered=full_discovered,
            recommendation_limit=recommendation_limit,
            limits=limits or {},
            allow_private=allow_private,
            include=selected,
            ga_property=ga_property,
            gsc_site=gsc_site,
        )
    )
    if result.seo_report is None:
        raise RuntimeError("canonical SEO execution returned no SEO report")
    return result.seo_report
