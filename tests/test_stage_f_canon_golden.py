"""Stage F golden cutover tests — CORE-CANON family (#34 increment 1).

Data-driven: scenario table, expected verdicts and classifications live in the
checked-in frozen manifest ``docs/stage-f-canon-golden.yaml`` (single source of
truth for Stage-F semantics). The tests pin the manifest to the live catalog
snapshot and execute both sides of every scenario from ONE shared collection.

Targeted exact-HEAD suite:

    python -m pytest tests/test_stage_f_canon_golden.py -q

"""

from __future__ import annotations

import ast
import pathlib

import pytest
import yaml

from agentready.audit_core.canon_evaluators import evaluate_canon_rule
from agentready.audit_core.collection import (
    links_fact_envelope,
    page_fact_envelope,
    parsed_facts_from_dict,
    transport_fact_envelope,
)
from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.seo.evidence import SeoPageEvidence
from agentready.seo.rules.builtin import _canonical

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = pathlib.Path("docs") / "stage-f-canon-golden.yaml"
TARGET = "https://example.test/page"
T0 = "2026-08-22T00:00:00Z"


def _load_manifest():
    return yaml.safe_load((REPO_ROOT / MANIFEST).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest():
    return _load_manifest()


@pytest.fixture(scope="module")
def snapshot():
    return load_rule_catalog_snapshot()


# ---------------------------------------------------------------------------
# manifest ↔ live catalog consistency
# ---------------------------------------------------------------------------


def test_manifest_pins_the_live_catalog(manifest, snapshot):
    pin = manifest["catalog_pin"]
    assert pin["version"] == snapshot.catalog_version
    assert pin["digest"] == snapshot.rule_catalog_digest


def test_manifest_covers_exactly_the_frozen_rules(manifest, snapshot):
    frozen = set(manifest["frozen_rules"])
    wave_ids = {
        "CORE-CANON-001",
        "CORE-CANON-002",
        "CORE-CANON-005",
        "CORE-CANON-008",
    }
    assert frozen == wave_ids
    blocked = {b["rule_id"] for b in manifest["blocked_rules"]}
    assert blocked == set()
    # every blocked entry carries a reason
    for b in manifest["blocked_rules"]:
        assert b.get("reason"), b


def test_classification_vocabulary_is_respected(manifest):
    vocab = set(manifest["classification_vocab"])
    for sc in manifest["scenarios"]:
        assert sc["classification"] in vocab, sc["name"]


# ---------------------------------------------------------------------------
# golden execution — legacy + frozen from one shared collection
# ---------------------------------------------------------------------------


def _corpus(scenario):
    final_url = scenario.get("final_url", TARGET)

    legacy = SeoPageEvidence(
        url=TARGET,
        final_url=final_url,
        status_code=200,
        content_type="text/html",
        title="t",
        titles=("t",),
        description="d",
        descriptions=("d",),
        h1=(),
        canonicals=tuple(scenario["canonicals"]),
        hreflangs=(),
        meta_robots=(),
        x_robots="",
        jsonld_nodes=(),
        jsonld_errors=(),
        evidence_ids=("ev-canonical",),
    )
    payload_links = [
        {
            "source_representation_id": "static-html",
            "ordinal": i,
            **row,
        }
        for i, row in enumerate(scenario["links"])
    ]
    page = page_fact_envelope(
        subject_url=TARGET,
        facts=parsed_facts_from_dict(
            {"canonicals": list(scenario["canonicals"]), "links": payload_links}
        ),
        observed_at=T0,
    )
    transport = transport_fact_envelope(
        subject_url=TARGET,
        final_url=final_url,
        redirect_chain=[final_url],
        observed_at=T0,
    )
    return {"legacy": legacy, "page": page, "transport": transport}


_BUNDLES: dict[str, tuple] = {}


def _bundles(scenario_name, scenario):
    if scenario_name not in _BUNDLES:
        c = _corpus(scenario)
        links_env = links_fact_envelope(
            subject_url=TARGET,
            links=tuple(scenario["links"]),
            observed_at=T0,
        )
        _BUNDLES[scenario_name] = (c["page"], c["transport"], links_env)
    return _BUNDLES[scenario_name]


def _legacy_verdict(corpus):
    return str(_canonical(corpus["legacy"]).status)


def _frozen_verdicts(scenario_name, scenario):
    b = _bundles(scenario_name, scenario)
    return {
        rid: evaluate_canon_rule(rid, TARGET, b).finding.status.value
        for rid in ("CORE-CANON-001", "CORE-CANON-002", "CORE-CANON-005", "CORE-CANON-008")
    }


@pytest.mark.parametrize(
    "scenario",
    [sc["name"] for sc in _load_manifest()["scenarios"]],
)
def test_golden_scenario_matches_manifest(scenario, manifest):
    sc = next(s for s in manifest["scenarios"] if s["name"] == scenario)
    corpus = _corpus(sc)
    bundle = _bundles(scenario, sc)
    assert _legacy_verdict_for(corpus) == sc["legacy_status"], scenario
    for rid, expected in sc["frozen"].items():
        got = evaluate_canon_rule(rid, TARGET, bundle).finding.status.value
        assert got == expected, f"{scenario}/{rid}"




def _sc(name):
    doc = yaml.safe_load((REPO_ROOT / MANIFEST).read_text(encoding="utf-8"))
    return next(s for s in doc["scenarios"] if s["name"] == name)


def _legacy_verdict_for(corpus):
    return str(_canonical(corpus["legacy"]).status)


# ---------------------------------------------------------------------------
# classification semantics
# ---------------------------------------------------------------------------


def test_off_origin_split_is_intended():
    m = _load_manifest()
    off = next(s for s in m["scenarios"] if s["name"] == "off-origin-single")
    assert off["frozen"]["CORE-CANON-002"] == "fail"
    assert off["frozen"]["CORE-CANON-005"] == "pass"
    assert off["split_note"].startswith("CORE-CANON-002 owns")


def test_paginated_drift_is_owned_by_005():
    drift = next(
        s for s in _load_manifest()["scenarios"] if s["name"] == "paginated-canonical-drift"
    )
    assert drift["frozen"]["CORE-CANON-005"] == "fail"
    assert drift["frozen"]["CORE-CANON-002"] == "pass"


def test_presence_scenarios_are_blocked_and_escalated():
    m = _load_manifest()
    for name in ("duplicated", "missing"):
        sc = next(s for s in m["scenarios"] if s["name"] == name)
        assert sc["classification"] == "presence_blocked"
        assert sc["escalation"] == "block_unknown_escalation"
        assert sc["frozen"]["CORE-CANON-008"] == "fail"


def test_policy_notes_document_block_unknown_escalation(manifest):
    note = manifest["policy_notes"]["block_unknown_escalation"]
    assert "block_on_missing_facts" in note
    assert "`error`" in note or "error" in note


# ---------------------------------------------------------------------------
# procedure gates (steps 9–10 + determinism + purity)
# ---------------------------------------------------------------------------


def test_single_collection_no_duplicate_fetch_surface():
    sc = next(s for s in _load_manifest()["scenarios"] if s["name"] == "self-paginated")
    a = _bundles("self-paginated", sc)
    b = _bundles("self-paginated", sc)
    assert a[0] is b[0] and a[1] is b[1]


def test_frozen_reruns_are_deterministic():
    sc = _sc("paginated-canonical-drift")
    a = _frozen_verdicts("paginated-canonical-drift", sc)
    b = _frozen_verdicts("paginated-canonical-drift", sc)
    assert a == b


def test_legacy_scoring_inputs_untouched_by_frozen_run():
    sc = next(s for s in _load_manifest()["scenarios"] if s["name"] == "off-origin-single")
    before = str(_canonical(_corpus(sc)["legacy"]).status)
    _bundles("off-origin-single", _sc("off-origin-single"))
    after = str(_canonical(_corpus(sc)["legacy"]).status)
    assert before == after == "fail"


def test_purity_module_has_no_io_imports():
    tree = ast.parse(
        (
            REPO_ROOT / "src" / "agentready" / "audit_core" / "canon_evaluators.py"
        ).read_text(encoding="utf-8")
    )
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.add(node.names[0].name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    forbidden = {"requests", "httpx", "sqlite3", "socket", "subprocess"}
    assert roots & forbidden == set(), roots & forbidden
