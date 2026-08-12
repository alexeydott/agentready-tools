"""Typed SEO atomic rule contracts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from ...report_v2 import Finding, FindingEvidence
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

    def to_v2(self) -> Finding:
        return Finding(
            id=self.rule.id,
            title=self.rule.title,
            status=V2FindingStatus("unavailable" if self.status == "error" else self.status),
            reason=self.reason or self.details,
            evidence=tuple(FindingEvidence(item, self.details, self.target) for item in self.evidence_ids),
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
        "target": target,
        "status": status,
        "evidence_ids": evidence_ids,
    }
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return AtomicFinding(rule, target, status, details, evidence_ids, impact, effort, priority, reason or details, command, fingerprint)
