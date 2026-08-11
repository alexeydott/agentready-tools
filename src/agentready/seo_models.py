from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from . import __version__

from .models import Evidence, Remediation

SeoStatus = Literal["pass", "fail", "warn", "skip", "error"]
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
