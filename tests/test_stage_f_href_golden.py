"""Stage F google-hreflang golden tests (#28).

Exercises the three bound GOOGLE-HREF rules against the golden scenarios
defined in ``docs/stage-f-href-golden.yaml``.  Two rules (002/005) are
declared_not_producible and not tested here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
import pytest

from agentready.audit_core.contracts import FactEnvelope
from agentready.audit_core.collection import (
    links_fact_envelope,
    page_fact_envelope,
    parsed_facts_from_dict,
    transport_fact_envelope,
)
from agentready.audit_core.google_href_evaluators import evaluate_google_href
from agentready.audit_core.urls import UrlIdentity

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "stage-f-href-golden.yaml"
TARGET = "https://example.test/page"
T0 = "2026-08-24T00:00:00Z"
_identity = UrlIdentity.parse(TARGET)


def _load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return _load_manifest()


def _corpus(scenario: dict[str, Any]) -> dict[str, Any]:
    hreflang = scenario.get("hreflang")
    if hreflang is None:
        payload = {
            "canonicals": list(scenario.get("canonicals", [])),
            "meta_robots": list(scenario.get("meta_robots", [])),
            "links": [],
        }
        page = FactEnvelope(
            id="test-hreflang-unavailable",
            kind="page",
            target=_identity,
            value=payload,
            observed_at=T0,
            schema_family="page",
        )
    else:
        page = page_fact_envelope(
            subject_url=TARGET,
            facts=parsed_facts_from_dict({
                "canonicals": list(scenario.get("canonicals", [])),
                "hreflang": list(hreflang),
                "meta_robots": list(scenario.get("meta_robots", [])),
                "links": [],
            }),
            observed_at=T0,
        )
    transport = transport_fact_envelope(
        subject_url=TARGET,
        final_url=TARGET,
        redirect_chain=[TARGET],
        observed_at=T0,
    )
    links_env = links_fact_envelope(
        subject_url=TARGET,
        links=tuple(scenario.get("links", [])),
        observed_at=T0,
    )
    return {"page": page, "transport": transport, "links": links_env}


_BUNDLES: dict[str, tuple] = {}


def _bundles(scenario_name: str, scenario: dict[str, Any]) -> tuple:
    if scenario_name not in _BUNDLES:
        c = _corpus(scenario)
        _BUNDLES[scenario_name] = (c["page"], c["transport"], c["links"])
    return _BUNDLES[scenario_name]


def test_manifest_pins_the_live_catalog(manifest):
    from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot

    snap = load_rule_catalog_snapshot()
    assert snap.catalog_version == manifest["catalog_pin"]["version"]
    assert snap.rule_catalog_digest == manifest["catalog_pin"]["digest"]


def test_manifest_covers_exactly_bound_and_deferred(manifest):
    bound = set(manifest["bound_rules"])
    expected_bound = {"GOOGLE-HREF-001", "GOOGLE-HREF-003", "GOOGLE-HREF-004"}
    assert bound == expected_bound
    deferred = {d["rule_id"] for d in manifest["declared_not_producible"]}
    assert deferred == {"GOOGLE-HREF-002", "GOOGLE-HREF-005"}


def test_classification_vocabulary_is_respected(manifest):
    vocab = set(manifest["classification_vocab"])
    for sc in manifest["scenarios"]:
        assert sc["classification"] in vocab, sc["name"]


@pytest.mark.parametrize(
    "scenario",
    [sc["name"] for sc in _load_manifest()["scenarios"]],
)
def test_golden_scenario_matches_manifest(scenario, manifest):
    sc = next(s for s in manifest["scenarios"] if s["name"] == scenario)
    bundle = _bundles(scenario, sc)
    for rid, expected in sc["frozen"].items():
        got = evaluate_google_href(TARGET, bundle, rule_id=rid).finding.status.value
        assert got == expected, f"{scenario}/{rid}: got {got}, expected {expected}"


def test_vacuous_skip_when_no_annotations(manifest):
    """Bound rules return skip (not_applicable) when hreflang is an empty list."""
    sc = next(s for s in manifest["scenarios"] if s["name"] == "single-language-no-annotations")
    bundle = _bundles(sc["name"], sc)
    for rid in manifest["bound_rules"]:
        result = evaluate_google_href(TARGET, bundle, rule_id=rid)
        assert result.finding.status.value == "skip", f"{rid}: expected skip for vacuously valid"
        assert result.finding.outcome.value == "not_applicable", f"{rid}: expected not_applicable"


def test_unknown_when_hreflang_unavailable(manifest):
    """Bound rules return error when hreflang field is missing from page fact."""
    sc = next(s for s in manifest["scenarios"] if s["name"] == "hreflang-unavailable")
    bundle = _bundles(sc["name"], sc)
    for rid in manifest["bound_rules"]:
        result = evaluate_google_href(TARGET, bundle, rule_id=rid)
        assert result.finding.status.value == "error", f"{rid}: expected error for unavailable hreflang"


def test_policy_notes_document_scope(manifest):
    assert "cross_page_reciprocity" in manifest["policy_notes"]
    assert "fact_availability" in manifest["policy_notes"]
