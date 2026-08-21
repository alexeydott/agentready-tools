from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from . import __version__
from .models import Evidence, Remediation

SeoStatus = Literal["pass", "fail", "warn", "skip", "error"]
ScoreRole = Literal["eligible", "observation", "guard", "legacy-only"]
SeoImpact = Literal["high", "medium", "low"]
SeoEffort = Literal["low", "medium", "high"]


@dataclass(slots=True)
class SeoCheckResult:
    id: str
    title: str
    category: str
    status: SeoStatus
    scored: bool
    details: str
    duration_ms: int = 0
    evidence: list[Evidence] = field(default_factory=list)
    remediation: Remediation | None = None
    score_role: ScoreRole = "eligible"
    score_included: bool | None = None

    @property
    def is_score_eligible(self) -> bool:
        return (
            self.score_included
            if self.score_included is not None
            else self.scored and self.score_role == "eligible"
        )

    @property
    def passed(self) -> bool:
        return self.status == "pass"


@dataclass(slots=True)
class SeoCategoryScore:
    category: str
    passed: int
    applicable: int
    score: int | None


@dataclass(slots=True)
class SeoRecommendation:
    check_id: str
    title: str
    action: str
    reason: str
    impact: SeoImpact
    effort: SeoEffort
    priority: int


@dataclass(slots=True)
class SeoReport:
    schema: str
    target: str
    origin: str
    checks: list[SeoCheckResult]
    score: int
    categories: list[SeoCategoryScore]
    recommendations: list[SeoRecommendation]
    started_at: str
    finished_at: str
    language: str = "en"
    tool_version: str = __version__
    run_id: str | None = None
    config_hash: str | None = None
    coverage: dict[str, Any] = field(default_factory=dict)
    inventory: dict[str, Any] = field(default_factory=dict)
    provider_freshness: dict[str, Any] = field(default_factory=dict)
    comparison: dict[str, Any] = field(default_factory=dict)
    score_model_id: str = "seo-binary-v1"
    rule_catalog_version: str = "seo-v2-atomic"
    rule_catalog_digest: str = ""
    rule_catalog_digest_kind: str = "synthetic"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Keep legacy JSON golden/consumer shape when optional marketer
        # projections are not populated; populated v2 runs emit them.
        for key in ("run_id", "config_hash", "coverage", "inventory", "provider_freshness", "comparison"):
            if payload.get(key) in (None, {}, []):
                payload.pop(key, None)
        return payload
