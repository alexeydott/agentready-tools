from __future__ import annotations

from .models import CheckResult, Recommendation
from .registry import BY_ID

_IMPACT_WEIGHT = {"high": 3, "medium": 2, "low": 1}
_EFFORT_WEIGHT = {"low": 0, "medium": 1, "high": 2}
_CATEGORY_REASON = {
    "Discoverability": "Agents need a deterministic way to discover machine-readable resources without scraping the UI.",
    "Content Accessibility": "Reducing parsing and context overhead makes agent retrieval faster, cheaper, and more reliable.",
    "Bot Access Control": "Explicit crawler and AI-use policy removes ambiguity about which automated clients may access content.",
    "Protocol Discovery": "Standard discovery metadata lets agents connect to APIs and tools without bespoke integration logic.",
    "Commerce": "Machine-readable commerce and payment protocols let agents transact without a human-only checkout flow.",
    "AI Search / GEO": "Search and answer engines need indexable, crawler-accessible, unambiguous pages with extractable factual content; heuristic checks are not claimed ranking factors.",
}


def _impact(row: CheckResult, current_level: int) -> str:
    if row.scored and current_level < 3:
        return "high"
    if row.scored:
        return "medium"
    if row.category == "AI Search / GEO":
        if row.geo_scored:
            return "high" if current_level < 3 else "medium"
        return "medium"
    if row.supplemental and row.category == "Content Accessibility":
        return "medium"
    return "low"


def generate_recommendations(results: list[CheckResult], current_level: int, *, limit: int = 10) -> list[Recommendation]:
    out: list[Recommendation] = []
    for row in results:
        if row.status not in {"fail", "warn", "error"} or not row.remediation:
            continue
        spec = BY_ID.get(row.id)
        effort = spec.effort if spec else "medium"
        impact = _impact(row, current_level)
        priority = _IMPACT_WEIGHT[impact] * 10 - _EFFORT_WEIGHT[effort]
        reason = _CATEGORY_REASON.get(row.category, "Fixing this reduces ambiguity for autonomous agents.")
        out.append(
            Recommendation(
                check_id=row.id,
                title=row.title,
                action=row.remediation.summary,
                reason=reason,
                impact=impact,  # type: ignore[arg-type]
                effort=effort,
                priority=priority,
            )
        )
    out.sort(key=lambda r: (-r.priority, _EFFORT_WEIGHT[r.effort], r.title.lower()))
    return out[: max(0, limit)]
