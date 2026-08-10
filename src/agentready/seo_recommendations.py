from __future__ import annotations

import logging

from .seo_models import SeoCheckResult, SeoRecommendation

logger = logging.getLogger(__name__)

_IMPACT_RANK = {"high": 0, "medium": 1, "low": 2}
_EFFORT_RANK = {"low": 0, "medium": 1, "high": 2}


def rank_recommendations(
    checks: list[SeoCheckResult],
    *,
    limit: int = 10,
) -> list[SeoRecommendation]:
    recommendations: list[SeoRecommendation] = []
    for check in checks:
        if check.status not in {"fail", "warn", "error"} or check.remediation is None:
            continue
        impact = "high" if check.category in {"crawlability", "indexability"} else "medium"
        effort = "low" if check.category in {"metadata", "indexability"} else "medium"
        recommendations.append(
            SeoRecommendation(
                check_id=check.id,
                title=check.title,
                action=check.remediation.summary,
                reason=check.details,
                impact=impact,  # type: ignore[arg-type]
                effort=effort,  # type: ignore[arg-type]
                priority=0,
            )
        )
    recommendations.sort(key=lambda item: (_IMPACT_RANK[item.impact], _EFFORT_RANK[item.effort], item.check_id))
    for index, recommendation in enumerate(recommendations, 1):
        recommendation.priority = index
    result = recommendations[: max(0, limit)]
    logger.debug("SEO recommendations ranked: candidates=%d emitted=%d", len(recommendations), len(result))
    return result
