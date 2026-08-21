"""Stable rule lifecycle contracts for the vNext audit core."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class AuthorityLevel(StrEnum):
    STANDARD = "standard"
    DOCUMENTED = "documented"
    HEURISTIC = "heuristic"


class RequirementLevel(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    SUPPLEMENTAL = "supplemental"


class Applicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class EvaluationCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    NOT_EVALUATED = "not_evaluated"


class ScoreParticipation(StrEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"


class FailurePolicy(StrEnum):
    STRICT = "strict"
    PARTIAL_DECISION_ALLOWED = "partial_decision_allowed"


class Status(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"
    ERROR = "error"


class EvaluationOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class OperationalState(StrEnum):
    NONE = "none"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RuleVersion:
    version: str
    released: str

    def to_dict(self) -> dict[str, str]:
        return {"version": self.version, "released": self.released}


@dataclass(frozen=True, slots=True)
class RuleSpec:
    id: str
    title: str
    category: str
    authority: AuthorityLevel
    requirement: RequirementLevel
    version: RuleVersion
    score_participation: ScoreParticipation = ScoreParticipation.INCLUDED
    score_model_id: str = "readiness-transparent-v2"
    score_policy_version: str = "1.0.0"
    failure_policy: FailurePolicy = FailurePolicy.STRICT

    def __post_init__(self) -> None:
        logger.debug("[WP1.1] validating RuleSpec id=%s authority=%s", self.id, self.authority.value)
        if not self.id.strip():
            raise ValueError("rule id must not be empty")
        if not self.title.strip():
            raise ValueError("rule title must not be empty")
        if not self.score_model_id.strip():
            raise ValueError("score model id must not be empty")
        if not self.score_policy_version.strip():
            raise ValueError("score policy version must not be empty")
        if self.authority == AuthorityLevel.HEURISTIC and self.score_participation == ScoreParticipation.INCLUDED:
            raise ValueError("heuristic rules must be excluded from the mandatory score")
        logger.debug("[WP1.1] RuleSpec validated id=%s version=%s", self.id, self.version.version)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["authority"] = self.authority.value
        value["requirement"] = self.requirement.value
        value["score_participation"] = self.score_participation.value
        value["failure_policy"] = self.failure_policy.value
        return value
