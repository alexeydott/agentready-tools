from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from agentready.audit_core import (
    CORE_COVERAGE_RULE_ID,
    CORE_COVERAGE_RULE_VERSION,
    CANARY_EVALUATOR_REGISTRY,
    FactEnvelope,
    FactSchemaRegistry,
    EvaluatorRegistry,
    UnregisteredRuleError,
    UnresolvedCatalogTargetError,
    bind_frozen_rule,
    evaluate_core_coverage,
)
from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.audit_core.urls import UrlIdentity
from agentready.report_v2 import FindingStatus, semantic_diff
from agentready.seo.rule_crosswalk import resolve_frozen_rule_ids

TARGET = "https://example.test/"


def _facts(*, page_version: str = "1", robots_version: str = "1", allowed: bool = True):
    target = UrlIdentity.parse(TARGET)
    return (
        FactEnvelope(
            "page-fact",
            "page",
            target,
            {"status_code": 200, "content_type": "text/html"},
            "2026-08-22T00:00:00Z",
            schema_family="page",
            schema_version=page_version,
        ),
        FactEnvelope(
            "robots-fact",
            "robots.policy",
            target,
            {"root_allowed": allowed},
            "2026-08-22T00:00:00Z",
            schema_family="robots.policy",
            schema_version=robots_version,
        ),
    )


def test_canary_registry_contains_exactly_one_frozen_target():
    assert CANARY_EVALUATOR_REGISTRY.registered_targets == (
        (CORE_COVERAGE_RULE_ID, CORE_COVERAGE_RULE_VERSION),
    )


def test_canary_valid_path_produces_scored_finding_and_identity_preserving_report():
    result = evaluate_core_coverage(
        TARGET,
        _facts(),
        run_id="run-e0",
        score_model_id="readiness-transparent-v2",
    )

    assert result.readiness.can_evaluate is True
    assert result.finding.key.rule_id == CORE_COVERAGE_RULE_ID
    assert result.finding.key.rule_version == CORE_COVERAGE_RULE_VERSION
    assert result.report.findings[0].id == CORE_COVERAGE_RULE_ID
    assert result.report.findings[0].rule_version == CORE_COVERAGE_RULE_VERSION
    assert result.report.rule_catalog_version == load_rule_catalog_snapshot().catalog_version
    assert result.report.score_model_id == "readiness-transparent-v2"
    assert result.report.coverage.to_dict() == {
        "total_rules": 1,
        "evaluated_rules": 1,
        "applicable_rules": 1,
        "complete_rules": 1,
    }

    baseline = result.report.to_dict()
    diff = semantic_diff(baseline, baseline)
    assert diff.comparable is True
    assert diff.findings["unchanged"] == (CORE_COVERAGE_RULE_ID,)


def test_canary_evaluator_fails_when_robots_policy_blocks_the_root():
    result = evaluate_core_coverage(TARGET, _facts(allowed=False))

    assert result.readiness.can_evaluate is True
    assert result.report.findings[0].status is FindingStatus.FAIL
    assert result.report.score == 0


@pytest.mark.parametrize("missing_family", ["page", "robots.policy"])
def test_missing_mandatory_fact_blocks_confident_evaluation(missing_family):
    facts = tuple(item for item in _facts() if item.schema_family != missing_family)

    result = evaluate_core_coverage(TARGET, facts)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.findings[0].outcome == "unknown"
    assert result.report.coverage.complete_rules == 0


@pytest.mark.parametrize(
    "facts",
    [
        _facts(page_version="0"),
        _facts(page_version="unknown"),
        _facts(robots_version="0"),
    ],
)
def test_old_or_unknown_fact_versions_block_confident_evaluation(facts):
    result = evaluate_core_coverage(TARGET, facts)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE


def test_incompatible_fact_version_blocks_confident_evaluation():
    result = evaluate_core_coverage(
        TARGET,
        _facts(),
        fact_registry=FactSchemaRegistry(
            {"page": "1", "robots.policy": "1"},
            incompatible=frozenset({("robots.policy", "1")}),
        ),
    )

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE


def test_applicability_is_resolved_before_evaluator_invocation():
    calls: list[str] = []

    def evaluator(target, facts):
        calls.append(target)
        raise AssertionError("evaluator must not run for a non-applicable subject")

    registry = EvaluatorRegistry()
    registry.register(CORE_COVERAGE_RULE_ID, CORE_COVERAGE_RULE_VERSION, evaluator)
    result = evaluate_core_coverage(TARGET, _facts(), subject_kind="origin", registry=registry)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.SKIP
    assert calls == []


def test_registry_rejects_unregistered_frozen_rules():
    registry = EvaluatorRegistry()
    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        registry.register("CORE-COVERAGE-002", "1.0.0", lambda target, facts: None)


def test_binding_rejects_catalog_rule_without_an_explicit_evaluator():
    with pytest.raises(UnregisteredRuleError, match="no evaluator binding"):
        bind_frozen_rule("CORE-COVERAGE-002", "1.0.0")


def test_binding_rejects_missing_catalog_target():
    snapshot = load_rule_catalog_snapshot()
    missing = replace(snapshot, entries=tuple(
        entry for entry in snapshot.entries if entry.rule_id != CORE_COVERAGE_RULE_ID
    ))

    with pytest.raises(UnresolvedCatalogTargetError, match="unresolved"):
        bind_frozen_rule(snapshot=missing)


def test_binding_rejects_stale_catalog_version():
    snapshot = load_rule_catalog_snapshot()
    entry = snapshot.entry(CORE_COVERAGE_RULE_ID)
    assert entry is not None
    stale = replace(snapshot, entries=tuple(
        replace(item, version="2.0.0") if item.rule_id == CORE_COVERAGE_RULE_ID else item
        for item in snapshot.entries
    ))

    with pytest.raises(UnresolvedCatalogTargetError, match="stale"):
        bind_frozen_rule(snapshot=stale)


def test_partial_crawl_coverage_is_preserved_without_second_rule_execution():
    result = evaluate_core_coverage(
        TARGET,
        _facts(),
        coverage_classification="partial_limit",
        urls_discovered=4,
        urls_fetched=1,
        max_pages_hit=True,
    )

    assert result.report.coverage.to_dict() == {
        "total_rules": 1,
        "evaluated_rules": 1,
        "applicable_rules": 1,
        "complete_rules": 1,
        "urls_discovered": 4,
        "urls_fetched": 1,
        "limit": {"max_pages_hit": True},
        "classification": "partial_limit",
    }
    assert len(result.report.findings) == 1


def test_current_legacy_crosswalk_remains_available_without_cutover():
    assert resolve_frozen_rule_ids("page-available") == (CORE_COVERAGE_RULE_ID,)


def test_evaluator_module_has_no_transport_or_collection_io_imports():
    path = Path(__file__).parents[1] / "src" / "agentready" / "audit_core" / "evaluator_registry.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imports.update(
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not imports & {"http", "httpx", "requests", "playwright", "sqlite3"}
