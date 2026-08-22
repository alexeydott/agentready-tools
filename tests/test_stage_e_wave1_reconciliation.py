"""Verification gates for the Stage E wave-1 reconciliation matrix (#50).

Checked-in artifact: ``docs/stage-e-wave1-reconciliation.yaml``.

These tests enforce, deterministically and offline, that the reconciliation
matrix stays consistent with the frozen catalog snapshot and with the real
produced-fact contract at the accepted base:

* exact wave coverage and per-row identity against the live snapshot;
* catalog digest/version equality (no catalog byte changed by #50);
* structural completeness and enum validity of every row;
* separation of catalog-authored semantics from proposed conditions
  (unaccepted semantics cannot bind authoritatively);
* absence of emitters for the unproducible fact families, so gaps stay
  explicit instead of being synthesized by evaluators.

Targeted exact-HEAD suite (gate 11):

    python -m pytest tests/test_stage_e_wave1_reconciliation.py tests/test_rule_catalog_integrity.py -q

"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from agentready.audit_core.collection import (
    parsed_facts_from_dict,
    parsed_facts_to_dict,
)
from agentready.audit_core.fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS
from agentready.audit_core.rule_catalog import RuleCatalogEntry, load_rule_catalog_snapshot

MATRIX_RELPATH = Path("docs") / "stage-e-wave1-reconciliation.yaml"
REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO_ROOT / MATRIX_RELPATH

EXPECTED_WAVE_IDS = frozenset(
    {
        "CORE-CANON-002",
        "CORE-CANON-003",
        "CORE-CANON-004",
        "CORE-CANON-005",
        "CORE-CANON-006",
        "CORE-CANON-007",
        "CORE-CANON-008",
        "CORE-LINK-001",
        "CORE-LINK-002",
        "CORE-LINK-003",
        "CORE-LINK-004",
        "CORE-LINK-005",
        "CORE-LINK-006",
        "GOOGLE-DESC-001",
        "GOOGLE-TITLE-001",
    }
)

REQUIRED_ROW_KEYS = (
    "rule_id",
    "version",
    "module",
    "catalog_title",
    "scope",
    "fact_requirements",
    "score_role",
    "failure_policy",
    "mechanism",
    "rule_kind",
    "automation_mode",
    "authoritative_executable_condition",
    "producers",
    "missing_behavior",
    "match_status",
    "disposition",
    "disposition_detail",
    "required_change",
    "owning_ref",
)

MATCH_STATUS_VALUES = {
    "MATCH",
    "SEMANTIC_MISMATCH",
    "MISSING_PRODUCED_FIELD",
    "UNGOVERNED_THRESHOLD",
    "BLOCKED",
}
DISPOSITION_VALUES = {"A", "B", "C", "D"}

EXECUTABLE_CONDITION_SURFACE = (
    "executable_condition",
    "conditions",
    "thresholds",
    "params",
    "assertions",
)


def _load_matrix() -> dict:
    return yaml.safe_load(MATRIX_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix() -> dict:
    return _load_matrix()


@pytest.fixture(scope="module")
def rules(matrix) -> dict[str, dict]:
    return {row["rule_id"]: row for row in matrix["rules"]}


@pytest.fixture(scope="module")
def snapshot():
    return load_rule_catalog_snapshot()


def test_matrix_covers_exactly_the_wave_rules(rules, snapshot) -> None:
    assert set(rules) == EXPECTED_WAVE_IDS
    for rule_id, row in rules.items():
        entry = snapshot.entry(rule_id)
        assert entry is not None, rule_id
        assert row["version"] == entry.version, rule_id


def test_matrix_identity_matches_live_snapshot(matrix, snapshot) -> None:
    catalog = matrix["rule_catalog"]
    assert catalog["name"] == "agentready.rule-catalog.v2"
    assert catalog["version"] == snapshot.catalog_version
    assert catalog["digest"] == snapshot.rule_catalog_digest
    assert re.fullmatch(r"[0-9a-f]{40}", matrix["accepted_base"])


def test_rows_are_structurally_complete_and_synced(rules, snapshot) -> None:
    for rule_id, row in rules.items():
        for key in REQUIRED_ROW_KEYS:
            assert key in row, f"{rule_id}: missing {key}"
        entry = snapshot.entry(rule_id)
        assert row["catalog_title"] == entry.title, rule_id
        assert row["module"] == entry.module, rule_id
        assert row["score_role"] == entry.score_role, rule_id
        assert row["failure_policy"] == entry.failure_policy, rule_id
        assert row["mechanism"] == entry.mechanism, rule_id
        assert row["rule_kind"] == entry.rule_kind, rule_id
        assert row["automation_mode"] == entry.automation_mode, rule_id
        declared = [(req.family, req.min_schema_version) for req in entry.fact_requirements]
        recorded = [(req["family"], str(req["min_schema_version"])) for req in row["fact_requirements"]]
        assert recorded == declared, rule_id


def test_row_enums_are_valid(rules) -> None:
    for rule_id, row in rules.items():
        assert row["match_status"] in MATCH_STATUS_VALUES, rule_id
        assert row["disposition"] in DISPOSITION_VALUES, rule_id


def test_gate6_no_hidden_thresholds_outside_governance(rules) -> None:
    ungoverned = {"GOOGLE-DESC-001", "GOOGLE-TITLE-001"}
    for rule_id, row in rules.items():
        authoritative = row["authoritative_executable_condition"]
        if rule_id in ungoverned:
            assert authoritative is None, rule_id
            proposed = row["proposed_executable_condition"]
            assert proposed is not None and proposed["governance_status"] == "proposed", rule_id
            band = proposed.get("length_band_part")
            assert band is not None, rule_id
            assert "NOT runtime evidence until governed" in band["threshold_source"], rule_id
            continue
        if authoritative is None:
            assert row["proposed_executable_condition"] is not None, rule_id
            assert (
                row["proposed_executable_condition"]["governance_status"] == "proposed"
            ), rule_id


def test_canon008_is_the_only_catalog_derived_condition(rules) -> None:
    derived = {
        rule_id
        for rule_id, row in rules.items()
        if row["authoritative_executable_condition"] is not None
    }
    assert derived == {"CORE-CANON-008"}
    block = rules["CORE-CANON-008"]["authoritative_executable_condition"]
    assert block["governance_status"] == "catalog_derived"
    assert "title" in block["source"]


def test_proposed_link_contracts_define_decision_space(rules) -> None:
    for rule_id in sorted(r for r in EXPECTED_WAVE_IDS if r.startswith("CORE-LINK-")):
        proposed = rules[rule_id]["proposed_executable_condition"]
        assert proposed["governance_status"] == "proposed", rule_id
        assert "intent" in proposed, rule_id
        positive = proposed.get("positive") or proposed.get("positive_or_census")
        assert positive, rule_id
        assert ("negative" in proposed) or ("warn" in proposed), rule_id
        assert "indeterminate" in proposed, rule_id
        assert proposed.get("evidence_fields"), rule_id


def test_gate7_unaccepted_semantics_cannot_bind_authoritatively(rules, matrix) -> None:
    entry_fields = set(RuleCatalogEntry.__dataclass_fields__)
    assert entry_fields.isdisjoint(EXECUTABLE_CONDITION_SURFACE)
    assert "condition" in entry_fields  # applicability prose only
    for rule_id, row in rules.items():
        proposed = row["proposed_executable_condition"]
        if proposed is None:
            continue
        assert proposed["governance_status"] == "proposed", rule_id
    authority = matrix["authority"]
    assert authority["catalog_authored_is_authoritative"] is True
    assert authority["proposed_conditions_are_not_authoritative"] is True
    assert authority["binding_requires_accepted_governance_path"] is True


def test_gate8_unproducible_family_emitters_stay_absent() -> None:
    families = ("links", "transport", "resources", "structured-data")
    for family in families:
        assert DEFAULT_FACT_SCHEMA_VERSIONS.get(family) == "1"
    pattern = re.compile(
        r"\b(?:schema_family|kind)\s*(:|=)(?!=)\s*[\"'](?:" + "|".join(families) + r")[\"']"
    )
    offenders: list[str] = []
    for path in (REPO_ROOT / "src" / "agentready").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], "unexpected envelope emitters for unproducible families"


def test_gate4_page_producer_roundtrip_preserves_wave_evidence_fields() -> None:
    payload = {
        "titles": ["Example Domain"],
        "descriptions": ["Example domain meta description"],
        "meta_robots": ["noindex, follow"],
        "canonicals": ["https://example.com/"],
        "links": [
            {
                "source_representation_id": "primary",
                "ordinal": 0,
                "raw_href": "/next",
                "resolved_url": "https://example.com/next",
                "anchor_text": "Next",
                "rel": "next",
                "element": "a",
            }
        ],
    }
    facts = parsed_facts_from_dict(payload)
    restored = parsed_facts_to_dict(facts)
    assert restored["titles"] == ("Example Domain",)
    assert restored["descriptions"] == ("Example domain meta description",)
    assert restored["canonicals"] == ("https://example.com/",)
    assert restored["meta_robots"] == ("noindex, follow",)
    link = restored["links"][0]
    assert link["raw_href"] == "/next"
    assert link["resolved_url"] == "https://example.com/next"
    assert link["rel"] == "next"


def test_pr_disposition_keeps_wave_blocked(matrix) -> None:
    blocked = matrix["pr_disposition_while_open"]
    assert set(blocked) == {"#46", "#47", "#48", "#49"}
    for ref, note in blocked.items():
        assert note.startswith("BLOCKED"), ref


def test_verification_gates_are_recorded(matrix) -> None:
    gates = matrix["verification_gates"]
    for index in range(1, 13):
        assert any(key.startswith(f"gate{index}_") for key in gates), index
