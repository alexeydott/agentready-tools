"""Stage F golden procedure — GOOGLE-TITLE-001 ↔ legacy ``title-length`` (#34).

Data-driven over the frozen manifest ``docs/stage-f-title-golden.yaml``.

Crosswalk class: PARTIAL_OVERLAP. The legacy rule is a HEURISTIC (warn/skip);
the frozen rule is SCORED with structural fails and a governed 30..65 band.
Every heuristic-vs-scored divergence is an intended split, encoded per
scenario in the manifest.

Targeted exact-HEAD suite:

    python -m pytest tests/test_stage_f_title_golden.py -q

"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from agentready.audit_core.collection import page_fact_envelope, parsed_facts_from_dict
from agentready.audit_core.rule_catalog import (
    load_rule_catalog_snapshot,
    load_rule_semantics,
)
from agentready.audit_core.google_title_evaluators import evaluate_google_title
from agentready.seo.evidence import SeoPageEvidence
from agentready.seo.rules.builtin import _title_length

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = pathlib.Path("docs") / "stage-f-title-golden.yaml"
TARGET = "https://example.test/page"
T0 = "2026-08-22T00:00:00Z"


def _load_manifest():
    return yaml.safe_load((REPO_ROOT / MANIFEST).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# shared collection builders
# ---------------------------------------------------------------------------


def _legacy_evidence(titles):
    primary = next((t for t in titles if t.strip()), "")
    return SeoPageEvidence(
        url=TARGET,
        final_url=TARGET,
        status_code=200,
        content_type="text/html",
        title=primary,
        titles=tuple(titles),
        description="d",
        descriptions=("d",),
        h1=(),
        canonicals=(TARGET,),
        hreflangs=(),
        meta_robots=(),
        x_robots="",
        jsonld_nodes=(),
        jsonld_errors=(),
        evidence_ids=("ev-title",),
    )


def _frozen_bundle(titles):
    payload_links = []
    envelope = page_fact_envelope(
        subject_url=TARGET,
        facts=parsed_facts_from_dict({"titles": list(titles), "links": payload_links}),
        observed_at=T0,
    )
    return (envelope,)


# ---------------------------------------------------------------------------
# golden execution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario", [s["name"] for s in _load_manifest()["scenarios"]]
)
def test_golden_title_scenario(scenario):
    m = _load_manifest()
    sc = next(s for s in m["scenarios"] if s["name"] == scenario)

    legacy = _title_length(_legacy_evidence(sc["titles"]))
    frozen = evaluate_google_title(TARGET, _frozen_bundle(sc["titles"]))

    assert legacy.status == sc["legacy_status"], f"{scenario}: legacy"
    assert (
        frozen.finding.status.value == sc["frozen_status"]
    ), f"{scenario}: frozen"


# ---------------------------------------------------------------------------
# manifest consistency gates
# ---------------------------------------------------------------------------


def test_manifest_pins_the_live_catalog():
    from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot

    m = _load_manifest()
    snap = load_rule_catalog_snapshot()
    assert m["catalog_pin"]["version"] == snap.catalog_version
    assert m["catalog_pin"]["digest"] == snap.rule_catalog_digest


def test_accepted_band_is_governed_by_the_artifact():
    from agentready.audit_core.google_title_evaluators import (
        GOOGLE_TITLE_MAX_LENGTH,
        GOOGLE_TITLE_MIN_LENGTH,
    )

    band = load_rule_semantics(load_rule_catalog_snapshot()).condition(
        "GOOGLE-TITLE-001"
    ).length_band
    assert (band.min, band.max, band.inclusive) == (30, 65, True)
    assert GOOGLE_TITLE_MIN_LENGTH == 30 and GOOGLE_TITLE_MAX_LENGTH == 65


def test_classification_vocabulary_is_respected():
    vocab = set(_load_manifest()["classification_vocab"])
    for sc in _load_manifest()["scenarios"]:
        assert sc["classification"] in vocab, sc["name"]


def test_every_heuristic_divergence_carries_a_note():
    for sc in _load_manifest()["scenarios"]:
        if sc["classification"].startswith("intended"):
            assert sc.get("note"), sc["name"]
