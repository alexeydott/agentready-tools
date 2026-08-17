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

    def to_contract(self, target: str):
        """Return the canonical v2 identity for this mobile finding."""
        from .audit_core import (
            Applicability,
            Effort,
            EvaluationCompleteness,
            EvidenceRef,
            FindingContract,
            FindingKey,
            FindingStateHash,
            Severity,
            Status,
            UrlIdentity,
        )

        status = Status.ERROR if self.status == "error" else Status(self.status if self.status in {"pass", "fail", "warn"} else "skip")
        applicability = Applicability.NOT_APPLICABLE if self.status == "skip" else Applicability.APPLICABLE
        completeness = EvaluationCompleteness.PARTIAL if self.status in {"skip", "error"} else EvaluationCompleteness.COMPLETE
        key = FindingKey(self.id, "2.0.0", UrlIdentity.parse(target))
        evidence = tuple(
            EvidenceRef(item.finding or item.action, item.url or target, item.finding or item.action)
            for item in self.evidence
        )
        return FindingContract(
            key=key,
            state_hash=FindingStateHash.from_state(
                key,
                status=status,
                applicability=applicability,
                completeness=completeness,
                evidence_ids=tuple(item.id for item in evidence),
            ),
            status=status,
            applicability=applicability,
            completeness=completeness,
            severity=Severity.HIGH if self.status == "fail" else Severity.INFO,
            impact="high" if self.status == "fail" else "info",
            effort=Effort.MEDIUM,
            priority=80 if self.status == "fail" else 10,
            evidence=evidence,
        )

    def to_dict(self, target: str) -> dict[str, Any]:
        """Project canonical state into the existing mobile v2 check fields."""
        projected = self.to_contract(target).to_report_finding(
            title=self.title,
            reason=self.details,
            url=target,
            public_id=self.id,
        )
        payload = asdict(self)
        payload.update(
            id=projected.id,
            title=projected.title,
            status=projected.status.value,
            details=projected.reason,
        )
        return payload


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
        payload = asdict(self)
        payload["checks"] = [check.to_dict(self.url) for check in self.checks]
        return payload


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
        payload = asdict(self)
        payload["pages"] = [page.to_dict() for page in self.pages]
        return payload
