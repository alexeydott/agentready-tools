"""Tests for the catalog-to-runtime projection layer (#19).

Table-driven per the #19 verification plan: applicability resolution,
fact-requirement gating, and evaluation-readiness combination — all as
pure functions over explicit context, with no evaluator execution.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agentready.audit_core.fact_schema import FactCompatibility, FactSchemaRegistry
from agentready.audit_core.models import Applicability, EvaluationOutcome
from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.audit_core.rule_projection import (
    ApplicabilityContext,
    ApplicabilityMode,
    RuleApplicabilityExpression,
    evaluate_fact_requirements,
    parse_applicability_expression,
    project_entry,
    resolve_applicability,
    resolve_evaluation_readiness,
)

ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "src" / "agentready"


@pytest.fixture(scope="module")
def snapshot():
    return load_rule_catalog_snapshot()


def test_project_entry_does_not_execute_or_evaluate(snapshot):
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    projection = project_entry(entry)
    assert projection.rule_id == "CORE-COVERAGE-001"
    assert projection.failure_policy == entry.failure_policy
    assert projection.rule_kind == entry.rule_kind
    assert projection.score_role == entry.score_role


def test_always_for_subject_applicability_matches_supported_catalog_condition(snapshot):
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    expression = parse_applicability_expression(entry)
    assert expression.mode is ApplicabilityMode.ALWAYS_FOR_SUBJECT
    assert expression.subject == entry.scope


def test_unsupported_condition_is_never_treated_as_always_applicable():
    expression = RuleApplicabilityExpression(
        mode=ApplicabilityMode.UNSUPPORTED,
        subject="html-page",
        raw_condition="something the projector cannot parse",
    )
    context = ApplicabilityContext(subject_kind="html-page")
    assert resolve_applicability(expression, context) is Applicability.UNKNOWN


@pytest.mark.parametrize(
    ("subject_kind", "expected"),
    [
        ("html-page", Applicability.APPLICABLE),
        ("origin", Applicability.NOT_APPLICABLE),
    ],
)
def test_always_for_subject_applicability_depends_on_context(subject_kind, expected):
    expression = RuleApplicabilityExpression(
        mode=ApplicabilityMode.ALWAYS_FOR_SUBJECT,
        subject="html-page",
        raw_condition="applies whenever a html-page subject was collected for the run",
    )
    context = ApplicabilityContext(subject_kind=subject_kind)
    assert resolve_applicability(expression, context) is expected


@pytest.mark.parametrize(
    ("required_profile", "required_engine", "required_surface", "context_kwargs", "expected"),
    [
        ("mobile", None, None, {"profile": "desktop"}, Applicability.NOT_APPLICABLE),
        ("mobile", None, None, {"profile": "mobile"}, Applicability.APPLICABLE),
        (None, "chromium", None, {"engine": "webkit"}, Applicability.NOT_APPLICABLE),
        (None, None, "rendered", {"surface": "static"}, Applicability.NOT_APPLICABLE),
    ],
)
def test_profile_engine_surface_mismatch_forces_not_applicable(
    required_profile, required_engine, required_surface, context_kwargs, expected
):
    expression = RuleApplicabilityExpression(
        mode=ApplicabilityMode.ALWAYS_FOR_SUBJECT,
        subject="html-page",
        required_profile=required_profile,
        required_engine=required_engine,
        required_surface=required_surface,
        raw_condition="applies whenever a html-page subject was collected for the run",
    )
    context = ApplicabilityContext(subject_kind="html-page", **context_kwargs)
    assert resolve_applicability(expression, context) is expected


def test_fact_requirement_gate_all_satisfied(snapshot):
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    projection = project_entry(entry)
    registry = FactSchemaRegistry({req.family: "1" for req in projection.fact_requirements})
    results = evaluate_fact_requirements(projection, registry)
    assert results
    assert all(result.compatibility is FactCompatibility.COMPATIBLE for result in results)


def test_fact_requirement_gate_one_missing_fact(snapshot):
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    projection = project_entry(entry)
    registry = FactSchemaRegistry({})
    results = evaluate_fact_requirements(projection, registry)
    assert any(result.compatibility is FactCompatibility.MISSING for result in results)


def test_fact_requirement_gate_one_too_old_fact(snapshot):
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    projection = project_entry(entry)
    family = projection.fact_requirements[0].family
    registry = FactSchemaRegistry({family: "0"})
    results = evaluate_fact_requirements(projection, registry)
    matching = [r for r in results if r.family == family]
    assert matching and matching[0].compatibility is FactCompatibility.TOO_OLD


def test_fact_requirement_gate_unknown_fact_version(snapshot):
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    projection = project_entry(entry)
    family = projection.fact_requirements[0].family
    registry = FactSchemaRegistry({family: "not-a-number"})
    results = evaluate_fact_requirements(projection, registry)
    matching = [r for r in results if r.family == family]
    assert matching and matching[0].compatibility is FactCompatibility.UNKNOWN


def test_readiness_all_facts_satisfied_allows_evaluation(snapshot):
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    projection = project_entry(entry)
    registry = FactSchemaRegistry({req.family: "1" for req in projection.fact_requirements})
    context = ApplicabilityContext(subject_kind=entry.scope)
    readiness = resolve_evaluation_readiness(projection, context, registry)
    assert readiness.applicability is Applicability.APPLICABLE
    assert readiness.can_evaluate is True
    assert readiness.forced_outcome is None


def test_readiness_missing_fact_prevents_confident_evaluation(snapshot):
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    projection = project_entry(entry)
    registry = FactSchemaRegistry({})
    context = ApplicabilityContext(subject_kind=entry.scope)
    readiness = resolve_evaluation_readiness(projection, context, registry)
    assert readiness.can_evaluate is False
    assert readiness.forced_outcome is EvaluationOutcome.UNKNOWN


def test_readiness_not_applicable_short_circuits_before_fact_check(snapshot):
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    projection = project_entry(entry)
    registry = FactSchemaRegistry({})
    context = ApplicabilityContext(subject_kind="a-subject-that-never-matches")
    readiness = resolve_evaluation_readiness(projection, context, registry)
    assert readiness.applicability is Applicability.NOT_APPLICABLE
    assert readiness.can_evaluate is False
    assert readiness.forced_outcome is EvaluationOutcome.NOT_APPLICABLE
    assert readiness.fact_results == ()


def test_readiness_unsupported_applicability_yields_unknown_not_always():
    projection_expression = RuleApplicabilityExpression(
        mode=ApplicabilityMode.UNSUPPORTED,
        subject="html-page",
        raw_condition="an expression the projector cannot parse",
    )
    from agentready.audit_core.rule_projection import RuleProjection

    projection = RuleProjection(
        rule_id="TEST-UNSUPPORTED-001",
        version="1.0.0",
        applicability_expression=projection_expression,
        fact_requirements=(),
        failure_policy="block_on_missing_facts",
        score_role="scored",
        rule_kind="scored_rule",
        automation_mode="automated",
        comparison_dimensions=(),
        sources=(),
    )
    registry = FactSchemaRegistry({})
    context = ApplicabilityContext(subject_kind="html-page")
    readiness = resolve_evaluation_readiness(projection, context, registry)
    assert readiness.applicability is Applicability.UNKNOWN
    assert readiness.can_evaluate is False
    assert readiness.forced_outcome is EvaluationOutcome.UNKNOWN


@pytest.mark.parametrize("score_role", ["scored", "diagnostic", "observation_only"])
def test_score_role_does_not_control_evaluation_readiness(snapshot, score_role):
    """Observation/guard/legacy-only rules still get evaluated (or blocked) purely
    on applicability + fact readiness -- never because of score_role."""
    entries = [e for e in snapshot.entries if e.score_role == score_role]
    assert entries, f"expected at least one catalog entry with score_role={score_role}"
    entry = entries[0]
    projection = project_entry(entry)
    registry_satisfied = FactSchemaRegistry({req.family: "1" for req in projection.fact_requirements})
    context = ApplicabilityContext(subject_kind=entry.scope)
    readiness = resolve_evaluation_readiness(projection, context, registry_satisfied)
    # Evaluation-readiness must be identical regardless of score_role, given the
    # same applicability/fact conditions -- i.e. driven only by those two inputs.
    assert readiness.can_evaluate is True
    assert readiness.forced_outcome is None


def test_all_catalog_entries_project_without_error(snapshot):
    for entry in snapshot.entries:
        projection = project_entry(entry)
        assert projection.rule_id == entry.rule_id
        # Every #17 draft rule uses the supported always-for-subject shape today.
        assert projection.applicability_expression.mode is ApplicabilityMode.ALWAYS_FOR_SUBJECT


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module.split(".", 1)[0])
    return result


def test_rule_projection_module_performs_no_transport_or_provider_imports():
    path = SOURCE / "audit_core" / "rule_projection.py"
    forbidden = {"http", "httpx", "playwright", "sqlite3", "requests"}
    assert not (_imports(path) & forbidden)
