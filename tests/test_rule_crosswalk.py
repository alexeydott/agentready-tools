"""Tests for the SEO live-check to frozen-catalog crosswalk (#20)."""
from __future__ import annotations

import pytest

from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot
from agentready.seo.compatibility import CURRENT_SEO_EVALUATOR_IDS, SEO_COMPATIBILITY_MAPPINGS
from agentready.seo.rule_crosswalk import (
    SEO_CROSSWALK_RECORDS,
    CrosswalkRelation,
    crosswalk_manifest,
    frozen_rule_ids_referenced,
    frozen_rules_without_live_coverage,
    live_ids_with_crosswalk,
    resolve_frozen_rule_ids,
    reverse_lookup,
    validate_crosswalk_against_snapshot,
)


@pytest.fixture(scope="module")
def snapshot():
    return load_rule_catalog_snapshot()


def test_full_live_id_coverage():
    """Every relevant live SEO check ID (current evaluator or Stage A legacy alias)
    has an explicit crosswalk record -- exact equality, not a subset check, per
    #20's full-coverage acceptance criterion."""
    legacy_ids = {mapping.legacy_id for mapping in SEO_COMPATIBILITY_MAPPINGS}
    relevant_ids = CURRENT_SEO_EVALUATOR_IDS | legacy_ids
    covered = live_ids_with_crosswalk()
    assert covered == relevant_ids
    # And the representative live IDs named in #20's work plan must be present.
    for expected in (
        "metadata",
        "canonical",
        "hreflang",
        "duplicate-metadata-site",
        "link-counts",
        "broken-links",
        "redirect-chains",
        "internal-nofollow",
    ):
        assert expected in covered, f"missing crosswalk record for {expected}"


def test_no_unknown_frozen_rule_ids(snapshot):
    known = {entry.rule_id for entry in snapshot.entries}
    referenced = frozen_rule_ids_referenced()
    assert referenced <= known


def test_no_duplicate_live_id_records():
    live_ids = [record.live_id for record in SEO_CROSSWALK_RECORDS]
    assert len(live_ids) == len(set(live_ids))


def test_no_relation_defaults_to_equivalent_without_explicit_record():
    equivalent_records = [r for r in SEO_CROSSWALK_RECORDS if r.relation is CrosswalkRelation.EQUIVALENT]
    assert equivalent_records, "expected at least one explicit EQUIVALENT golden case"
    for record in equivalent_records:
        assert record.frozen_rule_ids
        assert record.difference.strip()


@pytest.mark.parametrize(
    "live_id",
    ["duplicate-metadata-site", "link-counts", "insecure-links-pages"],
)
def test_expected_non_equivalent_cases_remain_non_equivalent(live_id):
    record = next(r for r in SEO_CROSSWALK_RECORDS if r.live_id == live_id)
    assert record.relation is CrosswalkRelation.NON_EQUIVALENT
    assert record.frozen_rule_ids == ()
    assert record.difference.strip()


@pytest.mark.parametrize("live_id", ["broken-links", "redirect-chains", "internal-nofollow"])
def test_compatibility_only_ids_remain_compatibility_only(live_id):
    record = next(r for r in SEO_CROSSWALK_RECORDS if r.live_id == live_id)
    assert record.relation is CrosswalkRelation.COMPATIBILITY_ONLY
    assert record.frozen_rule_ids == ()


def test_composite_live_id_maps_to_multiple_frozen_rules():
    record = next(r for r in SEO_CROSSWALK_RECORDS if r.live_id == "metadata")
    assert record.relation is CrosswalkRelation.COMPOSITE
    assert len(record.frozen_rule_ids) >= 2


def test_one_frozen_rule_referenced_by_multiple_live_ids_is_not_duplicate_execution():
    """GOOGLE-TITLE-001 is referenced by both 'metadata' (composite) and
    'title-length' (partial overlap) -- the crosswalk records this without any
    execution semantics attached."""
    referencing = reverse_lookup("GOOGLE-TITLE-001")
    assert set(referencing) >= {"metadata", "title-length"}
    assert len(referencing) == len(set(referencing))  # crosswalk itself has no duplicates


def test_reverse_lookup_returns_empty_for_uncovered_frozen_rule(snapshot):
    referenced = frozen_rule_ids_referenced()
    uncovered = [entry.rule_id for entry in snapshot.entries if entry.rule_id not in referenced]
    assert uncovered, "expected at least one frozen rule with no live coverage for this test to be meaningful"
    assert reverse_lookup(uncovered[0]) == ()


def test_frozen_rules_without_live_coverage_reports_migration_gap(snapshot):
    uncovered = frozen_rules_without_live_coverage(snapshot)
    referenced = frozen_rule_ids_referenced()
    assert all(rule_id not in referenced for rule_id in uncovered)
    # 200 rules total, only a handful are referenced by this crosswalk draft --
    # the overwhelming majority should be reported as migration gaps.
    assert len(uncovered) > 150


def test_crosswalk_manifest_is_stably_serializable_and_ordered():
    manifest_a = crosswalk_manifest()
    manifest_b = crosswalk_manifest()
    assert manifest_a == manifest_b
    assert [item["live_id"] for item in manifest_a] == [record.live_id for record in SEO_CROSSWALK_RECORDS]
    for item in manifest_a:
        assert isinstance(item["frozen_rule_ids"], tuple)
        assert isinstance(item["relation"], str)


def test_crosswalk_survives_catalog_reload_with_same_digest(snapshot):
    reloaded = load_rule_catalog_snapshot()
    assert reloaded.rule_catalog_digest == snapshot.rule_catalog_digest
    # Validation must succeed identically against either loaded snapshot.
    validate_crosswalk_against_snapshot(snapshot)
    validate_crosswalk_against_snapshot(reloaded)


def test_validate_crosswalk_against_snapshot_passes_for_current_catalog(snapshot):
    validate_crosswalk_against_snapshot(snapshot)


def test_validate_crosswalk_rejects_stale_frozen_rule_reference():
    from dataclasses import replace

    from agentready.audit_core.rule_catalog import RuleCatalogSnapshot

    snapshot = load_rule_catalog_snapshot()
    stale_entries = tuple(e for e in snapshot.entries if e.rule_id != "GOOGLE-DESC-001")
    stale_snapshot = replace(snapshot, entries=stale_entries)
    with pytest.raises(ValueError, match="unknown frozen rule id"):
        validate_crosswalk_against_snapshot(stale_snapshot)


def test_validate_crosswalk_rejects_stale_version_pin_on_unchanged_rule_id():
    """A catalog rule that keeps its ID but bumps its version must invalidate
    the crosswalk mapping pinned to the old version (#20/#21 version-aware
    compatibility gate) -- not just a removed-ID check."""
    from dataclasses import replace

    snapshot = load_rule_catalog_snapshot()
    entry = snapshot.entry("CORE-COVERAGE-001")
    assert entry is not None
    bumped_entry = replace(entry, version="2.0.0")
    bumped_entries = tuple(
        bumped_entry if e.rule_id == "CORE-COVERAGE-001" else e for e in snapshot.entries
    )
    bumped_snapshot = replace(snapshot, entries=bumped_entries)
    with pytest.raises(ValueError, match="is stale and must be re-verified"):
        validate_crosswalk_against_snapshot(bumped_snapshot)


def test_resolve_frozen_rule_ids_and_unknown_live_id_rejection():
    assert resolve_frozen_rule_ids("page-available") == ("CORE-COVERAGE-001",)
    with pytest.raises(ValueError, match="no crosswalk record"):
        resolve_frozen_rule_ids("not-a-real-check")
