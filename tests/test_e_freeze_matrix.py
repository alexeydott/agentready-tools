"""Stage 3 golden-matrix freeze (#34).

Compares the LIVE rule-catalog / semantics-artifact / evaluator-registry /
score-model state against the frozen post-E-waves baseline
(`docs/baseline-after-e-wave.json`). ANY drift fails and requires an explicit
governance re-freeze of the baseline artifact.

Targeted exact-HEAD suite:

    python -m pytest tests/test_e_freeze_matrix.py -q

"""

from __future__ import annotations

import json
import pathlib

import pytest

from agentready.audit_core.canon_evaluators import CANON_EVALUATOR_REGISTRY
from agentready.audit_core.evaluator_registry import CANARY_EVALUATOR_REGISTRY
from agentready.audit_core.google_desc_evaluators import (
    GOOGLE_DESC_EVALUATOR_REGISTRY,
)
from agentready.audit_core.google_title_evaluators import (
    GOOGLE_TITLE_EVALUATOR_REGISTRY,
)
from agentready.audit_core.link_evaluators import LINK_EVALUATOR_REGISTRY
from agentready.audit_core.google_href_evaluators import (
    GOOGLE_HREF_EVALUATOR_REGISTRY,
)
from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.seo.rules.catalog import compute_catalog_digest, load_rule_semantics
from agentready.seo.stage_e_reconciliation import (
    ReconciliationClassification,
    STAGE_E_PLAN_REFERENCES,
    build_stage_e_reconciliation_matrix,
    stage_e_binding_is_blocked,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE = json.loads(
    (REPO_ROOT / "docs" / "baseline-after-e-wave.json").read_text(encoding="utf-8")
)

REGISTRIES = {
    "CANARY": CANARY_EVALUATOR_REGISTRY,
    "CANON": CANON_EVALUATOR_REGISTRY,
    "LINK_BOUND": LINK_EVALUATOR_REGISTRY,
    "GOOGLE_DESC": GOOGLE_DESC_EVALUATOR_REGISTRY,
    "GOOGLE_HREF": GOOGLE_HREF_EVALUATOR_REGISTRY,
    "GOOGLE_TITLE": GOOGLE_TITLE_EVALUATOR_REGISTRY,
}


def _targets(reg):
    return sorted(f"{rid}@{ver}" for rid, ver in reg.registered_targets)


def test_frozen_catalog_is_unchanged():
    snap = load_rule_catalog_snapshot()
    base = BASELINE["rule_catalog"]
    assert snap.catalog_version == base["version"]
    assert snap.rule_catalog_digest == base["digest"]
    assert snap.rule_count == base["rule_count"]


def test_semantics_artifact_pin_tracks_the_same_catalog():
    from agentready.seo.rules.catalog import load_rule_semantics as _lrs

    snap = load_rule_catalog_snapshot()
    doc = _lrs(snap)
    assert doc.digest == BASELINE["semantics_artifact"]["digest"]
    assert (
        doc.catalog_version
        == BASELINE["rule_catalog"]["version"]
        == snap.catalog_version
    )


def test_registered_evaluator_targets_are_frozen():
    for name, reg in REGISTRIES.items():
        expected = sorted(BASELINE["registered_evaluators"][name]["targets"])
        got = _targets(reg)
        assert got == expected, f"{name}: registry targets drifted: {set(got) ^ set(expected)}"


def test_score_model_id_is_frozen():
    """P1 (review): live runtime default must equal the frozen baseline value."""
    import dataclasses

    from agentready.audit_core.run_context import AuditRunContext

    field = next(
        f for f in dataclasses.fields(AuditRunContext) if f.name == "score_model_id"
    )
    live_score_model_id = field.default
    assert live_score_model_id == BASELINE["score_projection"]["score_model_id"]
    assert live_score_model_id == "readiness-transparent-v2"


def test_deferred_declared_not_produced_set_is_frozen():
    """Deferred set includes HREF-002/005 (cross-page facts unavailable)."""
    deferred = {item["rule_id"] for item in BASELINE["deferred_declared_not_produced"]}
    assert deferred == {"GOOGLE-HREF-002", "GOOGLE-HREF-005"}


def test_frozen_retired_set_is_frozen():
    """Retired set matches baseline: issues #23, #25, #29 — exact per-issue mappings."""
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    retired_rows = [
        row for row in matrix["rows"]
        if row["classification"] == ReconciliationClassification.RETIRED
    ]
    retired_pairs = {(row["issue"], row["planned_rule_id"]) for row in retired_rows}
    baseline_pairs = set()
    for issue_key, issue_num in [("issue_23", 23), ("issue_25", 25), ("issue_29", 29)]:
        for rid in BASELINE["frozen_retired"][issue_key]["rule_ids"]:
            baseline_pairs.add((issue_num, rid))
    assert retired_pairs == baseline_pairs


def test_frozen_intentionally_unbound_set_is_frozen():
    """Intentionally unbound set matches baseline: issue #30 — exact per-issue mappings."""
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    unbound_rows = [
        row for row in matrix["rows"]
        if row["classification"] == ReconciliationClassification.INTENTIONALLY_UNBOUND
    ]
    unbound_pairs = {(row["issue"], row["planned_rule_id"]) for row in unbound_rows}
    baseline_pairs = set()
    for issue_key, issue_num in [("issue_30", 30)]:
        for rid in BASELINE["frozen_intentionally_unbound"][issue_key]["rule_ids"]:
            baseline_pairs.add((issue_num, rid))
    assert unbound_pairs == baseline_pairs


def test_retired_rows_have_terminal_resolution_status():
    """RETIRED rows must have resolution_status=retired (governance resolved)."""
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    retired_rows = [
        row for row in matrix["rows"]
        if row["classification"] == ReconciliationClassification.RETIRED
    ]
    assert retired_rows
    for row in retired_rows:
        assert row["resolution_status"] == "retired"


def test_intentionally_unbound_rows_have_terminal_resolution_status():
    """INTENTIONALLY_UNBOUND rows must have resolution_status=intentionally_unbound."""
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    unbound_rows = [
        row for row in matrix["rows"]
        if row["classification"] == ReconciliationClassification.INTENTIONALLY_UNBOUND
    ]
    assert unbound_rows
    for row in unbound_rows:
        assert row["resolution_status"] == "intentionally_unbound"


def test_retired_rows_are_never_bindable():
    """RETIRED rows must remain blocked for binding even when binding_allowed=True."""
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    matrix["binding_allowed"] = True
    retired_rows = [
        row for row in matrix["rows"]
        if row["classification"] == ReconciliationClassification.RETIRED
    ]
    for row in retired_rows:
        assert stage_e_binding_is_blocked(
            matrix, issue=row["issue"], rule_id=row["planned_rule_id"]
        ), f"{row['planned_rule_id']} should be blocked for binding"


def test_intentionally_unbound_rows_are_never_bindable():
    """INTENTIONALLY_UNBOUND rows must remain blocked for binding even when binding_allowed=True."""
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    matrix["binding_allowed"] = True
    unbound_rows = [
        row for row in matrix["rows"]
        if row["classification"] == ReconciliationClassification.INTENTIONALLY_UNBOUND
    ]
    for row in unbound_rows:
        assert stage_e_binding_is_blocked(
            matrix, issue=row["issue"], rule_id=row["planned_rule_id"]
        ), f"{row['planned_rule_id']} should be blocked for binding"


def test_no_duplicate_rule_ids_across_all_sets():
    """No bound rule ID appears in retired or unbound sets (retired↔unbound overlap is allowed)."""
    bound_ids = set()
    for name in REGISTRIES:
        for rid, ver in REGISTRIES[name].registered_targets:
            bound_ids.add(rid)
    deferred_ids = {item["rule_id"] for item in BASELINE["deferred_declared_not_produced"]}
    retired_ids = set()
    for issue_key in ["issue_23", "issue_25", "issue_29"]:
        retired_ids.update(BASELINE["frozen_retired"][issue_key]["rule_ids"])
    unbound_ids = set()
    for issue_key in ["issue_30"]:
        unbound_ids.update(BASELINE["frozen_intentionally_unbound"][issue_key]["rule_ids"])
    bound_vs_others = bound_ids & (deferred_ids | retired_ids | unbound_ids)
    assert not bound_vs_others, (
        f"Bound rules found in retired/unbound/deferred: {bound_vs_others}"
    )


def test_retired_issue_rule_entry_count():
    """18 issue-scoped retirement entries across #23 (10), #25 (2), #29 (6)."""
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    retired_rows = [
        row for row in matrix["rows"]
        if row["classification"] == ReconciliationClassification.RETIRED
    ]
    by_issue = {}
    for row in retired_rows:
        by_issue.setdefault(row["issue"], []).append(row["planned_rule_id"])
    assert len(by_issue[23]) == 10
    assert len(by_issue[25]) == 2
    assert len(by_issue[29]) == 6
    total_entries = sum(len(v) for v in by_issue.values())
    assert total_entries == 18


def test_retired_unique_ids_count():
    """14 unique retired rule IDs (4 shared between #23 and #29)."""
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    retired_rows = [
        row for row in matrix["rows"]
        if row["classification"] == ReconciliationClassification.RETIRED
    ]
    unique_ids = {row["planned_rule_id"] for row in retired_rows}
    assert len(unique_ids) == 14


def test_retired_shared_ids_between_23_and_29():
    """CORE-ROBOTS-003/004, CORE-SITEMAP-005/008 are shared between #23 and #29."""
    matrix = build_stage_e_reconciliation_matrix(load_rule_catalog_snapshot())
    retired_rows = [
        row for row in matrix["rows"]
        if row["classification"] == ReconciliationClassification.RETIRED
    ]
    ids_23 = {row["planned_rule_id"] for row in retired_rows if row["issue"] == 23}
    ids_29 = {row["planned_rule_id"] for row in retired_rows if row["issue"] == 29}
    shared = ids_23 & ids_29
    assert shared == {"CORE-ROBOTS-003", "CORE-ROBOTS-004", "CORE-SITEMAP-005", "CORE-SITEMAP-008"}


def test_all_plan_references_have_disposition():
    """Every STAGE_E_PLAN_REFERENCE has a non-empty disposition."""
    for ref in STAGE_E_PLAN_REFERENCES:
        assert ref.disposition, f"Issue #{ref.issue} rule {ref.planned_rule_id} has no disposition"


def test_all_plan_references_have_terminal_classification():
    """Every STAGE_E_PLAN_REFERENCE has a classification that is terminal."""
    terminal = {
        ReconciliationClassification.RETIRED,
        ReconciliationClassification.INTENTIONALLY_UNBOUND,
        ReconciliationClassification.SEMANTIC_MISMATCH,
        ReconciliationClassification.MATCH,
    }
    for ref in STAGE_E_PLAN_REFERENCES:
        assert ref.classification in terminal, (
            f"Issue #{ref.issue} rule {ref.planned_rule_id} has non-terminal classification {ref.classification}"
        )
