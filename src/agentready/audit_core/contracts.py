"""Canonical immutable fact, evidence, and finding identity contracts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .models import Applicability, EvaluationCompleteness, Status
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
        evidence_ids: tuple[str, ...] = (),
        fact_ids: tuple[str, ...] = (),
    ) -> FindingStateHash:
        payload = {
            "key": key.to_string(),
            "status": status.value,
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

    def __post_init__(self) -> None:
        if self.priority < 0:
            raise ValueError("finding priority must not be negative")

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

        status = (
            FindingStatus.UNAVAILABLE
            if self.status is Status.ERROR
            else FindingStatus(self.status.value)
        )
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
        )
