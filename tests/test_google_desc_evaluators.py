from __future__ import annotations

import ast
import socket
from dataclasses import replace
from pathlib import Path

import pathlib

import pytest

from agentready.audit_core import (
    CORE_COVERAGE_RULE_ID,
    CORE_COVERAGE_RULE_VERSION,
    CANARY_EVALUATOR_REGISTRY,
    FactEnvelope,
    FactSchemaRegistry,
    EvaluatorRegistry,
    GOOGLE_DESC_EVALUATOR_REGISTRY,
    GOOGLE_DESC_RULE_ID,
    GOOGLE_DESC_RULE_VERSION,
    MAX_DESCRIPTION_LENGTH,
    MIN_DESCRIPTION_LENGTH,
    RunFactRecord,
    RunRecord,
    SQLiteSiteStore,
    UnregisteredRuleError,
    evaluate_core_coverage,
    evaluate_google_desc,
)
from agentready.audit_core.google_desc_evaluators import _google_desc_evaluator
from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.audit_core.urls import UrlIdentity
from agentready.report_v2 import FindingStatus, semantic_diff

TARGET = "https://example.test/"
OTHER_TARGET = "https://example.test/other"

GOOD_DESCRIPTION = "x" * 140


def _facts(
    *,
    target: str = TARGET,
    page_version: str = "1",
    descriptions: list[str] | None = None,
):
    if descriptions is None:
        descriptions = [GOOD_DESCRIPTION]
    target_identity = UrlIdentity.parse(target)
    return (
        FactEnvelope(
            "page-fact",
            "page",
            target_identity,
            {
                "titles": ["Example"],
                "descriptions": descriptions,
                "status_code": 200,
                "content_type": "text/html",
            },
            "2026-08-22T00:00:00Z",
            schema_family="page",
            schema_version=page_version,
        ),
    )


def test_desc_registry_contains_exactly_one_frozen_target():
    assert GOOGLE_DESC_EVALUATOR_REGISTRY.registered_targets == (
        (GOOGLE_DESC_RULE_ID, GOOGLE_DESC_RULE_VERSION),
    )


def test_desc_pass_path_produces_complete_scored_finding():
    result = evaluate_google_desc(
        TARGET,
        _facts(),
        run_id="run-e8",
        score_model_id="readiness-transparent-v2",
    )

    assert result.readiness.can_evaluate is True
    assert result.finding.key.rule_id == GOOGLE_DESC_RULE_ID
    assert result.finding.key.rule_version == GOOGLE_DESC_RULE_VERSION
    assert result.report.findings[0].id == GOOGLE_DESC_RULE_ID
    assert result.report.findings[0].rule_version == GOOGLE_DESC_RULE_VERSION
    assert result.report.findings[0].status is FindingStatus.PASS
    assert result.report.findings[0].outcome == "pass"
    assert result.report.findings[0].completeness == "complete"
    assert result.report.rule_catalog_version == load_rule_catalog_snapshot().catalog_version
    assert result.report.coverage.complete_rules == 1
    assert result.report.score == 100


@pytest.mark.parametrize(
    "descriptions,expected_reason_fragment",
    [
        ([], "missing"),
        (["", "   "], "empty"),
        (["x" * 10], "too short"),
        (["x" * 500], "too long"),
        ([GOOD_DESCRIPTION, "y" * 130], "multiple"),
    ],
)
def test_desc_fail_reasons_are_deterministic(descriptions, expected_reason_fragment):
    result = evaluate_google_desc(TARGET, _facts(descriptions=descriptions))

    assert result.readiness.can_evaluate is True
    assert result.report.findings[0].status is FindingStatus.FAIL
    assert result.report.findings[0].outcome == "fail"
    assert result.report.findings[0].completeness == "complete"
    assert expected_reason_fragment in result.report.findings[0].reason

    repeat = evaluate_google_desc(TARGET, _facts(descriptions=descriptions))
    assert repeat.report.findings[0].reason == result.report.findings[0].reason
    assert repeat.report.findings[0].state_hash == result.report.findings[0].state_hash


def test_desc_band_boundaries_are_inclusive():
    at_min = _google_desc_evaluator(
        TARGET, {"page": {"descriptions": ["x" * MIN_DESCRIPTION_LENGTH]}}
    )
    at_max = _google_desc_evaluator(
        TARGET, {"page": {"descriptions": ["x" * MAX_DESCRIPTION_LENGTH]}}
    )
    below = _google_desc_evaluator(
        TARGET, {"page": {"descriptions": ["x" * (MIN_DESCRIPTION_LENGTH - 1)]}}
    )
    above = _google_desc_evaluator(
        TARGET, {"page": {"descriptions": ["x" * (MAX_DESCRIPTION_LENGTH + 1)]}}
    )

    assert at_min.outcome.value == "pass"
    assert at_max.outcome.value == "pass"
    assert below.outcome.value == "fail"
    assert above.outcome.value == "fail"


@pytest.mark.parametrize("missing_family", ["page"])
def test_missing_mandatory_fact_blocks_confident_evaluation(missing_family):
    facts = tuple(item for item in _facts() if item.schema_family != missing_family)

    result = evaluate_google_desc(TARGET, facts)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.findings[0].outcome == "unknown"
    assert result.report.coverage.complete_rules == 0


@pytest.mark.parametrize(
    "facts",
    [
        _facts(page_version="0"),
        _facts(page_version="unknown"),
    ],
)
def test_old_or_unknown_fact_versions_block_confident_evaluation(facts):
    result = evaluate_google_desc(TARGET, facts)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.coverage.complete_rules == 0


@pytest.mark.parametrize(
    "facts,override",
    [
        (
            _facts(page_version="0"),
            FactSchemaRegistry({"page": "1"}),
        ),
    ],
)
def test_override_registry_cannot_upgrade_old_or_unknown_bundle_versions(facts, override):
    result = evaluate_google_desc(TARGET, facts, fact_registry=override)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.coverage.complete_rules == 0


def test_override_registry_cannot_downgrade_bundle_observed_versions():
    result = evaluate_google_desc(TARGET, _facts(), fact_registry=FactSchemaRegistry({"page": "0"}))

    assert result.readiness.can_evaluate is True


def test_desc_uses_only_requested_target_facts():
    facts = _facts(target=OTHER_TARGET, descriptions=["too short"]) + _facts(
        target=TARGET, descriptions=["also short"]
    )

    result = evaluate_google_desc(TARGET, facts)

    assert result.readiness.can_evaluate is True
    assert result.report.findings[0].status is FindingStatus.FAIL
    assert "also short" in result.report.findings[0].reason


def test_desc_does_not_use_other_target_facts_to_satisfy_readiness():
    facts = _facts(target=OTHER_TARGET)

    result = evaluate_google_desc(TARGET, facts)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE


def test_applicability_is_resolved_before_evaluator_invocation():
    calls: list[str] = []

    def spy_evaluator(target, facts):
        calls.append(target)
        raise AssertionError("evaluator must not run for a non-applicable subject")

    registry = EvaluatorRegistry(
        ((GOOGLE_DESC_RULE_ID, GOOGLE_DESC_RULE_VERSION, spy_evaluator),),
        allowlist=((GOOGLE_DESC_RULE_ID, GOOGLE_DESC_RULE_VERSION),),
    )
    result = evaluate_google_desc(TARGET, _facts(), subject_kind="origin", registry=registry)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.SKIP
    assert calls == []


def test_canary_registry_rejects_google_desc_target():
    from agentready.audit_core.google_desc_evaluators import _google_desc_evaluator as evaluator

    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        CANARY_EVALUATOR_REGISTRY.register(
            GOOGLE_DESC_RULE_ID, GOOGLE_DESC_RULE_VERSION, evaluator
        )


def test_desc_registry_rejects_canary_target_and_duplicates():
    from agentready.audit_core.evaluator_registry import _core_coverage_evaluator

    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        GOOGLE_DESC_EVALUATOR_REGISTRY.register(
            CORE_COVERAGE_RULE_ID, CORE_COVERAGE_RULE_VERSION, _core_coverage_evaluator
        )

    with pytest.raises(Exception, match="already registered"):
        GOOGLE_DESC_EVALUATOR_REGISTRY.register(
            GOOGLE_DESC_RULE_ID,
            GOOGLE_DESC_RULE_VERSION,
            lambda target, facts: None,
        )


def test_desc_finding_participates_in_scoring_consistently():
    passing = evaluate_google_desc(TARGET, _facts())
    failing = evaluate_google_desc(TARGET, _facts(descriptions=["short"]))

    assert passing.finding.severity.value == "info"
    assert passing.finding.priority == 10
    assert passing.finding.failure_policy.value == "block_on_missing_facts"
    assert passing.report.score == 100

    assert failing.finding.severity.value == "high"
    assert failing.finding.priority == 20
    assert failing.report.score == 0

    unavailable = evaluate_google_desc(TARGET, ())
    assert unavailable.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert unavailable.report.score == 100


def test_desc_replays_persisted_facts_with_network_disabled(tmp_path, monkeypatch):
    run_id = "run-e8-replay"
    original_facts = _facts()
    original = evaluate_google_desc(TARGET, original_facts, run_id=run_id)
    path = tmp_path / "e8-replay.sqlite"
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
        raise AssertionError("offline E8 replay attempted network access")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    replayed = evaluate_google_desc(TARGET, replayed_facts, run_id=run_id)

    assert replayed.finding.key == original.finding.key
    assert replayed.finding.state_hash == original.finding.state_hash
    assert replayed.report.findings[0].id == GOOGLE_DESC_RULE_ID
    assert replayed.report.findings[0].status is FindingStatus.PASS


def test_desc_semantic_diff_identity_and_report_catalog_identity():
    baseline = evaluate_google_desc(TARGET, _facts(), run_id="run-e8").report.to_dict()

    assert baseline["rule_catalog_version"] == load_rule_catalog_snapshot().catalog_version
    assert baseline["rule_catalog_digest_kind"] == "content"
    assert baseline["rule_catalog_digest"]

    diff = semantic_diff(baseline, baseline)
    assert diff.comparable is True
    assert diff.findings["unchanged"] == (GOOGLE_DESC_RULE_ID,)


def test_desc_binding_resolves_from_real_catalog():
    from agentready.audit_core.evaluator_registry import bind_frozen_rule

    binding = bind_frozen_rule(
        GOOGLE_DESC_RULE_ID,
        GOOGLE_DESC_RULE_VERSION,
        registry=GOOGLE_DESC_EVALUATOR_REGISTRY,
    )

    assert binding.rule_id == GOOGLE_DESC_RULE_ID
    assert binding.version == GOOGLE_DESC_RULE_VERSION
    assert binding.title == "Meta description is present and within recommended length"


def test_desc_binding_rejects_stale_catalog_version():
    snapshot = load_rule_catalog_snapshot()
    stale = replace(
        snapshot,
        entries=tuple(
            replace(item, version="2.0.0") if item.rule_id == GOOGLE_DESC_RULE_ID else item
            for item in snapshot.entries
        ),
    )

    from agentready.audit_core.evaluator_registry import (
        UnresolvedCatalogTargetError,
        bind_frozen_rule,
    )

    with pytest.raises(UnresolvedCatalogTargetError, match="stale"):
        bind_frozen_rule(
            GOOGLE_DESC_RULE_ID,
            GOOGLE_DESC_RULE_VERSION,
            snapshot=stale,
            registry=GOOGLE_DESC_EVALUATOR_REGISTRY,
        )


def test_desc_evaluator_module_has_no_transport_or_collection_io_imports():
    path = (
        Path(__file__).parents[1]
        / "src"
        / "agentready"
        / "audit_core"
        / "google_desc_evaluators.py"
    )
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
    assert not imports & {
        "http",
        "httpx",
        "requests",
        "playwright",
        "sqlite3",
        "bs4",
        "lxml",
    }


def test_canary_path_remains_unchanged_alongside_desc_binding():
    canary_facts = (
        FactEnvelope(
            "page-fact",
            "page",
            UrlIdentity.parse(TARGET),
            {"status_code": 200, "content_type": "text/html", "crawlable": True},
            "2026-08-22T00:00:00Z",
            schema_family="page",
            schema_version="1",
        ),
        FactEnvelope(
            "robots-fact",
            "robots.policy",
            UrlIdentity.parse(TARGET),
            {"root_allowed": True},
            "2026-08-22T00:00:00Z",
            schema_family="robots.policy",
            schema_version="1",
        ),
    )

    result = evaluate_core_coverage(TARGET, canary_facts)

    assert result.report.findings[0].id == CORE_COVERAGE_RULE_ID
    assert result.report.findings[0].status is FindingStatus.PASS
    assert result.report.findings[0].rule_version == CORE_COVERAGE_RULE_VERSION


def _desc_module_source() -> str:
    return (
        pathlib.Path(__file__).parents[1]
        / "src"
        / "agentready"
        / "audit_core"
        / "google_desc_evaluators.py"
    ).read_text(encoding="utf-8")


def test_desc_contract_is_single_family_page():
    """#54 amendment: page@1 only — no hidden structured-data readiness deps."""
    src = _desc_module_source()
    assert '("structured-data", "1")' not in src
    assert 'schema_family="structured-data"' not in src
    assert "structured-data-fact" not in src
    assert "structured_version" not in src

    page_only = tuple(e for e in _facts() if e.schema_family == "page")
    result = evaluate_google_desc(
        TARGET, page_only, fact_registry=FactSchemaRegistry({"page": "1"})
    )
    assert result.readiness.can_evaluate is True
