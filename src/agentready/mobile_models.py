"""Data models for mobile-friendliness audit reports.

The audit evaluates one or more pages and produces a per-page result plus an
aggregate cross-page score. Machine identifiers stay stable; human-facing text
is localized at render time.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from . import __version__
from .models import Evidence, Remediation

MobileStatus = Literal["pass", "fail", "warn", "skip", "error"]
MobileImpact = Literal["high", "medium", "low"]
MobileEffort = Literal["low", "medium", "high"]


@dataclass(slots=True)
class MobileCheckResult:
    id: str
    title: str
    category: str
    status: MobileStatus
    scored: bool
    details: str
    duration_ms: int = 0
    evidence: list[Evidence] = field(default_factory=list)
    remediation: Remediation | None = None

    @property
    def passed(self) -> bool:
        return self.status == "pass"


@dataclass(slots=True)
class MobileCategoryScore:
    category: str
    passed: int
    applicable: int
    score: int | None


@dataclass(slots=True)
class MobileRecommendation:
    check_id: str
    title: str
    action: str
    reason: str
    impact: MobileImpact
    effort: MobileEffort
    priority: int


@dataclass(slots=True)
class MobilePageReport:
    url: str
    rendered: bool
    checks: list[MobileCheckResult]
    score: int
    categories: list[MobileCategoryScore]
    recommendations: list[MobileRecommendation]
    started_at: str
    finished_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MobileReport:
    schema: str
    targets: list[str]
    pages: list[MobilePageReport]
    score: int
    categories: list[MobileCategoryScore]
    recommendations: list[MobileRecommendation]
    started_at: str
    finished_at: str
    language: str = "en"
    tool_version: str = __version__

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
