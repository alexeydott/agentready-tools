"""Catalog-to-runtime projection layer (#19).

Converts a :class:`agentready.audit_core.rule_catalog.RuleCatalogEntry`
into a runtime-facing :class:`RuleProjection`, resolves applicability as a
pure function over explicit context, and gates fact-requirement
satisfaction using the existing :mod:`agentready.audit_core.fact_schema`
registry. This module never calls an evaluator and never performs
HTTP/browser/provider access; ``resolve_applicability`` and
``resolve_evaluation_readiness`` are pure functions over their arguments.

Design notes (see #19 acceptance criteria):
- Score role is preserved on the projection for reporting, but is never
  read by :func:`resolve_evaluation_readiness` — score eligibility must
  not influence whether a rule is evaluated.
- Rule kind and failure policy survive projection unchanged (raw catalog
  strings), for the evaluator/scoring layer to interpret later.
- Unsupported/malformed applicability expressions resolve to
  ``Applicability.UNKNOWN`` (never silently to ``APPLICABLE``), and force
  an ``UNKNOWN`` evaluation outcome rather than allowing a confident
  PASS/FAIL.
- Missing or incompatible mandatory fact requirements likewise force an
  ``UNKNOWN`` evaluation outcome instead of calling the evaluator.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agentready.audit_core.fact_schema import (
    FactSchemaRegistry,
    FactSchemaRequirement,
    FactSchemaResult,
)
from agentready.audit_core.models import Applicability, EvaluationOutcome
from agentready.audit_core.rule_catalog import RuleCatalogEntry, RuleCatalogSourceRef

__all__ = [
    "ApplicabilityMode",
    "RuleApplicabilityExpression",
    "ApplicabilityContext",
    "RuleProjection",
    "EvaluationReadiness",
    "parse_applicability_expression",
    "resolve_applicability",
    "project_entry",
    "evaluate_fact_requirements",
    "resolve_evaluation_readiness",
]


class ApplicabilityMode(StrEnum):
    """Supported applicability expression shapes.

    Only ``ALWAYS_FOR_SUBJECT`` is currently produced by the #17 catalog
    content (every draft rule's ``condition`` is the generated
    "applies whenever a {subject} subject was collected for the run"
    sentence). Any other condition text is explicitly unsupported rather
    than silently treated as always-applicable.
    """

    ALWAYS_FOR_SUBJECT = "always_for_subject"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class RuleApplicabilityExpression:
    mode: ApplicabilityMode
    subject: str
    required_profile: str | None = None
    required_engine: str | None = None
    required_surface: str | None = None
    raw_condition: str = ""


@dataclass(frozen=True, slots=True)
class ApplicabilityContext:
    """Explicit facts about the current run available to applicability resolution.

    Contains no transport/browser handles — only the already-collected
    subject kind and optional profile/engine/surface identifiers.
    """

    subject_kind: str
    profile: str | None = None
    engine: str | None = None
    surface: str | None = None


_ALWAYS_CONDITION_TEMPLATE = "applies whenever a {subject} subject was collected for the run"


def parse_applicability_expression(entry: RuleCatalogEntry) -> RuleApplicabilityExpression:
    """Parse a catalog entry's applicability data into a structured expression.

    Returns an explicit :class:`ApplicabilityMode.UNSUPPORTED` expression
    (never ``ALWAYS_FOR_SUBJECT``) when the condition text does not match
    a recognized supported shape, so callers cannot mistake an unparsed
    condition for an always-applicable rule.
    """
    expected = _ALWAYS_CONDITION_TEMPLATE.format(subject=entry.scope)
    if entry.condition == expected:
        return RuleApplicabilityExpression(
            mode=ApplicabilityMode.ALWAYS_FOR_SUBJECT,
            subject=entry.scope,
            raw_condition=entry.condition,
        )
    return RuleApplicabilityExpression(
        mode=ApplicabilityMode.UNSUPPORTED,
        subject=entry.scope,
        raw_condition=entry.condition,
    )


def resolve_applicability(
    expression: RuleApplicabilityExpression,
    context: ApplicabilityContext,
) -> Applicability:
    """Pure function: resolve applicability from an expression and explicit context.

    Performs no I/O. Unsupported expressions always resolve to
    ``Applicability.UNKNOWN`` rather than ``APPLICABLE`` or
    ``NOT_APPLICABLE`` -- an unsupported expression is not proof either way.
    """
    if expression.mode is ApplicabilityMode.UNSUPPORTED:
        return Applicability.UNKNOWN

    if expression.required_profile is not None and expression.required_profile != context.profile:
        return Applicability.NOT_APPLICABLE
    if expression.required_engine is not None and expression.required_engine != context.engine:
        return Applicability.NOT_APPLICABLE
    if expression.required_surface is not None and expression.required_surface != context.surface:
        return Applicability.NOT_APPLICABLE

    if expression.mode is ApplicabilityMode.ALWAYS_FOR_SUBJECT:
        if context.subject_kind == expression.subject:
            return Applicability.APPLICABLE
        return Applicability.NOT_APPLICABLE

    return Applicability.UNKNOWN


@dataclass(frozen=True, slots=True)
class RuleProjection:
    """Runtime-facing projection of one frozen catalog entry.

    ``score_role`` is retained for reporting only; evaluation-readiness
    resolution below never reads it (score eligibility must not gate
    whether a rule is evaluated).
    """

    rule_id: str
    version: str
    applicability_expression: RuleApplicabilityExpression
    fact_requirements: tuple[FactSchemaRequirement, ...]
    failure_policy: str
    score_role: str
    rule_kind: str
    automation_mode: str
    comparison_dimensions: tuple[str, ...]
    sources: tuple[RuleCatalogSourceRef, ...]


def project_entry(entry: RuleCatalogEntry) -> RuleProjection:
    """Project one catalog entry without executing or evaluating it."""
    expression = parse_applicability_expression(entry)
    fact_requirements = tuple(
        FactSchemaRequirement(family=req.family, min_schema_version=req.min_schema_version)
        for req in entry.fact_requirements
    )
    return RuleProjection(
        rule_id=entry.rule_id,
        version=entry.version,
        applicability_expression=expression,
        fact_requirements=fact_requirements,
        failure_policy=entry.failure_policy,
        score_role=entry.score_role,
        rule_kind=entry.rule_kind,
        automation_mode=entry.automation_mode,
        comparison_dimensions=entry.comparison_dimensions,
        sources=entry.sources,
    )


def evaluate_fact_requirements(
    projection: RuleProjection,
    registry: FactSchemaRegistry,
) -> tuple[FactSchemaResult, ...]:
    """Resolve a projection's fact requirements against an observed-fact registry."""
    return registry.resolve(projection.fact_requirements)


@dataclass(frozen=True, slots=True)
class EvaluationReadiness:
    """Whether a projected rule may be handed to an evaluator, and why not if not.

    ``can_evaluate`` and ``forced_outcome`` are derived solely from
    applicability and fact-requirement compatibility -- never from
    ``score_role`` -- so score eligibility cannot control whether the
    evaluator runs.
    """

    applicability: Applicability
    fact_results: tuple[FactSchemaResult, ...]
    can_evaluate: bool
    forced_outcome: EvaluationOutcome | None


def resolve_evaluation_readiness(
    projection: RuleProjection,
    context: ApplicabilityContext,
    registry: FactSchemaRegistry,
) -> EvaluationReadiness:
    """Pure function combining applicability + fact-requirement gating.

    Mandatory (i.e. all declared) fact requirements must be usable
    (:attr:`FactSchemaResult.usable`) for the evaluator to run; a missing,
    too-old, incompatible, or unknown-version fact forces
    ``EvaluationOutcome.UNKNOWN`` instead of allowing a confident
    PASS/FAIL. An unsupported/not-applicable applicability expression is
    resolved before fact requirements are even checked.
    """
    applicability = resolve_applicability(projection.applicability_expression, context)

    if applicability is Applicability.NOT_APPLICABLE:
        return EvaluationReadiness(applicability, (), False, EvaluationOutcome.NOT_APPLICABLE)
    if applicability is Applicability.UNKNOWN:
        return EvaluationReadiness(applicability, (), False, EvaluationOutcome.UNKNOWN)

    fact_results = evaluate_fact_requirements(projection, registry)
    mandatory_satisfied = all(result.usable for result in fact_results)
    if not mandatory_satisfied:
        return EvaluationReadiness(applicability, fact_results, False, EvaluationOutcome.UNKNOWN)

    return EvaluationReadiness(applicability, fact_results, True, None)
