"""Gates for the accepted Stage E rule-semantics artifact (#52–#55).

Locks the normative executable conditions and requirement amendments:

* the packaged document loads offline with a stable digest;
* it is pinned to the live frozen catalog (version + digest) and every
  rule id/version matches the snapshot;
* coverage is exactly the first-wave rule set;
* governed numeric bands (120..160 / 30..65) live HERE, not in evaluators;
* requirement amendments record the agreed post-acceptance fact families.

Targeted exact-HEAD suite:

    python -m pytest tests/test_rule_semantics.py -q

"""

from __future__ import annotations

import pytest

from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.seo.rules.catalog import (
    SEMANTICS_SCHEMA_ID,
    compute_semantics_digest,
    load_rule_semantics,
)

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


@pytest.fixture(scope="module")
def snapshot():
    return load_rule_catalog_snapshot()


@pytest.fixture(scope="module")
def semantics(snapshot):
    return load_rule_semantics(snapshot)


def test_document_loads_offline_with_stable_digest(semantics) -> None:
    assert semantics.schema == SEMANTICS_SCHEMA_ID
    assert semantics.semantics_version == "1.0.1"
    assert semantics.digest == compute_semantics_digest()
    assert len(semantics.digest) == 64
    amendments = {a.rule_id: a.families for a in semantics.amendments}
    assert amendments["CORE-LINK-001"] == ("page", "representation")
    assert amendments["CORE-LINK-004"] == ("page", "representation")


def test_artifact_is_pinned_to_live_catalog(semantics, snapshot) -> None:
    assert semantics.catalog_version == snapshot.catalog_version
    assert semantics.catalog_digest == snapshot.rule_catalog_digest
    for condition in semantics.conditions:
        entry = snapshot.entry(condition.rule_id)
        assert entry is not None, condition.rule_id
        assert condition.version == entry.version, condition.rule_id


def test_coverage_exactly_first_wave(semantics) -> None:
    assert {c.rule_id for c in semantics.conditions} == EXPECTED_WAVE_IDS
    assert {a.rule_id for a in semantics.amendments} == EXPECTED_WAVE_IDS


def test_governance_issues_are_wired(semantics) -> None:
    assert semantics.governance == {
        "canonical": "#52",
        "links": "#53",
        "google_desc": "#54",
        "google_title": "#55",
    }
    for condition in semantics.conditions:
        assert re.fullmatch(r"#\d+", condition.source_issue), condition.rule_id
        assert condition.verdicts, condition.rule_id
        assert condition.evidence_fields, condition.rule_id


import re  # noqa: E402  (kept next to usage-free import ordering constraints)


def test_numeric_bands_are_governed_by_the_artifact(semantics) -> None:
    from agentready.seo.rules.catalog.rule_semantics import LengthBand

    desc = semantics.condition("GOOGLE-DESC-001")
    title = semantics.condition("GOOGLE-TITLE-001")
    assert desc.length_band == LengthBand(min=120, max=160, inclusive=True)
    assert title.length_band == LengthBand(min=30, max=65, inclusive=True)
    assert desc.measurement and "whitespace-collapsed" in desc.measurement
    assert title.measurement and "str.strip()" in title.measurement
    assert desc.provenance_note and "governed HERE" in desc.provenance_note
    assert title.provenance_note and "governed HERE" in title.provenance_note
    assert desc.source_issue == "#54" and title.source_issue == "#55"


def test_requirement_amendments_match_acceptance(rules_snapshot=None) -> None:
    doc = load_rule_semantics(load_rule_catalog_snapshot())
    amendments = {a.rule_id: a.families for a in doc.amendments}
    assert amendments["CORE-CANON-002"] == ("page", "transport")
    assert amendments["CORE-CANON-004"] == ("page", "transport")
    assert amendments["CORE-CANON-008"] == ("page",)
    assert amendments["CORE-CANON-006"] == ("page", "run-projection")
    assert amendments["CORE-LINK-003"] == ("page",)
    assert amendments["GOOGLE-DESC-001"] == ("page",)


def test_drifted_pin_is_rejected(snapshot) -> None:
    doc = load_rule_semantics(snapshot)
    drifted = type(doc)(
        schema=doc.schema,
        semantics_version=doc.semantics_version,
        catalog_version=doc.catalog_version,
        catalog_digest="0" * 64,
        governance=dict(doc.governance),
        conditions=doc.conditions,
        amendments=doc.amendments,
        digest=doc.digest,
    )
    from agentready.seo.rules.catalog import RuleSemanticsError

    with pytest.raises(RuleSemanticsError):
        from agentready.seo.rules.catalog.rule_semantics import _validate_against_snapshot

        _validate_against_snapshot(drifted, snapshot)
