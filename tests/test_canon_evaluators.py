from __future__ import annotations

import ast
import socket
from dataclasses import replace
from pathlib import Path

import pytest

from agentready.audit_core import (
    CANARY_EVALUATOR_REGISTRY,
    CANON_EVALUATOR_REGISTRY,
    CANON_RULE_IDS,
    CANON_RULE_VERSION,
    CORE_COVERAGE_RULE_ID,
    CORE_COVERAGE_RULE_VERSION,
    FactEnvelope,
    FactSchemaRegistry,
    EvaluatorRegistry,
    RunFactRecord,
    RunRecord,
    SQLiteSiteStore,
    UnregisteredRuleError,
    UnresolvedCatalogTargetError,
    bind_frozen_rule,
    evaluate_canon_rule,
)
from agentready.audit_core.canon_evaluators import _EVALUATORS, _expected_contracts
from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.audit_core.urls import UrlIdentity
from agentready.report_v2 import FindingStatus, semantic_diff

TARGET = "https://example.test/page"
OTHER_TARGET = "https://example.test/other"
ORIGIN = "https://example.test"
CANONICAL = "https://example.test/page"


def _facts(
    *,
    target: str = TARGET,
    page_version: str = "1",
    links_version: str = "1",
    transport_version: str = "1",
    canonicals: list[str] | None = None,
    meta_robots: list[str] | None = None,
    parameter_variants: list[str] | None = None,
    links_payload: dict | None = None,
    transport_payload: dict | None = None,
):
    target_identity = UrlIdentity.parse(target)
    page = FactEnvelope(
        "page-fact",
        "page",
        target_identity,
        {
            "status_code": 200,
            "content_type": "text/html",
            "canonicals": [CANONICAL] if canonicals is None else canonicals,
            "meta_robots": [] if meta_robots is None else meta_robots,
            "parameter_variants": [] if parameter_variants is None else parameter_variants,
        },
        "2026-08-22T00:00:00Z",
        schema_family="page",
        schema_version=page_version,
    )
    links = FactEnvelope(
        "links-fact",
        "links",
        target_identity,
        {"links": []} if links_payload is None else links_payload,
        "2026-08-22T00:00:00Z",
        schema_family="links",
        schema_version=links_version,
    )
    transport = FactEnvelope(
        "transport-fact",
        "transport",
        target_identity,
        {
            "final_url": target,
            "redirect_chain": [target],
            "origin": ORIGIN,
        }
        if transport_payload is None
        else transport_payload,
        "2026-08-22T00:00:00Z",
        schema_family="transport",
        schema_version=transport_version,
    )
    return (page, links, transport)


def _facts_for(rule_id: str, **kwargs):
    """Return only the fact families required by the given rule."""
    required = {
        "CORE-CANON-002": {"page", "links", "transport"},
        "CORE-CANON-003": {"page"},
        "CORE-CANON-004": {"page", "links"},
        "CORE-CANON-005": {"page", "links", "transport"},
        "CORE-CANON-006": {"page"},
        "CORE-CANON-007": {"page", "links"},
        "CORE-CANON-008": {"page", "links", "transport"},
    }[rule_id]
    by_family = {envelope.schema_family: envelope for envelope in _facts(**kwargs)}
    return tuple(by_family[family] for family in required)


# ---------------------------------------------------------------------------
# registry allowlist
# ---------------------------------------------------------------------------


def test_canon_registry_contains_exactly_the_seven_canon_targets():
    assert CANON_EVALUATOR_REGISTRY.registered_targets == tuple(
        (rule_id, CANON_RULE_VERSION) for rule_id in CANON_RULE_IDS
    )


def test_canary_registry_still_contains_exactly_one_target():
    assert CANARY_EVALUATOR_REGISTRY.registered_targets == (
        (CORE_COVERAGE_RULE_ID, CORE_COVERAGE_RULE_VERSION),
    )


def test_canary_registry_rejects_canon_targets():
    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        CANARY_EVALUATOR_REGISTRY.register(
            "CORE-CANON-002", CANON_RULE_VERSION, lambda target, facts: None
        )


def test_canon_registry_rejects_canary_target():
    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        CANON_EVALUATOR_REGISTRY.register(
            CORE_COVERAGE_RULE_ID, CORE_COVERAGE_RULE_VERSION, lambda target, facts: None
        )


def test_canon_registry_rejects_unknown_targets():
    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        CANON_EVALUATOR_REGISTRY.register(
            "CORE-CANON-009", CANON_RULE_VERSION, lambda target, facts: None
        )


def test_canon_registry_rejects_duplicate_registration():
    with pytest.raises(Exception, match="already registered"):
        CANON_EVALUATOR_REGISTRY.register(
            "CORE-CANON-002", CANON_RULE_VERSION, _EVALUATORS["CORE-CANON-002"]
        )


def test_default_registry_allowlist_stays_canary_only():
    registry = EvaluatorRegistry()
    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        registry.register("CORE-CANON-002", CANON_RULE_VERSION, lambda target, facts: None)


# ---------------------------------------------------------------------------
# binding / catalog contract validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", CANON_RULE_IDS)
def test_each_canon_rule_binds_against_the_frozen_catalog(rule_id):
    binding = bind_frozen_rule(rule_id, CANON_RULE_VERSION, registry=CANON_EVALUATOR_REGISTRY)

    assert binding.rule_id == rule_id
    assert binding.version == CANON_RULE_VERSION
    assert binding.projection.rule_id == rule_id
    assert binding.projection.applicability_expression.subject == "html-page"
    assert binding.projection.automation_mode == "automated"


def test_canon_binding_rejects_missing_catalog_target():
    with pytest.raises(UnresolvedCatalogTargetError, match="unresolved"):
        bind_frozen_rule("CORE-CANON-999", CANON_RULE_VERSION, registry=CANON_EVALUATOR_REGISTRY)


def test_canon_binding_rejects_stale_catalog_version():
    snapshot = load_rule_catalog_snapshot()
    stale = replace(
        snapshot,
        entries=tuple(
            replace(item, version="2.0.0") if item.rule_id == "CORE-CANON-002" else item
            for item in snapshot.entries
        ),
    )

    with pytest.raises(UnresolvedCatalogTargetError, match="stale"):
        bind_frozen_rule(
            "CORE-CANON-002", CANON_RULE_VERSION, snapshot=stale, registry=CANON_EVALUATOR_REGISTRY
        )


def test_canon_binding_rejects_drifted_catalog_contract():
    snapshot = load_rule_catalog_snapshot()
    drifted = replace(
        snapshot,
        entries=tuple(
            replace(item, score_role="diagnostic") if item.rule_id == "CORE-CANON-002" else item
            for item in snapshot.entries
        ),
    )

    with pytest.raises(Exception, match="does not match the accepted frozen contract"):
        bind_frozen_rule(
            "CORE-CANON-002",
            CANON_RULE_VERSION,
            snapshot=drifted,
            registry=CANON_EVALUATOR_REGISTRY,
        )


def test_canary_binding_still_validates_its_own_contract():
    binding = bind_frozen_rule(
        CORE_COVERAGE_RULE_ID, CORE_COVERAGE_RULE_VERSION, registry=CANARY_EVALUATOR_REGISTRY
    )
    assert binding.rule_id == CORE_COVERAGE_RULE_ID


# ---------------------------------------------------------------------------
# per-rule positive / negative evaluation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", CANON_RULE_IDS)
def test_positive_path_produces_pass_finding_with_report_identity(rule_id):
    result = evaluate_canon_rule(rule_id, TARGET, _facts_for(rule_id), run_id="run-e2")

    assert result.readiness.can_evaluate is True
    assert result.finding.key.rule_id == rule_id
    assert result.finding.key.rule_version == CANON_RULE_VERSION
    assert result.finding.status.value == "pass"
    assert result.report.findings[0].id == rule_id
    assert result.report.findings[0].status is FindingStatus.PASS
    assert result.report.rule_catalog_version == load_rule_catalog_snapshot().catalog_version
    assert result.report.rule_catalog_digest == load_rule_catalog_snapshot().rule_catalog_digest
    assert result.report.coverage.complete_rules == 1


@pytest.mark.parametrize(
    "rule_id,kwargs",
    [
        ("CORE-CANON-002", {"canonicals": ["https://other.test/page"]}),
        ("CORE-CANON-003", {"meta_robots": ["noindex"]}),
        ("CORE-CANON-004", {"links_payload": {"redirect_chain": [CANONICAL, TARGET]}}),
        (
            "CORE-CANON-005",
            {
                "links_payload": {"rel_values": ["next"]},
                "transport_payload": {
                    "final_url": "https://example.test/page?page=2",
                    "redirect_chain": [TARGET],
                    "origin": ORIGIN,
                },
            },
        ),
        ("CORE-CANON-006", {"parameter_variants": ["https://example.test/page?utm=x"]}),
        (
            "CORE-CANON-007",
            {
                "canonicals": ["https://cdn.test/canonical"],
                "links_payload": {
                    "origin": ORIGIN,
                    "cross_domain_targets": ["https://mirror.test/canonical"],
                },
            },
        ),
        ("CORE-CANON-008", {"canonicals": [CANONICAL, "https://example.test/alt"]}),
    ],
)
def test_fail_paths_are_independent_per_rule(rule_id, kwargs):
    result = evaluate_canon_rule(rule_id, TARGET, _facts_for(rule_id, **kwargs))

    assert result.readiness.can_evaluate is True
    assert result.finding.status.value == "fail"
    assert result.report.findings[0].status is FindingStatus.FAIL
    assert result.report.findings[0].id == rule_id


@pytest.mark.parametrize("rule_id", CANON_RULE_IDS)
@pytest.mark.parametrize(
    "missing_family",
    ["page", "links", "transport"],
)
def test_missing_mandatory_fact_blocks_confident_evaluation(rule_id, missing_family):
    facts = tuple(
        item for item in _facts_for(rule_id) if item.schema_family != missing_family
    )

    result = evaluate_canon_rule(rule_id, TARGET, facts)

    if missing_family not in {item.schema_family for item in _facts_for(rule_id)}:
        pytest.skip(f"{rule_id} does not require {missing_family}")
    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.findings[0].outcome == "unknown"
    assert result.report.coverage.complete_rules == 0


@pytest.mark.parametrize("rule_id", CANON_RULE_IDS)
@pytest.mark.parametrize(
    "version_kwargs",
    [
        {"page_version": "0"},
        {"page_version": "unknown"},
        {"links_version": "0"},
        {"transport_version": "unknown"},
    ],
)
def test_old_or_unknown_fact_versions_block_confident_evaluation(rule_id, version_kwargs):
    required = {item.schema_family for item in _facts_for(rule_id)}
    touched = {
        key.split("_")[0] for key in version_kwargs if version_kwargs[key] != "1"
    }
    if not touched & required:
        pytest.skip(f"{rule_id} does not require {touched}")

    result = evaluate_canon_rule(rule_id, TARGET, _facts_for(rule_id, **version_kwargs))

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE


@pytest.mark.parametrize("rule_id", CANON_RULE_IDS)
def test_override_registry_cannot_upgrade_old_bundle_versions(rule_id):
    result = evaluate_canon_rule(
        rule_id,
        TARGET,
        _facts_for(rule_id, page_version="0"),
        fact_registry=FactSchemaRegistry(
            {"page": "1", "links": "1", "transport": "1"},
        ),
    )

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.coverage.complete_rules == 0


@pytest.mark.parametrize("rule_id", CANON_RULE_IDS)
def test_subject_scoping_ignores_other_target_facts(rule_id):
    facts = _facts_for(rule_id, target=OTHER_TARGET) + _facts_for(rule_id)

    result = evaluate_canon_rule(rule_id, TARGET, facts)

    assert result.readiness.can_evaluate is True
    assert result.finding.status.value == "pass"


@pytest.mark.parametrize("rule_id", CANON_RULE_IDS)
def test_other_target_facts_do_not_satisfy_readiness(rule_id):
    target_facts = _facts_for(rule_id)
    facts = _facts_for(rule_id, target=OTHER_TARGET) + target_facts[:-1]

    result = evaluate_canon_rule(rule_id, TARGET, facts)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE


@pytest.mark.parametrize("rule_id", CANON_RULE_IDS)
def test_applicability_is_resolved_before_evaluator_invocation(rule_id):
    calls: list[str] = []

    def spy_evaluator(target, facts):
        calls.append(target)
        raise AssertionError("evaluator must not run for a non-applicable subject")

    registry = EvaluatorRegistry(
        allowlist=frozenset({(rule_id, CANON_RULE_VERSION)}),
        expected_contracts=_expected_contracts(),
    )
    registry.register(rule_id, CANON_RULE_VERSION, spy_evaluator)

    result = evaluate_canon_rule(
        rule_id,
        TARGET,
        _facts_for(rule_id),
        subject_kind="origin",
        registry=registry,
    )

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.SKIP
    assert calls == []


# ---------------------------------------------------------------------------
# diagnostic / observation semantics
# ---------------------------------------------------------------------------


def test_diagnostic_rule_missing_facts_yield_unknown_not_confident_fail():
    result = evaluate_canon_rule("CORE-CANON-004", TARGET, (_facts()[0],))

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.findings[0].outcome == "unknown"


def test_observation_rule_missing_facts_yield_unknown_not_confident_fail():
    result = evaluate_canon_rule("CORE-CANON-006", TARGET, ())

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.findings[0].outcome == "unknown"


def test_diagnostic_and_observation_rules_keep_cataloged_rule_kind():
    snapshot = load_rule_catalog_snapshot()
    diagnostic = snapshot.entry("CORE-CANON-004")
    observation = snapshot.entry("CORE-CANON-006")
    assert diagnostic is not None and observation is not None
    assert diagnostic.rule_kind == "diagnostic_rule"
    assert diagnostic.score_role == "diagnostic"
    assert observation.rule_kind == "observation_rule"
    assert observation.score_role == "observation_only"
    # The registry allowlist is keyed by exact target, so a diagnostic or
    # observation rule can never be registered into a scored slot.
    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        CANARY_EVALUATOR_REGISTRY.register(
            "CORE-CANON-004", CANON_RULE_VERSION, lambda target, facts: None
        )


def test_failure_policy_mapping_is_deterministic():
    snapshot = load_rule_catalog_snapshot()
    for rule_id in CANON_RULE_IDS:
        entry = snapshot.entry(rule_id)
        assert entry is not None
        if entry.failure_policy == "block_on_missing_facts":
            assert entry.failure_policy == "block_on_missing_facts"
        else:
            assert entry.failure_policy == "unknown_on_missing_facts"


# ---------------------------------------------------------------------------
# replay through SQLiteSiteStore with network disabled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", ["CORE-CANON-002", "CORE-CANON-006"])
def test_canon_rules_replay_persisted_facts_with_network_disabled(tmp_path, monkeypatch, rule_id):
    run_id = f"run-e2-replay-{rule_id}"
    original_facts = _facts_for(rule_id)
    original = evaluate_canon_rule(rule_id, TARGET, original_facts, run_id=run_id)
    path = tmp_path / "e2-replay.sqlite"
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
        raise AssertionError("offline E2 replay attempted network access")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    replayed = evaluate_canon_rule(rule_id, TARGET, replayed_facts, run_id=run_id)

    assert replayed.finding.key == original.finding.key
    assert replayed.finding.state_hash == original.finding.state_hash
    assert replayed.report.findings[0].id == rule_id
    assert replayed.report.findings[0].status is FindingStatus.PASS


# ---------------------------------------------------------------------------
# report / diff identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", CANON_RULE_IDS)
def test_report_diff_identity_is_stable_per_rule(rule_id):
    result = evaluate_canon_rule(rule_id, TARGET, _facts_for(rule_id))
    baseline = result.report.to_dict()

    diff = semantic_diff(baseline, baseline)

    assert diff.comparable is True
    assert diff.findings["unchanged"] == (rule_id,)


@pytest.mark.parametrize("rule_id", CANON_RULE_IDS)
def test_report_carries_catalog_identity(rule_id):
    snapshot = load_rule_catalog_snapshot()
    result = evaluate_canon_rule(rule_id, TARGET, _facts_for(rule_id))

    assert result.report.rule_catalog_version == snapshot.catalog_version
    assert result.report.rule_catalog_digest == snapshot.rule_catalog_digest


# ---------------------------------------------------------------------------
# purity
# ---------------------------------------------------------------------------


def test_canon_evaluator_module_has_no_transport_or_collection_io_imports():
    path = Path(__file__).parents[1] / "src" / "agentready" / "audit_core" / "canon_evaluators.py"
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
