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
