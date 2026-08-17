"""Typed SEO atomic rule contracts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from ...audit_core import (
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
from ...report_v2 import Finding
from ...report_v2 import FindingStatus as V2FindingStatus

FindingStatus = Literal["pass", "fail", "warn", "skip", "error"]


class RuleKind(StrEnum):
    STANDARD = "standard"
    CAPABILITY = "capability"
    HEURISTIC = "heuristic"


@dataclass(frozen=True, slots=True)
class SeoRuleSpec:
    id: str
    title: str
    category: str
    kind: RuleKind
    scored_by_default: bool
    applies_to: str = "html-page"
    version: str = "1.0.0"


@dataclass(frozen=True, slots=True)
class AtomicFinding:
    rule: SeoRuleSpec
    target: str
    status: FindingStatus
    details: str
    evidence_ids: tuple[str, ...]
    impact: str
    effort: str
    priority: int
    reason: str
    rerun_command: str
    fingerprint: str

    @property
    def scored(self) -> bool:
        return self.rule.scored_by_default and self.status != "skip"

    def to_contract(self) -> FindingContract:
        status = Status.ERROR if self.status == "error" else Status(self.status)
        applicability = Applicability.NOT_APPLICABLE if self.status == "skip" else Applicability.APPLICABLE
        completeness = EvaluationCompleteness.PARTIAL if self.status in {"error", "skip"} else EvaluationCompleteness.COMPLETE
        severity = Severity(self.impact) if self.impact in {item.value for item in Severity} else Severity.LOW
        effort = Effort(self.effort) if self.effort in {item.value for item in Effort} else Effort.LOW
        key = FindingKey(self.rule.id, self.rule.version, UrlIdentity.parse(self.target))
        return FindingContract(
            key=key,
            state_hash=FindingStateHash.from_state(
                key,
                status=status,
                applicability=applicability,
                completeness=completeness,
                evidence_ids=self.evidence_ids,
            ),
            status=status,
            applicability=applicability,
            completeness=completeness,
            severity=severity,
            impact=self.impact,
            effort=effort,
            priority=self.priority,
            evidence=tuple(EvidenceRef(item, item, self.details) for item in self.evidence_ids),
        )

    def to_v2(self) -> Finding:
        projected = self.to_contract().to_report_finding(
            title=self.rule.title,
            reason=self.reason or self.details,
            url=self.target,
        )
        # Keep the public v2 ID stable while the canonical contract carries
        # rule version and target identity in its machine key.
        return Finding(
            id=self.rule.id,
            title=projected.title,
            status=V2FindingStatus(projected.status.value),
            reason=projected.reason,
            evidence=projected.evidence,
        )


def finding(
    rule: SeoRuleSpec,
    target: str,
    status: FindingStatus,
    details: str,
    evidence_ids: tuple[str, ...],
    *,
    impact: str = "low",
    effort: str = "low",
    priority: int = 50,
    reason: str = "",
    rerun_command: str | None = None,
) -> AtomicFinding:
    if status in {"fail", "warn", "error"} and not evidence_ids:
        raise ValueError(f"actionable finding {rule.id} requires evidence")
    command = rerun_command or f"agentready audit --mode seo {target!r}"
    payload = {
        "rule": rule.id,
        "rule_version": rule.version,
        "target": target,
        "status": status,
        "evidence_ids": evidence_ids,
    }
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return AtomicFinding(rule, target, status, details, evidence_ids, impact, effort, priority, reason or details, command, fingerprint)
