from __future__ import annotations

import ast
import socket
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
    RunFactRecord,
    RunRecord,
    SQLiteSiteStore,
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
OTHER_TARGET = "https://example.test/other"


def _facts(
    *,
    target: str = TARGET,
    page_version: str = "1",
    robots_version: str = "1",
    allowed: bool = True,
):
    target_identity = UrlIdentity.parse(target)
    return (
        FactEnvelope(
            "page-fact",
            "page",
            target_identity,
            {"status_code": 200, "content_type": "text/html"},
            "2026-08-22T00:00:00Z",
            schema_family="page",
            schema_version=page_version,
        ),
        FactEnvelope(
            "robots-fact",
            "robots.policy",
            target_identity,
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


def test_canary_uses_only_requested_target_facts_for_readiness_and_evaluation():
    facts = _facts(target=OTHER_TARGET) + _facts(target=TARGET, allowed=False)

    result = evaluate_core_coverage(TARGET, facts)

    assert result.readiness.can_evaluate is True
    assert result.report.findings[0].status is FindingStatus.FAIL
    assert result.report.findings[0].reason == "robots.policy blocks the audited root"


def test_canary_does_not_use_other_target_facts_to_satisfy_readiness():
    facts = _facts(target=OTHER_TARGET) + (_facts(target=TARGET)[0],)

    result = evaluate_core_coverage(TARGET, facts)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE


def test_canary_scopes_schema_override_to_the_requested_fact_bundle():
    facts = _facts(target=OTHER_TARGET) + (_facts(target=TARGET)[0],)

    result = evaluate_core_coverage(
        TARGET,
        facts,
        fact_registry=FactSchemaRegistry({"page": "1", "robots.policy": "1"}),
    )

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE


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


def test_canary_replays_persisted_facts_with_network_disabled(tmp_path, monkeypatch):
    run_id = "run-e0-replay"
    original_facts = _facts()
    original = evaluate_core_coverage(TARGET, original_facts, run_id=run_id)
    path = tmp_path / "e0-replay.sqlite"
    store = SQLiteSiteStore(path)
    try:
        store.begin_run(RunRecord(run_id, "config", "tool", "rules"))
        for envelope in original_facts:
            assert envelope.schema_family is not None
            assert envelope.schema_version is not None
            store.put_run_fact(
                RunFactRecord(
                    run_id,
                    envelope.schema_family,
                    envelope.schema_version,
                    "url",
                    envelope.target.normalized(),
                    {
                        "id": envelope.id,
                        "kind": envelope.kind,
                        "value": envelope.value,
                        "representation_id": envelope.representation_id,
                    },
                    envelope.observed_at,
                )
            )
    finally:
        store.close()

    replay_store = SQLiteSiteStore(path, read_only=True)
    try:
        replayed_facts = tuple(
            FactEnvelope(
                record.payload["id"],
                record.payload["kind"],
                UrlIdentity.parse(record.subject),
                record.payload["value"],
                record.observed_at,
                representation_id=record.payload.get("representation_id"),
                schema_family=record.family,
                schema_version=record.schema_version,
            )
            for record in replay_store.iter_run_facts(run_id)
        )
    finally:
        replay_store.close()

    def fail_network(*args, **kwargs):
        raise AssertionError("offline E0 replay attempted network access")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    replayed = evaluate_core_coverage(TARGET, replayed_facts, run_id=run_id)

    assert replayed.finding.key == original.finding.key
    assert replayed.finding.state_hash == original.finding.state_hash
    assert replayed.report.findings[0].id == CORE_COVERAGE_RULE_ID
    assert replayed.report.findings[0].status is FindingStatus.PASS
