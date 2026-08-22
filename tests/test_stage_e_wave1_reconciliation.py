"""Verification gates for the Stage E wave-1 reconciliation matrix (#50).

Checked-in artifact: ``docs/stage-e-wave1-reconciliation.yaml``.

These tests enforce, deterministically and offline, that the reconciliation
matrix stays consistent with the frozen catalog snapshot and with the real
produced-fact contract at the accepted base:

* exact wave coverage and per-row identity against the live snapshot,
  including the exact applicability contract (scope AND condition);
* catalog digest/version equality (no catalog byte changed by #50);
* structural completeness, enum validity, and per-evidence-token provenance;
* declared-family evidence admissibility: any evidence token outside the
  rule's declared families must be explicitly wired to a governing issue;
* separation of catalog-authored semantics from proposed conditions
  (unaccepted semantics cannot bind authoritatively; this PR is not an
  acceptance mechanism);
* absence of emitters for the unproducible fact families via an AST scan of
  pipeline modules plus an assignment-form regex lock, with the documented
  adapter boundary checked against reality.

Targeted exact-HEAD suite (gate 11):

    python -m pytest tests/test_stage_e_wave1_reconciliation.py tests/test_rule_catalog_integrity.py -q

"""

from __future__ import annotations

import ast
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
from agentready.audit_core import run_facts as run_facts_module

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
    "applicability_condition",
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
    "paths",
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

# Evidence token prefixes that are identity inputs rather than observations.
IDENTITY_PREFIXES = {"subject"}
PIPELINE_MODULES = ("collection.py", "crawler.py", "discovery.py", "run_facts.py", "store.py")


def _evidence_tokens(row: dict) -> set[str]:
    tokens: set[str] = set()
    for block_key in ("authoritative_executable_condition", "proposed_executable_condition"):
        block = row.get(block_key)
        if isinstance(block, dict):
            tokens.update(block.get("evidence_fields") or ())
    return tokens


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


def test_rows_record_exact_applicability_contract(rules, snapshot) -> None:
    """P0: scope and applicability condition must match the snapshot exactly."""
    for rule_id, row in rules.items():
        entry = snapshot.entry(rule_id)
        assert row["scope"] == entry.scope, rule_id
        assert row["applicability_condition"] == entry.condition, rule_id


def test_followup_issues_are_wired(matrix) -> None:
    followups = matrix["followup_issues"]
    for key in (
        "gov_canonical",
        "gov_links",
        "gov_google_desc",
        "gov_google_title",
        "fact_transport",
        "fact_projections_resources",
    ):
        assert re.fullmatch(r"#\d+", followups[key]), key
    authority = matrix["authority"]
    assert authority["this_pr_is_not_an_acceptance_mechanism"] is True
    assert authority["declared_family_evidence_rule"] is True


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
        assert row["paths"], rule_id
        for path in row["paths"]:
            assert path[0] in DISPOSITION_VALUES or path.startswith(("A-", "D-")), (rule_id, path)


def test_gate6_thresholds_are_normative_only_in_the_artifact(rules) -> None:
    ungoverned = {"GOOGLE-DESC-001", "GOOGLE-TITLE-001"}
    for rule_id, row in rules.items():
        authoritative = row["authoritative_executable_condition"]
        if rule_id in ungoverned:
            assert authoritative is None, rule_id
            proposed = row["proposed_executable_condition"]
            assert proposed is not None and proposed["governance_status"] == "accepted", rule_id
            band = proposed.get("length_band_part")
            assert band is not None, rule_id
            assert (
                "normative numbers live in agentready.rule-semantics.v2"
                in band["threshold_source"]
            ), rule_id
            continue
        if authoritative is None:
            assert row["proposed_executable_condition"] is not None, rule_id
            assert (
                row["proposed_executable_condition"]["governance_status"] == "accepted"
            ), rule_id


def test_canon008_is_deferred_not_path_a(rules) -> None:
    """P0: semantic MATCH stands but binding readiness is blocked -> Path D."""
    row = rules["CORE-CANON-008"]
    assert row["match_status"] == "MATCH"
    assert row["disposition"] == "D"
    assert "blocked" in row["binding_readiness"]
    derived = {
        rule_id
        for rule_id, item in rules.items()
        if item["authoritative_executable_condition"] is not None
    }
    assert derived == {"CORE-CANON-008"}


def test_proposed_link_contracts_define_decision_space(rules) -> None:
    for rule_id in sorted(r for r in EXPECTED_WAVE_IDS if r.startswith("CORE-LINK-")):
        proposed = rules[rule_id]["proposed_executable_condition"]
        assert proposed["governance_status"] == "accepted", rule_id
        assert "intent" in proposed, rule_id
        positive = proposed.get("positive") or proposed.get("positive_or_census")
        assert positive, rule_id
        assert ("negative" in proposed) or ("warn" in proposed), rule_id
        assert "indeterminate" in proposed, rule_id
        assert proposed.get("evidence_fields"), rule_id


def test_every_evidence_token_has_provenance(rules) -> None:
    """P0: producers must cover every consumed evidence field, LINK rows included."""
    for rule_id, row in rules.items():
        producers = row["producers"]
        assert producers, f"{rule_id}: empty provenance"
        for token in _evidence_tokens(row):
            assert token in producers, f"{rule_id}: no provenance for {token}"
            entry = producers[token]
            assert "producer" in entry and "scoping" in entry, (rule_id, token)


def test_declared_family_evidence_consistency(rules) -> None:
    """P0: evidence outside declared families requires explicit governance wiring."""
    for rule_id, row in rules.items():
        declared = {req["family"] for req in row["fact_requirements"]}
        non_declared = row.get("non_declared_evidence") or {}
        has_gap_note = bool(row.get("declared_surface_gap"))
        paths = set(row["paths"])
        for token in _evidence_tokens(row):
            prefix = token.split("[")[0].split(".")[0]
            if prefix in declared or prefix in IDENTITY_PREFIXES or token == "subject_origin":
                continue
            wired = token in non_declared or prefix in non_declared
            assert wired, f"{rule_id}: undeclared evidence {token} not wired"
            if row["disposition"] != "D":
                assert has_gap_note, f"{rule_id}: missing declared_surface_gap"
                assert "C" in paths, f"{rule_id}: requirement amendment path missing"


def test_unproducible_declared_families_have_explicit_resolution(rules, matrix) -> None:
    """P0-B: every declared family without a producer needs a wired resolution.

    Extra entries beyond declared families are allowed only when they are
    evidence-driven requirements (family of some consumed/proposed evidence
    token), e.g. transport for CORE-CANON-004's redirect-chain condition.
    """
    non_emitted = set(matrix["adapter_boundary"]["non_emitted_registered_families"])
    for rule_id, row in rules.items():
        declared = {req["family"] for req in row["fact_requirements"]}
        tokens = _evidence_tokens(row)
        token_families = {
            re.split(r"[\[\].]", token)[0]
            for token in tokens
            if re.split(r"[\[\].]", token)[0] not in IDENTITY_PREFIXES
            and token != "subject_origin"
        }
        blocking = sorted(declared & non_emitted)
        recorded = row.get("readiness_blocking_families") or {}
        assert set(blocking) <= set(recorded), (
            f"{rule_id}: readiness_blocking_families must cover {blocking}"
        )
        for family in set(recorded) - set(blocking):
            assert family in token_families or family in (row.get("non_declared_evidence") or {}), (
                f"{rule_id}: unjustified extra readiness family {family}"
            )
        for family, ref in recorded.items():
            assert re.search(r"#\d+", str(ref)), (rule_id, family)


def test_gate7_unaccepted_semantics_cannot_bind_authoritatively(rules, matrix) -> None:
    entry_fields = set(RuleCatalogEntry.__dataclass_fields__)
    assert entry_fields.isdisjoint(EXECUTABLE_CONDITION_SURFACE)
    assert "condition" in entry_fields  # applicability prose only
    for rule_id, row in rules.items():
        proposed = row["proposed_executable_condition"]
        if proposed is None:
            continue
        assert proposed["governance_status"] == "accepted", rule_id
    authority = matrix["authority"]
    assert authority["catalog_authored_is_authoritative"] is True
    assert authority["proposed_conditions_are_not_authoritative"] is True
    assert authority["binding_requires_accepted_governance_path"] is True


def test_gate8_pipeline_modules_never_construct_non_emitted_family_envelopes(matrix) -> None:
    """P0/P1: AST-level lock over emitter-shaped constructions repo-wide.

    Only families still recorded as non-emitted are forbidden; transport and
    run-projection gained sanctioned adapters (#56/#57).
    """
    families = set(matrix["adapter_boundary"]["non_emitted_registered_families"])
    assert families == {"links", "resources", "structured-data"}
    kind_names = {"schema_family", "kind"}
    offenders: list[str] = []
    src_root = REPO_ROOT / "src" / "agentready"
    for path in sorted(src_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id in kind_names for t in node.targets)
                and isinstance(node.value, ast.Constant)
                and node.value.value in families
            ):
                offenders.append(f"{rel}:{node.lineno}")
            if isinstance(node, ast.keyword) and node.arg in kind_names:
                if isinstance(node.value, ast.Constant) and node.value.value in families:
                    offenders.append(f"{rel}:{getattr(node.value, 'lineno', node.lineno)}")
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value in kind_names
                        and isinstance(value, ast.Constant)
                        and value.value in families
                    ):
                        offenders.append(f"{rel}:{key.lineno}")
        if offenders:
            break
    assert offenders == []


def test_gate8_no_assignment_form_emitters_for_non_emitted_families(matrix) -> None:
    non_emitted = tuple(matrix["adapter_boundary"]["non_emitted_registered_families"])
    for family in non_emitted + ("transport", "run-projection"):
        assert DEFAULT_FACT_SCHEMA_VERSIONS.get(family) == "1"
    pattern = re.compile(
        r"\b(?:schema_family|kind)\s*(:|=)(?!=)\s*[\"'](?:" + "|".join(non_emitted) + r")[\"']"
    )
    offenders: list[str] = []
    src_root = REPO_ROOT / "src" / "agentready"
    for path in src_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], "unexpected envelope emitters for non-emitted families"


def test_adapter_boundary_documented_and_real(matrix) -> None:
    emitters = {item["family"]: item["adapter"] for item in matrix["adapter_boundary"]["emitters"]}
    assert set(emitters) == {
        "page",
        "representation",
        "robots.fetch|robots.parsed|robots.policy|sitemap.*",
        "transport",
        "run-projection",
    }
    persist_functions = {
        name
        for name in dir(run_facts_module)
        if name.startswith("persist_") and callable(getattr(run_facts_module, name))
    }
    robots_or_sitemap = [n for n in persist_functions if "robots" in n or "sitemap" in n]
    assert robots_or_sitemap, "run_facts emitters disappeared"
    non_emitted = set(matrix["adapter_boundary"]["non_emitted_registered_families"])
    assert non_emitted == {"links", "resources", "structured-data"}
    from agentready.audit_core.collection import (  # noqa: F401
        canonical_projection_fact_envelopes as _cp,
        load_transport_fact_envelopes as _lt,
        transport_fact_envelope as _te,
    )

    assert callable(_te) and callable(_lt) and callable(_cp)


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


def _artifact_issue_for(rule_id: str, governance: dict[str, str]) -> str:
    if rule_id.startswith("CORE-CANON"):
        return governance["canonical"]
    if rule_id.startswith("CORE-LINK"):
        return governance["links"]
    if rule_id == "GOOGLE-DESC-001":
        return governance["google_desc"]
    assert rule_id == "GOOGLE-TITLE-001"
    return governance["google_title"]


def test_matrix_conditions_are_backed_by_the_semantics_artifact(rules) -> None:
    """Accepted matrix conditions must exist verbatim-rule-wise in the artifact."""
    from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
    from agentready.seo.rules.catalog import load_rule_semantics

    artifact = load_rule_semantics(load_rule_catalog_snapshot())
    for rule_id, row in rules.items():
        condition = artifact.condition(rule_id)
        assert condition is not None, rule_id
        expected_issue = _artifact_issue_for(rule_id, artifact.governance)
        assert condition.source_issue == expected_issue, rule_id
        block = row["proposed_executable_condition"]
        if block is None:
            # catalog-derived authoritative rows (CORE-CANON-008) need no
            # acceptance flip; the artifact still records their condition.
            assert row["authoritative_executable_condition"] is not None, rule_id
            continue
        assert block["governance_status"] == "accepted", rule_id
        assert "agentready.rule-semantics.v2" in block.get("accepted_via", ""), rule_id
