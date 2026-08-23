"""Stage F golden procedure — CORE-CANON family (#34 increment 1).

Ten-step golden cutover procedure for the partial-overlap pair ``canonical``
(legacy) ↔ {CORE-CANON-002/005/008} (frozen), with explicit dispositions for
every difference and hard gates against duplicate collection and double
scoring.

Crosswalk class: PARTIAL_OVERLAP — only overlapping semantics may cut over;
presence-only branches (CORE-CANON-001) are not implemented at runtime, so
full replacement is BLOCKED until that binding lands.

FREEZE MODE: current runtime verdicts are frozen as golden. Semantic
divergences vs the accepted semantics artifact are tracked separately
(see KNOWN_DELTAS in tests/test_stage_f_known_deltas.py).
"""

from __future__ import annotations

import pathlib

import pytest

from agentready.audit_core.canon_evaluators import evaluate_canon_rule
from agentready.audit_core.collection import (
    page_fact_envelope,
    parsed_facts_from_dict,
    transport_fact_envelope,
)
from agentready.seo.evidence import SeoPageEvidence
from agentready.seo.rules.builtin import _canonical

TARGET = "https://example.test/page"
FINAL = "https://example.test/page"
OTHER_ORIGIN = "https://cdn.example.test/canonical"
OTHER_PATH = "https://example.test/other"
ORIGIN_TEST = "https://example.test"
T0 = "2026-08-22T00:00:00Z"


def _row(ordinal, raw_href, resolved_url, rel=""):
    return {
        "source_representation_id": "static-html",
        "ordinal": ordinal,
        "raw_href": raw_href,
        "resolved_url": resolved_url,
        "rel": rel,
    }


SCENARIOS = {
    "self-non-paginated": {"canonicals": [FINAL], "links": []},
    "self-paginated": {
        "canonicals": [FINAL],
        "links": [_row(0, "/next", f"{ORIGIN_TEST}/next", "next")],
    },
    "off-origin-single": {"canonicals": [OTHER_ORIGIN], "links": []},
    "self-host-other-path-single": {"canonicals": [OTHER_PATH], "links": []},
    "paginated-other-final": {
        "canonicals": [OTHER_PATH],
        "links": [_row(0, "/next", f"{ORIGIN_TEST}/next", "next")],
    },
    "paginated-canonical-drift": {
        "canonicals": [FINAL],
        "links": [_row(0, "/next", f"{ORIGIN_TEST}/next", "next")],
        "final_url": OTHER_PATH,
    },
    "duplicated": {"canonicals": [FINAL, OTHER_PATH], "links": []},
    "missing": {"canonicals": [], "links": []},
}

_BUNDLES: dict[str, tuple] = {}


def _corpus(scenario_name):
    """Step 1–3: build BOTH legacy evidence and frozen bundles from one fact set."""
    sc = SCENARIOS[scenario_name]
    final_url = sc.get("final_url", FINAL)

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
        canonicals=tuple(sc["canonicals"]),
        hreflangs=(),
        meta_robots=(),
        x_robots="",
        jsonld_nodes=(),
        jsonld_errors=(),
        evidence_ids=("ev-canonical",),
    )

    page = page_fact_envelope(
        subject_url=TARGET,
        facts=parsed_facts_from_dict(
            {"canonicals": list(sc["canonicals"]), "links": list(sc["links"])}
        ),
        observed_at=T0,
    )
    transport = transport_fact_envelope(
        subject_url=TARGET,
        final_url=final_url,
        redirect_chain=[final_url],
        observed_at=T0,
    )

    return {"legacy_evidence": legacy, "page": page, "transport": transport}


def _bundles(scenario_name):
    if scenario_name not in _BUNDLES:
        c = _corpus(scenario_name)
        _BUNDLES[scenario_name] = (c["page"], c["transport"])
    return _BUNDLES[scenario_name]


def _legacy_verdict(scenario_name):
    return str(_canonical(_corpus(scenario_name)["legacy_evidence"]).status)


def _frozen_verdicts(scenario_name):
    b = _bundles(scenario_name)
    out = {}
    for rid in ("CORE-CANON-002", "CORE-CANON-005", "CORE-CANON-008"):
        r = evaluate_canon_rule(rid, TARGET, b)
        out[rid] = r.finding.status.value
    return out


# ---------------------------------------------------------------------------
# classification table (step 6) — frozen runtime verdicts
# ---------------------------------------------------------------------------

EXPECTED_TABLE = [
    ("self-non-paginated", "pass", "pass", "pass", "pass"),
    ("self-paginated", "pass", "pass", "pass", "pass"),
    ("off-origin-single", "fail", "pass", "pass", "fail"),
    ("self-host-other-path-single", "fail", "pass", "pass", "pass"),
    ("paginated-other-final", "fail", "fail", "pass", "pass"),
    ("paginated-canonical-drift", "fail", "fail", "pass", "pass"),
    ("duplicated", "fail", "error", "fail", "error"),
    ("missing", "fail", "error", "fail", "error"),
]


@pytest.mark.parametrize("scenario,legacy,f005,f008,f002", EXPECTED_TABLE)
def test_golden_classification_table(scenario, legacy, f005, f008, f002):
    assert _legacy_verdict(scenario) == legacy
    got = _frozen_verdicts(scenario)
    assert got["CORE-CANON-005"] == f005, scenario
    assert got["CORE-CANON-008"] == f008, scenario
    assert got["CORE-CANON-002"] == f002, scenario


# ---------------------------------------------------------------------------
# intended differences (crosswalk PARTIAL_OVERLAP splits)
# ---------------------------------------------------------------------------


def test_off_origin_difference_is_intended_split():
    got = _frozen_verdicts("off-origin-single")
    assert got["CORE-CANON-002"] == "fail"      # 002 owns scheme/host drift
    assert got["CORE-CANON-005"] == "pass"      # strategy not violated


def test_paginated_strategy_is_owned_by_005():
    got = _frozen_verdicts("paginated-canonical-drift")
    assert got["CORE-CANON-005"] == "fail"      # 005 owns pagination strategy
    assert got["CORE-CANON-002"] == "pass"      # same-origin drift is not 002's


def test_presence_branch_is_blocked_for_replacement():
    got = _frozen_verdicts("duplicated")
    assert got["CORE-CANON-008"] == "fail"      # exactly-once covers dup detection
    assert got["CORE-CANON-005"] == "error"     # block policy escalates unknown


# ---------------------------------------------------------------------------
# procedure gates (steps 9–10 + determinism)
# ---------------------------------------------------------------------------


def test_single_collection_no_duplicate_fetch_surface():
    a = _bundles("self-paginated")
    b = _bundles("self-paginated")
    assert a[0] is b[0] and a[1] is b[1]


def test_frozen_reruns_are_deterministic():
    a = _frozen_verdicts("paginated-canonical-drift")
    b = _frozen_verdicts("paginated-canonical-drift")
    assert a == b


def test_legacy_scoring_inputs_untouched_by_frozen_run():
    before = _canonical(_corpus("off-origin-single")["legacy_evidence"])
    _frozen_verdicts("off-origin-single")
    after = _canonical(_corpus("off-origin-single")["legacy_evidence"])
    assert before.status == after.status == "fail"
    assert before.impact == after.impact and before.priority == after.priority
