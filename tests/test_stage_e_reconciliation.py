"""Contract tests for the Stage E/F catalog reconciliation gate (#42)."""
from __future__ import annotations

from pathlib import Path

import yaml

from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.seo.stage_e_reconciliation import (
    ReconciliationClassification,
    STAGE_E_PLAN_REFERENCES,
    build_stage_e_reconciliation_matrix,
    stage_e_binding_is_blocked,
)

ROOT = Path(__file__).parents[1]


def test_stage_e_matrix_is_catalog_authoritative_and_binding_is_disabled():
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    assert matrix["schema"] == "agentready.stage-e-reconciliation.v1"
    assert matrix["authority"] == "catalog-authoritative"
    assert matrix["binding_allowed"] is False
    assert stage_e_binding_is_blocked(matrix)


def test_every_planned_reference_has_an_explicit_disposition():
    assert STAGE_E_PLAN_REFERENCES
    for reference in STAGE_E_PLAN_REFERENCES:
        assert reference.issue in range(22, 34)
        assert reference.planned_rule_id
        assert reference.classification in {
            ReconciliationClassification.MATCH,
            ReconciliationClassification.SEMANTIC_MISMATCH,
            ReconciliationClassification.MISSING_FROM_CATALOG,
            ReconciliationClassification.RETIRED,
            ReconciliationClassification.PLAN_NO_LONGER_APPLICABLE,
            ReconciliationClassification.UNBLOCKED,
            ReconciliationClassification.INTENTIONALLY_UNBOUND,
        }
        assert reference.disposition
        assert reference.planned_semantics


def test_matrix_marks_missing_planned_ids_without_synthesizing_catalog_entries():
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    rows = matrix["rows"]
    missing = [row for row in rows if row["classification"] == "MISSING_FROM_CATALOG"]
    assert not missing
    unbound = [row for row in rows if row["classification"] == "INTENTIONALLY_UNBOUND"]
    assert unbound
    assert all(row["catalog"] is None for row in unbound)


def test_matrix_preserves_catalog_identity_and_metadata_for_existing_ids():
    snapshot = load_rule_catalog_snapshot()
    matrix = build_stage_e_reconciliation_matrix(snapshot)
    assert matrix["catalog"]["catalog_version"] == snapshot.catalog_version
    assert matrix["catalog"]["rule_catalog_digest"] == snapshot.rule_catalog_digest
    row = next(row for row in matrix["rows"] if row["planned_rule_id"] == "CORE-COVERAGE-001")
    assert row["catalog"]["version"] == "1.0.0"
    assert row["catalog"]["fact_requirements"] == [
        {"family": "page", "min_schema_version": "1"},
        {"family": "robots.policy", "min_schema_version": "1"},
    ]
    assert row["catalog"]["applicability_condition"].startswith("applies whenever")
    assert row["planned_semantics"] == (
        "run-scoped guard-only coverage completeness over audit.coverage"
    )
    assert row["effective_contract"]["rule_id"] == "CORE-COVERAGE-001"


def test_no_stage_e_reference_is_silently_treated_as_a_match():
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    assert not any(
        row["classification"] == ReconciliationClassification.MATCH
        for row in matrix["rows"]
    )


def test_binding_gate_cannot_be_bypassed_by_setting_binding_allowed_true():
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    assert stage_e_binding_is_blocked(matrix)
    assert stage_e_binding_is_blocked(
        matrix, issue=22, rule_id="CORE-COVERAGE-001"
    )


def test_binding_gate_is_target_scoped_but_rejects_unresolved_target():
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())

    assert stage_e_binding_is_blocked(
        matrix, issue=22, rule_id="CORE-COVERAGE-001"
    )
    matrix["binding_allowed"] = True
    assert not stage_e_binding_is_blocked(
        matrix, issue=22, rule_id="CORE-COVERAGE-001"
    )
    assert stage_e_binding_is_blocked(
        matrix, issue=23, rule_id="CORE-ROBOTS-001"
    )


def test_existing_catalog_rows_preserve_authored_planned_semantics():
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    rows = {
        (row["issue"], row["planned_rule_id"]): row
        for row in matrix["rows"]
    }
    assert rows[(31, "GOOGLE-DESC-001")]["planned_semantics"] == (
        "catalog-authoritative exact per-rule contract"
    )
    assert rows[(32, "GOOGLE-TITLE-001")]["planned_semantics"] == (
        "catalog-authoritative exact per-rule contract"
    )


def test_binding_gate_rejects_semantic_and_version_mismatches():
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    matrix["binding_allowed"] = True
    row = next(row for row in matrix["rows"] if row["catalog"] is not None)
    row["resolution_status"] = "resolved_catalog_authoritative"
    row["effective_contract"]["version"] = ""
    assert stage_e_binding_is_blocked(matrix)


def test_issue_34_has_an_explicit_issue_level_disposition():
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    assert matrix["issues"] == list(range(22, 35))
    dispositions = matrix["issue_dispositions"]
    assert len(dispositions) == 5
    by_issue = {d["issue"]: d for d in dispositions}
    assert by_issue[23]["classification"] == ReconciliationClassification.RETIRED
    assert by_issue[25]["classification"] == ReconciliationClassification.RETIRED
    assert by_issue[29]["classification"] == ReconciliationClassification.RETIRED
    assert by_issue[30]["classification"] == ReconciliationClassification.INTENTIONALLY_UNBOUND
    assert by_issue[34]["classification"] == ReconciliationClassification.UNBLOCKED
    assert "unblocked" in by_issue[34]["disposition"]


def test_retired_and_unbound_rows_have_terminal_resolution_status():
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    rows_by_id = {row["planned_rule_id"]: row for row in matrix["rows"]}
    assert rows_by_id["CORE-ROBOTS-001"]["resolution_status"] == "retired"
    assert rows_by_id["CORE-ROBOTS-002"]["resolution_status"] == "retired"
    assert rows_by_id["CORE-HTTP-002"]["resolution_status"] == "intentionally_unbound"
    assert rows_by_id["GOOGLE-IDX-001"]["resolution_status"] == "intentionally_unbound"


def test_binding_gate_blocks_retired_and_unbound_rows():
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    assert stage_e_binding_is_blocked(matrix)
    matrix["binding_allowed"] = True
    assert stage_e_binding_is_blocked(matrix, issue=23, rule_id="CORE-ROBOTS-001")
    assert stage_e_binding_is_blocked(matrix, issue=30, rule_id="GOOGLE-IDX-001")


def test_checked_in_matrix_matches_the_loaded_catalog_snapshot():
    expected = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    checked_in = yaml.safe_load((ROOT / "docs" / "stage-e-f-reconciliation.yaml").read_text(encoding="utf-8"))
    assert checked_in == expected
