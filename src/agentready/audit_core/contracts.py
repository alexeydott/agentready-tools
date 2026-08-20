"""Canonical immutable fact, evidence, and finding identity contracts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .models import (
    Applicability,
    EvaluationCompleteness,
    EvaluationOutcome,
    OperationalState,
    Status,
)
from .urls import UrlIdentity


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    id: str
    locator: str
    summary: str


@dataclass(frozen=True, slots=True)
class FactEnvelope:
    id: str
    kind: str
    target: UrlIdentity
    value: Any
    observed_at: str
    representation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "target": self.target.normalized(),
            "value": self.value,
            "observed_at": self.observed_at,
            "representation_id": self.representation_id,
        }


@dataclass(frozen=True, slots=True)
class FindingKey:
    rule_id: str
    rule_version: str
    target: UrlIdentity

    def to_string(self) -> str:
        return f"{self.rule_id}@{self.rule_version}:{self.target.normalized()}"


@dataclass(frozen=True, slots=True)
class FindingStateHash:
    value: str

    @classmethod
    def from_state(
        cls,
        key: FindingKey,
        *,
        status: Status,
        applicability: Applicability,
        completeness: EvaluationCompleteness,
        outcome: EvaluationOutcome | None = None,
        operational_state: OperationalState = OperationalState.NONE,
        evidence_ids: tuple[str, ...] = (),
        fact_ids: tuple[str, ...] = (),
    ) -> FindingStateHash:
        if outcome is None:
            outcome = {
                Status.PASS: EvaluationOutcome.PASS,
                Status.FAIL: EvaluationOutcome.FAIL,
                Status.WARN: EvaluationOutcome.WARN,
                Status.SKIP: EvaluationOutcome.NOT_APPLICABLE,
                Status.ERROR: EvaluationOutcome.UNKNOWN,
            }[status]
        payload = {
            "key": key.to_string(),
            "status": status.value,
            "outcome": outcome.value,
            "operational_state": operational_state.value,
            "applicability": applicability.value,
            "completeness": completeness.value,
            "evidence_ids": sorted(evidence_ids),
            "fact_ids": sorted(fact_ids),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return cls(hashlib.sha256(encoded.encode("utf-8")).hexdigest())


@dataclass(frozen=True, slots=True)
class FindingContract:
    key: FindingKey
    state_hash: FindingStateHash
    status: Status
    applicability: Applicability
    completeness: EvaluationCompleteness
    severity: Severity
    impact: str
    effort: Effort
    priority: int
    evidence: tuple[EvidenceRef, ...] = ()
    outcome: EvaluationOutcome | None = None
    operational_state: OperationalState = OperationalState.NONE

    def __post_init__(self) -> None:
        if self.priority < 0:
            raise ValueError("finding priority must not be negative")
        if self.outcome is None:
            outcome = {
                Status.PASS: EvaluationOutcome.PASS,
                Status.FAIL: EvaluationOutcome.FAIL,
                Status.WARN: EvaluationOutcome.WARN,
                Status.SKIP: EvaluationOutcome.NOT_APPLICABLE,
                Status.ERROR: EvaluationOutcome.UNKNOWN,
            }[self.status]
            object.__setattr__(self, "outcome", outcome)
        if self.status is Status.ERROR and self.operational_state is OperationalState.NONE:
            object.__setattr__(self, "operational_state", OperationalState.ERROR)

    def to_report_finding(
        self,
        *,
        title: str,
        reason: str,
        url: str | None = None,
        public_id: str | None = None,
    ) -> Any:
        """Project canonical machine state into the v2 report DTO."""
        from ..report_v2 import Finding, FindingEvidence, FindingStatus

        if self.operational_state is not OperationalState.NONE:
            status = FindingStatus.UNAVAILABLE
        elif self.outcome is EvaluationOutcome.NOT_APPLICABLE:
            status = FindingStatus.SKIP
        elif self.outcome is EvaluationOutcome.UNKNOWN:
            status = FindingStatus.SKIP
        else:
            status = FindingStatus(self.outcome.value)
        evidence = tuple(
            FindingEvidence(item.id, item.summary, url or self.key.target.normalized())
            for item in self.evidence
        )
        return Finding(
            id=public_id or self.key.to_string(),
            title=title,
            status=status,
            reason=reason,
            evidence=evidence,
            rule_version=self.key.rule_version,
        )
