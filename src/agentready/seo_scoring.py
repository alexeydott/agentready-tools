from __future__ import annotations

import logging
from collections import defaultdict

from .seo_models import SeoCategoryScore, SeoCheckResult

logger = logging.getLogger(__name__)


def score_checks(checks: list[SeoCheckResult]) -> tuple[int, list[SeoCategoryScore]]:
    applicable = [check for check in checks if check.scored and check.status not in {"skip"}]
    passed = sum(check.status == "pass" for check in applicable)
    score = round(passed * 100 / len(applicable)) if applicable else 0
    grouped: dict[str, list[SeoCheckResult]] = defaultdict(list)
    for check in applicable:
        grouped[check.category].append(check)
    categories = [
        SeoCategoryScore(
            category=category,
            passed=sum(item.status == "pass" for item in items),
            applicable=len(items),
            score=round(sum(item.status == "pass" for item in items) * 100 / len(items)),
        )
        for category, items in sorted(grouped.items())
    ]
    logger.debug(
        "SEO score calculated: checks=%d applicable=%d passed=%d score=%d categories=%d",
        len(checks), len(applicable), passed, score, len(categories),
    )
    return score, categories
