"""Stage E5 tests: frozen CORE-LINK-001..006 evaluator bindings."""
from __future__ import annotations

import ast
import socket
from dataclasses import replace
from pathlib import Path

import pytest

from agentready.audit_core import (
    CANARY_EVALUATOR_REGISTRY,
    CORE_COVERAGE_RULE_ID,
    CORE_LINK_RULE_VERSION,
    EvaluatorRegistry,
    FactEnvelope,
    FactSchemaRegistry,
    FailurePolicy,
    LINK_EVALUATOR_REGISTRY,
    LINK_EXPECTED_CONTRACTS,
    LINK_RULE_IDS,
    RunFactRecord,
    RunRecord,
    SQLiteSiteStore,
    UnregisteredRuleError,
    bind_link_rule,
    evaluate_link_rule,
)
from agentready.audit_core.link_evaluators import _core_link_001
from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.audit_core.urls import UrlIdentity
from agentready.report_v2 import FindingStatus, semantic_diff

TARGET = "https://example.test/"
OTHER_TARGET = "https://example.test/other"

SCORED_RULES = ("CORE-LINK-001", "CORE-LINK-002", "CORE-LINK-003", "CORE-LINK-005")
DIAGNOSTIC_RULE = "CORE-LINK-004"
OBSERVATION_RULE = "CORE-LINK-006"


def _links_value(
    *,
    internal_count: int = 2,
    external_count: int = 1,
    links: list[dict] | None = None,
):
    if links is None:
        links = [
            {
                "resolved_url": "https://example.test/a",
                "raw_href": "/a",
                "rel": "",
                "element": "a",
            },
            {
                "resolved_url": "https://example.test/b",
                "raw_href": "/b",
                "rel": "next",
                "element": "a",
            },
            {
                "resolved_url": "https://external.test/x",
                "raw_href": "https://external.test/x",
                "rel": "",
                "element": "a",
            },
        ]
    return {"links": links, "internal_count": internal_count, "external_count": external_count}


def _page_value(*, status_code: int = 200, content_type: str = "text/html"):
    return {"status_code": status_code, "content_type": content_type}


def _resources_value(*, resources: list[dict] | None = None):
    if resources is None:
        resources = [
            {
                "url": "/a",
                "resource_type": "stylesheet",
                "resolved_url": "https://example.test/a",
            },
            {
                "url": "/b",
                "resource_type": "script",
                "resolved_url": "https://example.test/b",
            },
        ]
    return {"resources": resources}


def _envelope(family: str, value, *, target: str = TARGET, version: str = "1"):
    return FactEnvelope(
        f"{family}-fact",
        family,
        UrlIdentity.parse(target),
        value,
        "2026-08-22T00:00:00Z",
        schema_family=family,
        schema_version=version,
    )


def _facts(
    rule_id: str,
    *,
    target: str = TARGET,
    links_version: str = "1",
    page_version: str = "1",
    resources_version: str = "1",
    links_value=None,
    page_value=None,
    resources_value=None,
):
    families = LINK_EXPECTED_CONTRACTS[rule_id]["facts"]
    by_family = {
        "links": links_value if links_value is not None else _links_value(),
        "page": page_value if page_value is not None else _page_value(),
        "resources": resources_value if resources_value is not None else _resources_value(),
    }
    versions = {
        "links": links_version,
        "page": page_version,
        "resources": resources_version,
    }
    return tuple(
        _envelope(family, by_family[family], target=target, version=versions[family])
        for family, _ in families
    )


# ---------------------------------------------------------------------------
# positive PASS/FAIL per rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule_id,expected_status",
    [
        ("CORE-LINK-001", FindingStatus.PASS),
        ("CORE-LINK-002", FindingStatus.PASS),
        ("CORE-LINK-003", FindingStatus.PASS),
        ("CORE-LINK-004", FindingStatus.PASS),
        ("CORE-LINK-005", FindingStatus.PASS),
        ("CORE-LINK-006", FindingStatus.PASS),
    ],
)
def test_positive_path_passes_for_every_rule(rule_id, expected_status):
    result = evaluate_link_rule(TARGET, _facts(rule_id), rule_id=rule_id)

    assert result.readiness.can_evaluate is True
    assert result.finding.key.rule_id == rule_id
    assert result.finding.key.rule_version == CORE_LINK_RULE_VERSION
    assert result.report.findings[0].id == rule_id
    assert result.report.findings[0].title == "Core Links check " + rule_id[-3:]
    assert result.report.findings[0].status is expected_status
    assert result.report.coverage.complete_rules == 1


def test_link_001_fails_without_internal_links():
    facts = _facts("CORE-LINK-001", links_value=_links_value(internal_count=0))

    result = evaluate_link_rule(TARGET, facts, rule_id="CORE-LINK-001")

    assert result.report.findings[0].status is FindingStatus.FAIL
    assert result.report.score == 0


def test_link_001_fails_when_page_is_not_a_successful_html_response():
    facts = _facts("CORE-LINK-001", page_value=_page_value(status_code=500))

    result = evaluate_link_rule(TARGET, facts, rule_id="CORE-LINK-001")

    assert result.report.findings[0].status is FindingStatus.FAIL


def test_link_002_fails_on_inconsistent_resource_resolution():
    links_value = _links_value(
        links=[
            {
                "resolved_url": "https://example.test/other",
                "raw_href": "/a",
                "rel": "",
                "element": "a",
            }
        ],
        internal_count=1,
        external_count=0,
    )
    facts = _facts("CORE-LINK-002", links_value=links_value)

    result = evaluate_link_rule(TARGET, facts, rule_id="CORE-LINK-002")

    assert result.report.findings[0].status is FindingStatus.FAIL


def test_link_003_fails_when_no_links_exist():
    facts = _facts(
        "CORE-LINK-003",
        links_value=_links_value(links=[], internal_count=0, external_count=0),
    )

    result = evaluate_link_rule(TARGET, facts, rule_id="CORE-LINK-003")

    assert result.report.findings[0].status is FindingStatus.FAIL


def test_link_004_warns_on_inconclusive_consistency_without_failing():
    facts = _facts("CORE-LINK-004", page_value=_page_value(status_code=500))

    result = evaluate_link_rule(TARGET, facts, rule_id="CORE-LINK-004")

    assert result.report.findings[0].status is FindingStatus.WARN
    assert result.report.findings[0].outcome == "warn"


def test_link_005_fails_on_orphan_declared_resource():
    resources_value = _resources_value(
        resources=[
            {
                "url": "/a",
                "resource_type": "stylesheet",
                "resolved_url": "https://example.test/a",
            },
            {
                "url": "/orphan",
                "resource_type": "script",
                "resolved_url": "https://example.test/orphan",
            },
        ]
    )
    facts = _facts("CORE-LINK-005", resources_value=resources_value)

    result = evaluate_link_rule(TARGET, facts, rule_id="CORE-LINK-005")

    assert result.report.findings[0].status is FindingStatus.FAIL


def test_link_006_observes_outbound_census_and_never_fails():
    facts = _facts("CORE-LINK-006", links_value=_links_value(external_count=7))

    result = evaluate_link_rule(TARGET, facts, rule_id="CORE-LINK-006")

    assert result.report.findings[0].status is FindingStatus.PASS
    assert result.report.findings[0].reason == "observed 7 outbound link(s)"


def test_findings_are_independent_per_rule():
    first = evaluate_link_rule(TARGET, _facts("CORE-LINK-001"), rule_id="CORE-LINK-001")
    second = evaluate_link_rule(TARGET, _facts("CORE-LINK-003"), rule_id="CORE-LINK-003")

    assert first.finding.key != second.finding.key
    assert first.finding.state_hash != second.finding.state_hash


# ---------------------------------------------------------------------------
# missing mandatory facts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule_id,missing_family",
    [
        ("CORE-LINK-001", "links"),
        ("CORE-LINK-001", "page"),
        ("CORE-LINK-002", "links"),
        ("CORE-LINK-002", "page"),
        ("CORE-LINK-002", "resources"),
        ("CORE-LINK-003", "links"),
        ("CORE-LINK-004", "links"),
        ("CORE-LINK-004", "page"),
        ("CORE-LINK-005", "links"),
        ("CORE-LINK-005", "page"),
        ("CORE-LINK-005", "resources"),
        ("CORE-LINK-006", "links"),
    ],
)
def test_missing_mandatory_fact_yields_unavailable(rule_id, missing_family):
    facts = tuple(
        item for item in _facts(rule_id) if item.schema_family != missing_family
    )

    result = evaluate_link_rule(TARGET, facts, rule_id=rule_id)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.findings[0].outcome == "unknown"
    assert result.report.coverage.complete_rules == 0


@pytest.mark.parametrize(
    "rule_id,family",
    [
        ("CORE-LINK-001", "links"),
        ("CORE-LINK-002", "resources"),
        ("CORE-LINK-003", "links"),
        ("CORE-LINK-005", "resources"),
        ("CORE-LINK-006", "links"),
    ],
)
@pytest.mark.parametrize("version", ["0", "unknown"])
def test_old_or_unknown_fact_versions_yield_unavailable(rule_id, family, version):
    versions = {"links": "1", "page": "1", "resources": "1"}
    versions[family] = version
    facts = _facts(
        rule_id,
        links_version=versions["links"],
        page_version=versions["page"],
        resources_version=versions["resources"],
    )

    result = evaluate_link_rule(TARGET, facts, rule_id=rule_id)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.coverage.complete_rules == 0


@pytest.mark.parametrize("rule_id", LINK_RULE_IDS)
def test_override_fact_registry_cannot_upgrade_bundle_versions(rule_id):
    facts = _facts(rule_id, links_version="0")
    override = FactSchemaRegistry({"links": "1", "page": "1", "resources": "1"})

    result = evaluate_link_rule(TARGET, facts, rule_id=rule_id, fact_registry=override)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE
    assert result.report.coverage.complete_rules == 0


# ---------------------------------------------------------------------------
# subject scoping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", LINK_RULE_IDS)
def test_other_target_facts_do_not_satisfy_readiness(rule_id):
    target_facts = _facts(rule_id)
    facts = _facts(rule_id, target=OTHER_TARGET) + target_facts[:-1]

    result = evaluate_link_rule(TARGET, facts, rule_id=rule_id)

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.UNAVAILABLE


@pytest.mark.parametrize("rule_id", ("CORE-LINK-001", "CORE-LINK-003"))
def test_other_target_facts_do_not_influence_evaluation(rule_id):
    facts = _facts(rule_id, target=OTHER_TARGET) + _facts(rule_id)

    result = evaluate_link_rule(TARGET, facts, rule_id=rule_id)

    assert result.readiness.can_evaluate is True
    assert result.report.findings[0].status is FindingStatus.PASS


# ---------------------------------------------------------------------------
# applicability gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", LINK_RULE_IDS)
def test_applicability_gate_skips_before_evaluator_invocation(rule_id):
    calls: list[str] = []

    def spy_evaluator(target, facts):
        calls.append(target)
        raise AssertionError("evaluator must not run for a non-applicable subject")

    registry = EvaluatorRegistry(
        ((rule_id, CORE_LINK_RULE_VERSION, spy_evaluator),),
        allowlist=frozenset({(rule_id, CORE_LINK_RULE_VERSION)}),
    )
    result = evaluate_link_rule(
        TARGET,
        _facts(rule_id),
        rule_id=rule_id,
        subject_kind="origin",
        registry=registry,
    )

    assert result.readiness.can_evaluate is False
    assert result.report.findings[0].status is FindingStatus.SKIP
    assert calls == []


# ---------------------------------------------------------------------------
# registry allowlisting
# ---------------------------------------------------------------------------


def test_canary_registry_rejects_core_link_rules():
    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        CANARY_EVALUATOR_REGISTRY.register(
            "CORE-LINK-001", CORE_LINK_RULE_VERSION, lambda target, facts: None
        )


def test_link_registry_rejects_canary_and_other_rules():
    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        LINK_EVALUATOR_REGISTRY.register(
            CORE_COVERAGE_RULE_ID, "1.0.0", lambda target, facts: None
        )
    with pytest.raises(UnregisteredRuleError, match="not allowlisted"):
        LINK_EVALUATOR_REGISTRY.register(
            "CORE-CANON-002", CORE_LINK_RULE_VERSION, lambda target, facts: None
        )


def test_link_registry_rejects_duplicate_registration():
    from agentready.audit_core.link_evaluators import _core_link_001

    with pytest.raises(Exception, match="already registered"):
        LINK_EVALUATOR_REGISTRY.register(
            "CORE-LINK-001", CORE_LINK_RULE_VERSION, _core_link_001
        )


def test_link_registry_contains_exactly_the_six_frozen_targets():
    assert LINK_EVALUATOR_REGISTRY.registered_targets == tuple(
        (rule_id, CORE_LINK_RULE_VERSION) for rule_id in LINK_RULE_IDS
    )


# ---------------------------------------------------------------------------
# diagnostic / observation contracts
# ---------------------------------------------------------------------------


def test_link_004_stays_diagnostic():
    binding = bind_link_rule(DIAGNOSTIC_RULE)
    entry = load_rule_catalog_snapshot().entry(DIAGNOSTIC_RULE)
    assert entry is not None

    assert binding.projection.score_role == entry.score_role == "diagnostic"
    assert binding.projection.rule_kind == entry.rule_kind == "diagnostic_rule"
    assert binding.projection.failure_policy == entry.failure_policy == "unknown_on_missing_facts"
    assert binding.projection.failure_policy != "block_on_missing_facts"


def test_link_006_stays_observation_only():
    binding = bind_link_rule(OBSERVATION_RULE)
    entry = load_rule_catalog_snapshot().entry(OBSERVATION_RULE)
    assert entry is not None

    assert binding.projection.score_role == entry.score_role == "observation_only"
    assert binding.projection.rule_kind == entry.rule_kind == "observation_rule"
    assert binding.projection.failure_policy == entry.failure_policy == "unknown_on_missing_facts"
    assert binding.projection.failure_policy != "block_on_missing_facts"


@pytest.mark.parametrize("rule_id", [DIAGNOSTIC_RULE, OBSERVATION_RULE])
def test_partial_rules_cannot_carry_block_on_missing_facts(rule_id):
    binding = bind_link_rule(rule_id)
    result = evaluate_link_rule(TARGET, _facts(rule_id), rule_id=rule_id)

    assert binding.projection.failure_policy == "unknown_on_missing_facts"
    assert result.finding.failure_policy is FailurePolicy.PARTIAL_DECISION_ALLOWED
    assert result.finding.failure_policy is not FailurePolicy.BLOCK_ON_MISSING_FACTS


@pytest.mark.parametrize("rule_id", SCORED_RULES)
def test_scored_rules_keep_block_on_missing_facts(rule_id):
    binding = bind_link_rule(rule_id)
    result = evaluate_link_rule(TARGET, _facts(rule_id), rule_id=rule_id)

    assert binding.projection.failure_policy == "block_on_missing_facts"
    assert result.finding.failure_policy is FailurePolicy.BLOCK_ON_MISSING_FACTS


# ---------------------------------------------------------------------------
# no legacy intent.indexability input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", LINK_RULE_IDS)
def test_projection_fact_families_exclude_intent_indexability(rule_id):
    binding = bind_link_rule(rule_id)

    families = tuple(item.family for item in binding.projection.fact_requirements)
    assert "intent.indexability" not in families
    assert all(family in {"links", "page", "resources"} for family in families)


def test_link_002_evaluates_with_only_declared_fact_envelopes():
    """CRITICAL regression: CORE-LINK-002 needs no intent.indexability input."""
    binding = bind_link_rule("CORE-LINK-002")
    assert tuple(item.family for item in binding.projection.fact_requirements) == (
        "links",
        "page",
        "resources",
    )

    facts = _facts("CORE-LINK-002")
    assert {item.schema_family for item in facts} == {"links", "page", "resources"}

    result = evaluate_link_rule(TARGET, facts, rule_id="CORE-LINK-002")

    assert result.readiness.can_evaluate is True
    assert result.report.findings[0].status is FindingStatus.PASS


def test_link_evaluator_module_has_no_transport_or_collection_io_imports():
    path = (
        Path(__file__).parents[1]
        / "src"
        / "agentready"
        / "audit_core"
        / "link_evaluators.py"
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
    source = path.read_text(encoding="utf-8")
    assert "intent.indexability" not in source


# ---------------------------------------------------------------------------
# SQLiteSiteStore replay
# ---------------------------------------------------------------------------


def _persist_and_replay(rule_id: str, facts, tmp_path):
    run_id = f"run-{rule_id.lower()}"
    original = evaluate_link_rule(TARGET, facts, rule_id=rule_id, run_id=run_id)
    path = tmp_path / f"{rule_id.lower()}-replay.sqlite"
    store = SQLiteSiteStore(path)
    try:
        store.begin_run(RunRecord(run_id, "config", "tool", "rules"))
        for envelope in facts:
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
    return original, replayed_facts


@pytest.mark.parametrize("rule_id", ["CORE-LINK-002", "CORE-LINK-006"])
def test_link_rules_replay_persisted_facts_with_network_disabled(rule_id, tmp_path, monkeypatch):
    facts = _facts(rule_id)
    original, replayed_facts = _persist_and_replay(rule_id, facts, tmp_path)

    def fail_network(*args, **kwargs):
        raise AssertionError("offline link replay attempted network access")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    replayed = evaluate_link_rule(
        TARGET, replayed_facts, rule_id=rule_id, run_id=f"run-{rule_id.lower()}"
    )

    assert replayed.finding.key == original.finding.key
    assert replayed.finding.state_hash == original.finding.state_hash
    assert replayed.report.findings[0].status is original.report.findings[0].status


# ---------------------------------------------------------------------------
# semantic_diff identity and catalog propagation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", LINK_RULE_IDS)
def test_semantic_diff_identity_and_catalog_propagation(rule_id):
    result = evaluate_link_rule(TARGET, _facts(rule_id), rule_id=rule_id)
    snapshot = load_rule_catalog_snapshot()

    assert result.report.rule_catalog_version == snapshot.catalog_version
    assert result.report.rule_catalog_digest == snapshot.rule_catalog_digest

    baseline = result.report.to_dict()
    diff = semantic_diff(baseline, baseline)
    assert diff.comparable is True
    assert diff.findings["unchanged"] == (rule_id,)


# ---------------------------------------------------------------------------
# binding identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_id", LINK_RULE_IDS)
def test_binding_uses_catalog_title_verbatim(rule_id):
    binding = bind_link_rule(rule_id)
    entry = load_rule_catalog_snapshot().entry(rule_id)
    assert entry is not None

    assert binding.title == entry.title
    assert binding.title == f"Core Links check {rule_id[-3:]}"


def test_binding_rejects_stale_link_catalog_version():
    snapshot = load_rule_catalog_snapshot()
    stale = replace(
        snapshot,
        entries=tuple(
            replace(item, version="2.0.0") if item.rule_id == "CORE-LINK-001" else item
            for item in snapshot.entries
        ),
    )

    from agentready.audit_core import UnresolvedCatalogTargetError

    with pytest.raises(UnresolvedCatalogTargetError, match="stale"):
        bind_link_rule("CORE-LINK-001", snapshot=stale)
