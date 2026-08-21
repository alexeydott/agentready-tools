"""Compatibility crosswalk from live SEO check IDs to frozen v2.1 catalog rules (#20).

Starts from the Stage A (#2) explicit compatibility mapping
(:mod:`agentready.seo.compatibility`) rather than rebuilding a separate
legacy registry, and extends it with an explicit crosswalk to frozen
catalog rule IDs loaded via #18's ``load_rule_catalog_snapshot()``.

This module never executes or binds frozen rules; it only records
relations and lets migration tooling report:
- which live IDs have covering frozen rules (and which relation applies);
- which frozen rules have no live-check coverage yet (``NO_FROZEN_SUCCESSOR``
  in reverse: a frozen rule with zero crosswalk records pointing at it).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agentready.audit_core.rule_catalog import RuleCatalogSnapshot, load_rule_catalog_snapshot
from agentready.seo.compatibility import CURRENT_SEO_EVALUATOR_IDS, SEO_COMPATIBILITY_MAPPINGS

__all__ = [
    "CrosswalkRelation",
    "CrosswalkRecord",
    "SEO_CROSSWALK_RECORDS",
    "crosswalk_manifest",
    "live_ids_with_crosswalk",
    "frozen_rule_ids_referenced",
    "resolve_frozen_rule_ids",
    "reverse_lookup",
    "frozen_rules_without_live_coverage",
    "validate_crosswalk_against_snapshot",
]


class CrosswalkRelation(StrEnum):
    """Machine-readable relation between a live check ID and frozen rule(s)."""

    EQUIVALENT = "equivalent"
    COMPOSITE = "composite"
    PARTIAL_OVERLAP = "partial_overlap"
    COMPATIBILITY_ONLY = "compatibility_only"
    NON_EQUIVALENT = "non_equivalent"
    NO_FROZEN_SUCCESSOR = "no_frozen_successor"


@dataclass(frozen=True, slots=True)
class CrosswalkRecord:
    live_id: str
    frozen_rule_ids: tuple[str, ...]
    relation: CrosswalkRelation
    difference: str


# One live check may map to many frozen rules (COMPOSITE); a frozen rule may
# be referenced by multiple live checks below without implying duplicate
# execution -- the crosswalk is metadata only, never an executor.
#
# NON_EQUIVALENT / NO_FROZEN_SUCCESSOR records always carry an empty
# frozen_rule_ids tuple and a concrete `difference` explaining why no
# catalog rule is claimed as equivalent -- no relation defaults to
# EQUIVALENT without an explicit, tested record here.
SEO_CROSSWALK_RECORDS: tuple[CrosswalkRecord, ...] = (
    CrosswalkRecord(
        "metadata",
        ("GOOGLE-DESC-001", "GOOGLE-TITLE-001"),
        CrosswalkRelation.COMPOSITE,
        "Current 'metadata' evaluator checks title+description+heading semantics "
        "together in one pass; the frozen catalog separates title and description "
        "into distinct rules with independent length/presence semantics.",
    ),
    CrosswalkRecord(
        "title-length",
        ("GOOGLE-TITLE-001",),
        CrosswalkRelation.PARTIAL_OVERLAP,
        "Current 'title-length' only checks length thresholds; GOOGLE-TITLE-001 also "
        "requires presence, so the frozen rule is strictly broader than the legacy check.",
    ),
    CrosswalkRecord(
        "page-available",
        ("CORE-COVERAGE-001",),
        CrosswalkRelation.EQUIVALENT,
        "Both current 'page-available' and CORE-COVERAGE-001 test the same "
        "underlying condition: the page is discoverable and returns a crawlable "
        "transport response, with no additional semantics on either side.",
    ),
    CrosswalkRecord(
        "indexability",
        (),
        CrosswalkRelation.NON_EQUIVALENT,
        "Current 'indexability' evaluates robots/meta-robots directives only. "
        "CORE-COVERAGE-001 already covers the crawlable-response condition via "
        "'page-available'; no separate draft rule encodes meta-robots/robots-header "
        "indexability directive semantics, so no frozen successor is claimed here.",
    ),
    CrosswalkRecord(
        "canonical",
        ("CORE-CANON-001", "CORE-CANON-005"),
        CrosswalkRelation.PARTIAL_OVERLAP,
        "Current 'canonical' evaluator treats self-referencing canonical as the "
        "primary success condition; the frozen catalog splits canonical presence "
        "(CORE-CANON-001) from self-canonical-for-paginated-pages strategy "
        "(CORE-CANON-005) as distinct rules with different failure semantics.",
    ),
    CrosswalkRecord(
        "canonical-consistency-site",
        ("CORE-CANON-007",),
        CrosswalkRelation.PARTIAL_OVERLAP,
        "Current site-wide canonical-consistency check aggregates across the whole "
        "crawl; CORE-CANON-007 is scoped to cross-domain canonical targets "
        "specifically, a narrower condition than the legacy site-wide diagnostic.",
    ),
    CrosswalkRecord(
        "hreflang",
        ("GOOGLE-HREF-001", "GOOGLE-HREF-003"),
        CrosswalkRelation.PARTIAL_OVERLAP,
        "Current 'hreflang' evaluator validates language-region codes and "
        "self-reference on one page; it does not check cross-page reciprocity, "
        "which the catalog splits into a separate site-wide rule.",
    ),
    CrosswalkRecord(
        "hreflang-reciprocity-site",
        ("GOOGLE-HREF-002", "GOOGLE-HREF-004"),
        CrosswalkRelation.COMPOSITE,
        "Current site-wide reciprocity check combines reciprocal-pair validation "
        "and x-default presence in one diagnostic; the catalog keeps these as two "
        "separate rules (GOOGLE-HREF-002 reciprocity, GOOGLE-HREF-004 x-default).",
    ),
    CrosswalkRecord(
        "duplicate-metadata-site",
        (),
        CrosswalkRelation.NON_EQUIVALENT,
        "Current duplicate-metadata-site clusters near-duplicate title/description "
        "text across the crawl using a similarity threshold; the draft catalog has "
        "no rule with that fuzzy cross-page comparison semantics.",
    ),
    CrosswalkRecord(
        "link-counts",
        (),
        CrosswalkRelation.NON_EQUIVALENT,
        "Legacy internal-link count thresholds are a raw numeric heuristic with no "
        "equivalent compatibility-only or scored frozen rule; the catalog's "
        "CORE-LINK-* rules test link presence/validity, not count thresholds.",
    ),
    CrosswalkRecord(
        "insecure-links-pages",
        (),
        CrosswalkRelation.NON_EQUIVALENT,
        "Legacy insecure-links-pages flags any http:// link on an https page as a "
        "site-wide diagnostic; no catalog rule currently encodes that specific "
        "mixed-content-link heuristic.",
    ),
    CrosswalkRecord(
        "broken-links",
        (),
        CrosswalkRelation.COMPATIBILITY_ONLY,
        "Retained purely for selection-namespace compatibility (see #2); the "
        "underlying crawl-based broken-link detection has no frozen-catalog "
        "successor rule in this draft.",
    ),
    CrosswalkRecord(
        "redirect-chains",
        (),
        CrosswalkRelation.COMPATIBILITY_ONLY,
        "Retained purely for selection-namespace compatibility (see #2); "
        "redirect-chain diagnostics are transport-fact-driven and not yet "
        "represented as a scored/diagnostic frozen rule in this draft.",
    ),
    CrosswalkRecord(
        "internal-nofollow",
        (),
        CrosswalkRelation.COMPATIBILITY_ONLY,
        "Retained purely for selection-namespace compatibility (see #2); no "
        "catalog rule currently encodes internal-nofollow-link semantics.",
    ),
)

_RECORDS_BY_LIVE_ID: dict[str, CrosswalkRecord] = {record.live_id: record for record in SEO_CROSSWALK_RECORDS}


def crosswalk_manifest() -> tuple[dict[str, object], ...]:
    """Stable, serializable crosswalk manifest (deterministic declaration order)."""
    return tuple(
        {
            "live_id": record.live_id,
            "frozen_rule_ids": record.frozen_rule_ids,
            "relation": record.relation.value,
            "difference": record.difference,
        }
        for record in SEO_CROSSWALK_RECORDS
    )


def live_ids_with_crosswalk() -> frozenset[str]:
    return frozenset(_RECORDS_BY_LIVE_ID)


def frozen_rule_ids_referenced() -> frozenset[str]:
    result: set[str] = set()
    for record in SEO_CROSSWALK_RECORDS:
        result.update(record.frozen_rule_ids)
    return frozenset(result)


def resolve_frozen_rule_ids(live_id: str) -> tuple[str, ...]:
    """Frozen rule IDs a live check maps to. Never executes/binds them."""
    record = _RECORDS_BY_LIVE_ID.get(live_id)
    if record is None:
        raise ValueError(f"no crosswalk record for live SEO check ID: {live_id}")
    return record.frozen_rule_ids


def reverse_lookup(frozen_rule_id: str) -> tuple[str, ...]:
    """Live/legacy check IDs that reference a given frozen rule ID (may be many)."""
    return tuple(
        record.live_id
        for record in SEO_CROSSWALK_RECORDS
        if frozen_rule_id in record.frozen_rule_ids
    )


def frozen_rules_without_live_coverage(snapshot: RuleCatalogSnapshot | None = None) -> tuple[str, ...]:
    """Frozen rule IDs with zero crosswalk records referencing them.

    Deterministically ordered by catalog declaration order (not sorted),
    matching the snapshot's own entry order.
    """
    snapshot = snapshot or load_rule_catalog_snapshot()
    referenced = frozen_rule_ids_referenced()
    return tuple(entry.rule_id for entry in snapshot.entries if entry.rule_id not in referenced)


def validate_crosswalk_against_snapshot(snapshot: RuleCatalogSnapshot | None = None) -> None:
    """Fail closed if the crosswalk references a live ID or frozen rule ID that no longer exists.

    Raises ``ValueError`` collecting every problem found, rather than
    stopping at the first one, so a catalog reload/version bump surfaces
    every stale mapping at once.
    """
    snapshot = snapshot or load_rule_catalog_snapshot()
    known_frozen_ids = {entry.rule_id for entry in snapshot.entries}
    errors: list[str] = []

    seen_live_ids: set[str] = set()
    for record in SEO_CROSSWALK_RECORDS:
        if record.live_id in seen_live_ids:
            errors.append(f"duplicate crosswalk record for live_id: {record.live_id}")
        seen_live_ids.add(record.live_id)

        if record.live_id not in CURRENT_SEO_EVALUATOR_IDS and record.live_id not in {
            mapping.legacy_id for mapping in SEO_COMPATIBILITY_MAPPINGS
        }:
            errors.append(f"crosswalk live_id {record.live_id!r} is not a known current or legacy SEO check ID")

        if record.relation in (
            CrosswalkRelation.NON_EQUIVALENT,
            CrosswalkRelation.COMPATIBILITY_ONLY,
            CrosswalkRelation.NO_FROZEN_SUCCESSOR,
        ) and record.frozen_rule_ids:
            errors.append(
                f"crosswalk live_id {record.live_id!r} has relation {record.relation.value} but "
                "declares frozen_rule_ids; those relations must have an empty tuple"
            )
        if record.relation in (
            CrosswalkRelation.EQUIVALENT,
            CrosswalkRelation.COMPOSITE,
            CrosswalkRelation.PARTIAL_OVERLAP,
        ) and not record.frozen_rule_ids:
            errors.append(
                f"crosswalk live_id {record.live_id!r} has relation {record.relation.value} but "
                "declares no frozen_rule_ids"
            )
        if not record.difference.strip() and record.relation is not CrosswalkRelation.EQUIVALENT:
            errors.append(
                f"crosswalk live_id {record.live_id!r} is {record.relation.value} but has no recorded difference"
            )

        for frozen_id in record.frozen_rule_ids:
            if frozen_id not in known_frozen_ids:
                errors.append(
                    f"crosswalk live_id {record.live_id!r} references unknown frozen rule id {frozen_id!r}"
                )

    if errors:
        raise ValueError("invalid SEO crosswalk:\n- " + "\n- ".join(errors))
