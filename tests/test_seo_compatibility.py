import pytest

from agentready.seo.compatibility import (
    CompatibilityRelation,
    compatibility_manifest,
    normalize_selection,
    resolve_selection_ids,
)


def test_legacy_seo_selection_mappings_are_explicit_and_deterministic():
    manifest = {item["legacy_id"]: item for item in compatibility_manifest()}
    assert manifest["page-metadata"] == {
        "legacy_id": "page-metadata",
        "evaluator_ids": ("metadata",),
        "relation": CompatibilityRelation.EQUIVALENT.value,
    }
    assert manifest["duplicate-metadata"]["relation"] == CompatibilityRelation.COMPOSITE.value
    assert resolve_selection_ids(("page-metadata", "duplicate-metadata")) == {
        "metadata",
        "duplicate-metadata-site",
    }


def test_non_equivalent_legacy_ids_are_not_substituted_by_broader_rules():
    for legacy_id in ("broken-links", "internal-nofollow", "link-counts", "insecure-links-pages"):
        with pytest.raises(ValueError, match=legacy_id):
            resolve_selection_ids((legacy_id,))


def test_redirect_chain_mapping_rejects_absent_evaluator():
    with pytest.raises(ValueError, match="redirect-chains"):
        resolve_selection_ids(("redirect-chains",))


def test_unknown_and_absent_current_ids_are_rejected():
    with pytest.raises(ValueError, match="unknown SEO check ID"):
        resolve_selection_ids(("does-not-exist",))

    with pytest.raises(ValueError, match="unknown SEO check ID"):
        resolve_selection_ids(("redirect-inventory-site",))


def test_include_and_exclude_share_namespace_and_exclusion_wins():
    selection = normalize_selection(("page-metadata", "duplicate-metadata"), ("metadata",))
    assert selection.include == {"metadata", "duplicate-metadata-site"}
    assert selection.exclude == {"metadata"}
    assert selection.selected == {"duplicate-metadata-site"}
