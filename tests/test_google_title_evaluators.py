"""Stage E9 tests for the frozen GOOGLE-TITLE-001@1.0.0 evaluator binding."""
from __future__ import annotations

import ast
import socket
from dataclasses import replace
from pathlib import Path

import pathlib

import pytest

from agentready.audit_core import (
    CORE_COVERAGE_RULE_ID,
    FactEnvelope,
    FactSchemaRegistry,
    GOOGLE_TITLE_EVALUATOR_REGISTRY,
    GOOGLE_TITLE_MAX_LENGTH,
    GOOGLE_TITLE_MIN_LENGTH,
    GOOGLE_TITLE_RULE_ID,
    GOOGLE_TITLE_RULE_VERSION,
    RunFactRecord,
    RunRecord,
    SQLiteSiteStore,
    UnregisteredRuleError,
    UnresolvedCatalogTargetError,
    bind_frozen_rule,
    bind_google_title_rule,
    evaluate_google_title,
)
from agentready.audit_core.evaluator_registry import EvaluatorRegistry, register_expected_contract
from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.audit_core.urls import UrlIdentity
from agentready.report_v2 import FindingStatus, semantic_diff

TARGET = "https://example.test/"
OTHER_TARGET = "https://example.test/other"

GOOD_TITLE = "Example Domain — Products, Pricing, and Documentation Overview"


def _facts(
    *,
    target: str = TARGET,
    page_version: str = "1",
    titles: list[str] | None = None,
):
    target_identity = UrlIdentity.parse(target)
    if titles is None:
        titles = [GOOD_TITLE]
    return (
        FactEnvelope(
            "page-fact",
            "page",
            target_identity,
            {
                "titles": titles,
                "descriptions": ["Example domain meta description"],
                "status_code": 200,
                "content_type": "text/html; charset=utf-8",
            },
            "2026-08-22T00:00:00Z",
            schema_family="page",
            schema_version=page_version,
        ),
    )


def test_title_registry_contains_exactly_one_frozen_target():
    assert GOOGLE_TITLE_EVALUATOR_REGISTRY.registered_targets == (
        (GOOGLE_TITLE_RULE_ID, GOOGLE_TITLE_RULE_VERSION),
    )


def test_binding_targets_the_single_catalog_row_with_page_fact_only():
    binding = bind_google_title_rule()

    assert binding.rule_id == GOOGLE_TITLE_RULE_ID
    assert binding.version == GOOGLE_TITLE_RULE_VERSION
    assert binding.title == "Title tag is present and within recommended length"
    assert tuple(
        (requirement.family, requirement.min_schema_version)
        for requirement in binding.projection.fact_requirements
    ) == (("page", "1"),)


def test_content_main_is_not_a_prerequisite_for_binding_or_evaluation():
    """Regression for #32: no undeclared content.main prerequisite exists."""
    snapshot = load_rule_catalog_snapshot()
    entry = snapshot.entry(GOOGLE_TITLE_RULE_ID)
    assert entry is not None
    assert [item.family for item in entry.fact_requirements] == ["page"]

    result = evaluate_google_title(TARGET, _facts())

    assert result.readiness.can_evaluate is True
    assert result.report.findings[0].status is FindingStatus.PASS


def test_pass_path_within_recommended_band():
    result = evaluate_google_title(TARGET, _facts())

    assert result.readiness.can_evaluate is True
    assert result.report.findings[0].status is FindingStatus.PASS
    assert result.report.findings[0].status is FindingStatus.PASS
    assert result.report.coverage.complete_rules == 1


@pytest.mark.parametrize("length", [GOOGLE_TITLE_MIN_LENGTH, GOOGLE_TITLE_MAX_LENGTH])
def test_band_boundaries_pass(length):
    result = evaluate_google_title(TARGET, _facts(titles=["a" * length]))

    assert result.report.findings[0].status is FindingStatus.PASS


def test_missing_title_fact_reason():
    result = evaluate_google_title(TARGET, _facts(titles=None))
    result = evaluate_google_title(
        TARGET,
        (
            FactEnvelope(
                "page-fact",
                "page",
                UrlIdentity.parse(TARGET),
                {"titles": [], "status_code": 200, "content_type": "text/html"},
                "2026-08-22T00:00:00Z",
                schema_family="page",
                schema_version="1",
            ),
        ),
    )

    assert result.report.findings[0].status is FindingStatus.FAIL
    assert result.report.findings[0].reason == "page has no non-empty title"


def test_empty_and_whitespace_titles_fail_deterministically():
    result = evaluate_google_title(TARGET, _facts(titles=["   "]))

    assert result.report.findings[0].status is FindingStatus.FAIL
    assert result.report.findings[0].reason == "page has no non-empty title"


def test_multiple_titles_fail_deterministically():
    result = evaluate_google_title(TARGET, _facts(titles=[GOOD_TITLE, "Second Title"]))

    assert result.report.findings[0].status is FindingStatus.FAIL
    assert result.report.findings[0].reason.startswith(
        "page declares 2 title elements"
    )


def test_too_short_title_fails_deterministically():
    short = "a" * (GOOGLE_TITLE_MIN_LENGTH - 1)
    result = evaluate_google_title(TARGET, _facts(titles=[short]))

    assert result.report.findings[0].status is FindingStatus.FAIL
    assert result.report.findings[0].reason.startswith("title is too short")


def test_too_long_title_fails_deterministically():
    long_title = "b" * (GOOGLE_TITLE_MAX_LENGTH + 1)
    result = evaluate_google_title(TARGET, _facts(titles=[long_title]))

    assert result.report.findings[0].status is FindingStatus.FAIL
    assert result.report.findings[0].reason.startswith("title is too long")


def test_missing_page_fact_blocks_confident_evaluation():
    result = evaluate_google_title(TARGET, ())

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.findings[0].outcome == "unknown"
    assert result.report.coverage.complete_rules == 0


@pytest.mark.parametrize("page_version", ["0", "unknown"])
def test_old_or_unknown_page_versions_block_confident_evaluation(page_version):
    result = evaluate_google_title(TARGET, _facts(page_version=page_version))

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE


def test_override_registry_cannot_upgrade_bundle_versions():
    result = evaluate_google_title(
        TARGET,
        _facts(page_version="0"),
        fact_registry=FactSchemaRegistry({"page": "1"}),
    )

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.coverage.complete_rules == 0


def test_other_url_titles_are_ignored_by_subject_scoping():
    facts = _facts(target=OTHER_TARGET, titles=["Other Page Title"]) + _facts(
        titles=["x" * (GOOGLE_TITLE_MAX_LENGTH + 5)]
    )

    result = evaluate_google_title(TARGET, facts)

    assert result.readiness.can_evaluate is True
    assert result.report.findings[0].status is FindingStatus.FAIL
    assert result.report.findings[0].reason.startswith("title is too long")


def test_applicability_gate_skips_before_evaluator_invocation():
    calls: list[str] = []

    def spy_evaluator(target, facts):
        calls.append(target)
        raise AssertionError("evaluator must not run for a non-applicable subject")

    registry = EvaluatorRegistry(
        ((GOOGLE_TITLE_RULE_ID, GOOGLE_TITLE_RULE_VERSION, spy_evaluator),),
        allowlist=((GOOGLE_TITLE_RULE_ID, GOOGLE_TITLE_RULE_VERSION),),
    )
    result = evaluate_google_title(
        TARGET, _facts(), subject_kind="origin", registry=registry
    )

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.SKIP
    assert calls == []


def test_canary_registry_rejects_google_title_registration():
    registry = EvaluatorRegistry()
    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        registry.register(
            GOOGLE_TITLE_RULE_ID,
            GOOGLE_TITLE_RULE_VERSION,
            lambda target, facts: None,
        )


def test_title_registry_rejects_canary_rule_and_duplicates():
    registry = EvaluatorRegistry(allowlist=((GOOGLE_TITLE_RULE_ID, GOOGLE_TITLE_RULE_VERSION),))
    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        registry.register(CORE_COVERAGE_RULE_ID, "1.0.0", lambda target, facts: None)
    registry.register(
        GOOGLE_TITLE_RULE_ID,
        GOOGLE_TITLE_RULE_VERSION,
        lambda target, facts: None,
    )
    with pytest.raises(Exception, match="already registered"):
        registry.register(
            GOOGLE_TITLE_RULE_ID,
            GOOGLE_TITLE_RULE_VERSION,
            lambda target, facts: None,
        )
    assert GOOGLE_TITLE_EVALUATOR_REGISTRY.registered_targets == (
        (GOOGLE_TITLE_RULE_ID, GOOGLE_TITLE_RULE_VERSION),
    )


def test_score_participation_matches_scored_role():
    passing = evaluate_google_title(TARGET, _facts())
    failing = evaluate_google_title(TARGET, _facts(titles=["short"]))

    assert passing.binding.projection.score_role == "scored"
    assert passing.report.score == 100
    assert failing.report.score == 0


def test_offline_sqlite_replay_preserves_identity(tmp_path, monkeypatch):
    run_id = "run-e9-replay"
    original_facts = _facts()
    original = evaluate_google_title(TARGET, original_facts, run_id=run_id)
    path = tmp_path / "e9-replay.sqlite"
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
        raise AssertionError("offline E9 replay attempted network access")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    replayed = evaluate_google_title(TARGET, replayed_facts, run_id=run_id)

    assert replayed.finding.key == original.finding.key
    assert replayed.finding.state_hash == original.finding.state_hash
    assert replayed.report.findings[0].id == GOOGLE_TITLE_RULE_ID
    assert replayed.report.findings[0].status is FindingStatus.PASS


def test_semantic_diff_of_identical_reports_is_unchanged():
    baseline = evaluate_google_title(TARGET, _facts()).report.to_dict()

    diff = semantic_diff(baseline, baseline)

    assert diff.comparable is True
    assert diff.findings["unchanged"] == (GOOGLE_TITLE_RULE_ID,)


def test_report_carries_catalog_identity_and_public_id():
    snapshot = load_rule_catalog_snapshot()
    result = evaluate_google_title(TARGET, _facts())

    assert result.report.rule_catalog_version == snapshot.catalog_version
    assert result.report.rule_catalog_digest == snapshot.rule_catalog_digest
    assert result.report.findings[0].id == GOOGLE_TITLE_RULE_ID


def test_binding_rejects_stale_catalog_version():
    snapshot = load_rule_catalog_snapshot()
    stale = replace(
        snapshot,
        entries=tuple(
            replace(item, version="2.0.0") if item.rule_id == GOOGLE_TITLE_RULE_ID else item
            for item in snapshot.entries
        ),
    )

    with pytest.raises(UnresolvedCatalogTargetError, match="stale"):
        bind_frozen_rule(
            GOOGLE_TITLE_RULE_ID,
            GOOGLE_TITLE_RULE_VERSION,
            snapshot=stale,
            registry=GOOGLE_TITLE_EVALUATOR_REGISTRY,
        )


def test_binding_rejects_contract_drift_from_expected_row():
    snapshot = load_rule_catalog_snapshot()
    drifted = replace(
        snapshot,
        entries=tuple(
            replace(
                item,
                fact_requirements=item.fact_requirements
                + (type(item.fact_requirements[0])("robots.policy", "1"),),
            )
            if item.rule_id == GOOGLE_TITLE_RULE_ID
            else item
            for item in snapshot.entries
        ),
    )

    with pytest.raises(Exception, match="accepted frozen evaluator contract"):
        bind_frozen_rule(
            GOOGLE_TITLE_RULE_ID,
            GOOGLE_TITLE_RULE_VERSION,
            snapshot=drifted,
            registry=GOOGLE_TITLE_EVALUATOR_REGISTRY,
        )


def test_register_expected_contract_rejects_unexpected_rows_via_validator():
    # A rule without an expected-contract row cannot pass validation even if a
    # registry entry existed; the validator fails closed.
    snapshot = load_rule_catalog_snapshot()
    other_entry = next(
        item for item in snapshot.entries if item.rule_id not in {GOOGLE_TITLE_RULE_ID, CORE_COVERAGE_RULE_ID}
    )
    registry = EvaluatorRegistry(
        ((other_entry.rule_id, other_entry.version, lambda target, facts: None),),
        allowlist=((other_entry.rule_id, other_entry.version),),
    )

    with pytest.raises(Exception, match="accepted frozen evaluator contract"):
        bind_frozen_rule(
            other_entry.rule_id,
            other_entry.version,
            snapshot=snapshot,
            registry=registry,
        )
    # Cleanup so later parametrized catalog loads are unaffected.
    from agentready.audit_core.evaluator_registry import _EXPECTED_CONTRACTS

    _EXPECTED_CONTRACTS.pop((other_entry.rule_id, other_entry.version), None)


def test_evaluator_module_has_no_transport_collection_or_storage_imports():
    path = (
        Path(__file__).parents[1]
        / "src"
        / "agentready"
        / "audit_core"
        / "google_title_evaluators.py"
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
        "urllib",
        "socket",
    }


def _title_module_source() -> str:
    return (
        pathlib.Path(__file__).parents[1]
        / "src"
        / "agentready"
        / "audit_core"
        / "google_title_evaluators.py"
    ).read_text(encoding="utf-8")


def test_title_contract_is_page_only_with_typed_band():
    """page@1 only; typed LengthBand 30..65 governed by the semantics artifact."""
    from agentready.audit_core.rule_catalog import load_rule_semantics

    src = _title_module_source()
    assert '("structured-data", "1")' not in src
    assert "content.main" not in src
    assert "#32" not in src

    band = load_rule_semantics().condition("GOOGLE-TITLE-001").length_band
    assert (band.min, band.max, band.inclusive) == (30, 65, True)
    assert GOOGLE_TITLE_MIN_LENGTH == 30 and GOOGLE_TITLE_MAX_LENGTH == 65


def test_title_override_registry_cannot_downgrade_bundle_versions():
    result = evaluate_google_title(
        TARGET,
        _facts(),
        fact_registry=FactSchemaRegistry({"page": "0"}),
    )

    assert result.readiness.can_evaluate is True
