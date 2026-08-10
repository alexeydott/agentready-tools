"""Scoring and recommendations for mobile-friendliness audits."""
from __future__ import annotations

import logging
from collections import defaultdict

from .mobile_models import MobileCategoryScore, MobileCheckResult, MobileRecommendation

logger = logging.getLogger(__name__)

_IMPACT_RANK = {"high": 0, "medium": 1, "low": 2}
_EFFORT_RANK = {"low": 0, "medium": 1, "high": 2}


def score_mobile_checks(checks: list[MobileCheckResult]) -> tuple[int, list[MobileCategoryScore]]:
    applicable = [check for check in checks if check.scored and check.status != "skip"]
    passed = sum(check.status == "pass" for check in applicable)
    score = round(passed * 100 / len(applicable)) if applicable else 0
    grouped: dict[str, list[MobileCheckResult]] = defaultdict(list)
    for check in applicable:
        grouped[check.category].append(check)
    categories = [
        MobileCategoryScore(
            category=category,
            passed=sum(item.status == "pass" for item in items),
            applicable=len(items),
            score=round(sum(item.status == "pass" for item in items) * 100 / len(items)),
        )
        for category, items in sorted(grouped.items())
    ]
    logger.debug(
        "Mobile score calculated: checks=%d applicable=%d passed=%d score=%d",
        len(checks), len(applicable), passed, score,
    )
    return score, categories


def rank_mobile_recommendations(
    checks: list[MobileCheckResult],
    *,
    limit: int = 10,
) -> list[MobileRecommendation]:
    recommendations: list[MobileRecommendation] = []
    for check in checks:
        if check.status not in {"fail", "warn", "error"} or check.remediation is None:
            continue
        impact = "high" if check.category in {"configuration", "layout"} else "medium"
        effort = "low" if check.category == "configuration" else "medium"
        recommendations.append(
            MobileRecommendation(
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
    logger.debug("Mobile recommendations ranked: candidates=%d emitted=%d", len(recommendations), len(result))
    return result
