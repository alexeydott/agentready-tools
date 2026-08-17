"""Deterministic contracts shared by versioned protocol auditors."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..audit_core import (
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


class ProtocolStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    UNAVAILABLE = "unavailable"
    NOT_EVALUATED = "not_evaluated"


@dataclass(frozen=True)
class ProtocolEvidence:
    source_id: str
    locator: str
    summary: str
    url: str | None = None
    anchor: str | None = None

    def to_dict(self) -> dict[str, str]:
        result = {
            "source_id": self.source_id,
            "locator": self.locator,
            "summary": self.summary,
        }
        if self.url is not None:
            result["url"] = self.url
        if self.anchor is not None:
            result["anchor"] = self.anchor
        return result


@dataclass(frozen=True)
class ProtocolFinding:
    profile_id: str
    version: str
    status: ProtocolStatus
    title: str
    reason: str
    evidence: tuple[ProtocolEvidence, ...] = ()
    deprecated: bool = False

    def to_contract(self, target: str) -> FindingContract:
        status = Status.ERROR if self.status is ProtocolStatus.UNAVAILABLE else Status(self.status.value)
        key = FindingKey(self.profile_id, self.version, UrlIdentity.parse(target))
        completeness = EvaluationCompleteness.PARTIAL if status is Status.ERROR else EvaluationCompleteness.COMPLETE
        return FindingContract(
            key=key,
            state_hash=FindingStateHash.from_state(
                key,
                status=status,
                applicability=Applicability.APPLICABLE,
                completeness=completeness,
                evidence_ids=tuple(item.source_id for item in self.evidence),
            ),
            status=status,
            applicability=Applicability.APPLICABLE,
            completeness=completeness,
            severity=Severity.HIGH if status is Status.FAIL else Severity.INFO,
            impact="high" if status is Status.FAIL else "info",
            effort=Effort.MEDIUM,
            priority=80 if status is Status.FAIL else 10,
            evidence=tuple(EvidenceRef(item.source_id, item.locator, item.summary) for item in self.evidence),
        )

    @property
    def fingerprint(self) -> str:
        payload = {
            "profile_id": self.profile_id,
            "version": self.version,
            "status": self.status.value,
            "evidence": [(item.source_id, item.locator, item.url, item.anchor) for item in self.evidence],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self, *, target: str | None = None) -> dict[str, Any]:
        projected = None
        if target is not None:
            projected = self.to_contract(target).to_report_finding(
                title=self.title,
                reason=self.reason,
                url=target,
                public_id=f"{self.profile_id}@{self.version}",
            )
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "status": projected.status.value if projected is not None else self.status.value,
            "title": projected.title if projected is not None else self.title,
            "reason": projected.reason if projected is not None else self.reason,
            "deprecated": self.deprecated,
            "fingerprint": self.fingerprint,
            "evidence": [item.to_dict() for item in self.evidence],
        }
