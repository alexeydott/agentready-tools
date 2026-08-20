from __future__ import annotations

import math
from collections import defaultdict

from .models import CategoryScore, CheckResult, NextLevel

LEVEL_NAMES = {
    0: "Not Agent-Ready",
    1: "Basic Web Presence",
    2: "Bot-Aware",
    3: "Agent-Readable",
    4: "Agent-Integrated",
    5: "Agent-Native",
}
LEVEL_MODEL = "transparent-tiered-v2; sequential 80% tier threshold inspired by open readiness tooling; not Cloudflare's unpublished formula"
SCORE_MODEL_ID = "readiness-transparent-v2"

_LEVEL_CRITERIA: dict[int, tuple[str, ...]] = {
    1: ("robots-txt", "sitemap", "link-headers"),
    2: ("ai-bot-rules", "content-signals"),
    3: ("markdown-negotiation",),
    4: ("api-catalog", "oauth-discovery", "oauth-protected-resource", "mcp-server-card", "a2a-agent-card"),
    5: ("agent-skills",),
}
_REQUIREMENT_LABELS = {
    "robots-txt": "valid robots.txt",
    "sitemap": "valid XML sitemap",
    "link-headers": "agent/API discovery Link header",
    "ai-bot-rules": "explicit AI crawler/user-agent policy",
    "content-signals": "explicit valid Content-Signal policy",
    "markdown-negotiation": "working Accept: text/markdown negotiation",
    "api-catalog": "API Catalog",
    "oauth-discovery": "OAuth Authorization Server Metadata",
    "oauth-protected-resource": "OAuth Protected Resource Metadata",
    "mcp-server-card": "MCP Server Card",
    "a2a-agent-card": "A2A Agent Card",
    "agent-skills": "Agent Skills index",
}


def overall_score(results: list[CheckResult]) -> int:
    applicable = [r for r in results if r.is_score_eligible and r.status not in {"skip", "error"}]
    if not applicable:
        return 0
    passed = sum(r.status == "pass" for r in applicable)
    return round(100 * passed / len(applicable))


def category_scores(results: list[CheckResult]) -> list[CategoryScore]:
    groups: dict[str, list[CheckResult]] = defaultdict(list)
    for r in results:
        groups[r.category].append(r)
    out: list[CategoryScore] = []
    for category, rows in groups.items():
        applicable = [r for r in rows if r.is_score_eligible and r.status not in {"skip", "error"}]
        passed = sum(r.status == "pass" for r in applicable)
        score = round(100 * passed / len(applicable)) if applicable else None
        out.append(CategoryScore(category=category, passed=passed, applicable=len(applicable), score=score))
    return out


def maturity_level(results: list[CheckResult], threshold: float = 0.8) -> tuple[int, str, NextLevel | None]:
    """Compute a transparent sequential maturity level.

    Only selected scored checks participate. A tier must contain at least one
    selected criterion and at least ``threshold`` of its applicable criteria
    must pass. Tiers are sequential. This intentionally does not claim to be
    Cloudflare's private scoring implementation.
    """
    if not 0 < threshold <= 1:
        raise ValueError("level threshold must be in (0, 1]")
    by_id = {r.id: r for r in results if r.is_score_eligible and r.status not in {"skip", "error"}}
    highest = 0
    next_level: NextLevel | None = None

    for level in range(1, 6):
        ids = [cid for cid in _LEVEL_CRITERIA[level] if cid in by_id]
        if not ids:
            # No criteria from this or later tiers means the chosen preset has
            # reached its highest meaningful tier (e.g. content-only scans).
            any_later = any(
                cid in by_id
                for later in range(level + 1, 6)
                for cid in _LEVEL_CRITERIA[later]
            )
            if any_later:
                next_level = NextLevel(
                    target=level,
                    name=LEVEL_NAMES[level],
                    requirements=[_REQUIREMENT_LABELS[cid] for cid in _LEVEL_CRITERIA[level]],
                    current=0,
                    needed=1,
                    remaining=1,
                )
            break
        passed_ids = [cid for cid in ids if by_id[cid].status == "pass"]
        needed = math.ceil(len(ids) * threshold)
        if len(passed_ids) >= needed:
            highest = level
            continue
        missing = [cid for cid in ids if by_id[cid].status != "pass"]
        next_level = NextLevel(
            target=level,
            name=LEVEL_NAMES[level],
            requirements=[_REQUIREMENT_LABELS[cid] for cid in missing],
            current=len(passed_ids),
            needed=needed,
            remaining=max(0, needed - len(passed_ids)),
        )
        break

    if highest == 5:
        next_level = None
    return highest, LEVEL_NAMES[highest], next_level


def ai_search_score(results: list[CheckResult]) -> tuple[int | None, int]:
    """Return a separate AI Search/GEO score without changing the core protocol score.

    Only checks explicitly marked ``geo_scored`` participate. Skipped/error checks
    are excluded because their applicability could not be established.
    """
    applicable = [r for r in results if r.geo_scored and r.status not in {"skip", "error"}]
    if not applicable:
        return None, 0
    passed = sum(r.status == "pass" for r in applicable)
    return round(100 * passed / len(applicable)), len(applicable)
