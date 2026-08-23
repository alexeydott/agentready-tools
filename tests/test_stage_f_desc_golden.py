"""Stage F golden procedure — GOOGLE-DESC-001 ↔ legacy ``metadata`` (#34).

Data-driven over the frozen manifest ``docs/stage-f-desc-golden.yaml``.

Crosswalk class: COMPOSITE — only the description constituent overlaps
GOOGLE-DESC-001. Length band 120..160 (collapsed) is governed by
``agentready.rule-semantics.v2`` 1.0.1; legacy metadata never scored length.

Targeted exact-HEAD suite:

    python -m pytest tests/test_stage_f_desc_golden.py -q

"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from agentready.audit_core.collection import (
    page_fact_envelope,
    parsed_facts_from_dict,
)
from agentready.audit_core.google_desc_evaluators import evaluate_google_desc
from agentready.seo.evidence import SeoPageEvidence
from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.seo.rules.builtin import _metadata

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = pathlib.Path("docs") / "stage-f-desc-golden.yaml"
TARGET = "https://example.test/page"
T0 = "2026-08-22T00:00:00Z"


def _load_manifest():
    return yaml.safe_load((REPO_ROOT / MANIFEST).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# shared collection builders
# ---------------------------------------------------------------------------


def _legacy_evidence(sc):
    return SeoPageEvidence(
        url=TARGET,
        final_url=TARGET,
        status_code=200,
        content_type=sc.get("content_type", "text/html"),
        title=sc["title"],
        titles=tuple(sc["titles"]),
        description=(sc["descriptions"][0] if sc["descriptions"] else ""),
        descriptions=tuple(sc["descriptions"]),
        h1=tuple(sc["h1"]),
        canonicals=(TARGET,),
        hreflangs=(),
        meta_robots=(),
        x_robots="",
        jsonld_nodes=(),
        jsonld_errors=(),
        evidence_ids=("ev-metadata",),
    )


def _frozen_bundle(sc):
    payload = {"titles": list(sc["titles"]), "descriptions": list(sc["descriptions"])}
    envelope = page_fact_envelope(
        subject_url=TARGET,
        facts=parsed_facts_from_dict(payload),
        observed_at=T0,
    )
    return envelope


def _frozen_verdicts(sc):
    r = evaluate_google_desc(TARGET, (_frozen_bundle(sc),))
    return r.finding.status.value


# ---------------------------------------------------------------------------
# golden execution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario", [sc["name"] for sc in _load_manifest()["scenarios"]]
)
def test_golden_desc_scenario(scenario):
    m = _load_manifest()
    sc = next(s for s in m["scenarios"] if s["name"] == scenario)

    assert _legacy_evidence(sc) is not None
    legacy_status = str(_metadata(_legacy_evidence(sc)).status)
    frozen_status = _frozen_verdicts(sc)

    assert legacy_status == sc["legacy_status"], f"{scenario}: legacy"
    assert frozen_status == sc["frozen_status"], f"{scenario}: frozen"


# ---------------------------------------------------------------------------
# classification semantics
# ---------------------------------------------------------------------------


def test_normalization_split_is_intended():
    m = _load_manifest()
    ws = next(s for s in m["scenarios"] if s["name"] == "whitespace-only-description")
    assert ws["legacy_status"] == "pass"
    assert ws["frozen_status"] == "fail"


def test_multiplicity_split_is_intended():
    m = _load_manifest()
    multi = next(s for s in m["scenarios"] if s["name"] == "multiple-descriptions")
    assert multi["frozen"]["GOOGLE-DESC-001"] == "fail"
    assert multi["classification"] == "intended_multiplicity"


def test_scored_band_is_governed_by_the_artifact():
    from agentready.audit_core.google_desc_evaluators import (
        MAX_DESCRIPTION_LENGTH,
        MIN_DESCRIPTION_LENGTH,
    )
    from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot, load_rule_semantics

    band = load_rule_semantics(load_rule_catalog_snapshot()).condition(
        "GOOGLE-DESC-001"
    ).length_band
    assert (band.min, band.max, band.inclusive) == (120, 160, True)
    assert MIN_DESCRIPTION_LENGTH == 120 and MAX_DESCRIPTION_LENGTH == 160


def test_non_desc_constituents_are_out_of_scope():
    """Composite constituents title/H1 belong to other rule families."""
    m = _load_manifest()
    for sc in m["scenarios"]:
        assert "h1" not in sc.get("frozen", {})


# ---------------------------------------------------------------------------
# manifest consistency gates
# ---------------------------------------------------------------------------


def test_manifest_pins_the_live_catalog():
    manifest = _load_manifest()
    pin = manifest["catalog_pin"]
    snap = load_rule_catalog_snapshot()
    assert pin["version"] == snap.catalog_version
    assert pin["digest"] == snap.rule_catalog_digest


def test_classification_vocabulary_is_respected():
    manifest = _load_manifest()
    vocab = set(manifest["classification_vocab"])
    for sc in manifest["scenarios"]:
        assert sc["classification"] in vocab, sc["name"]
