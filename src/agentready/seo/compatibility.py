"""Explicit compatibility metadata for legacy SEO selection IDs."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CompatibilityRelation(StrEnum):
    EQUIVALENT = "equivalent"
    COMPOSITE = "composite"
    COMPATIBILITY_ONLY = "compatibility-only"
    NON_EQUIVALENT = "non-equivalent"
    DEPRECATED = "deprecated"


@dataclass(frozen=True)
class SeoCompatibilityMapping:
    legacy_id: str
    evaluator_ids: tuple[str, ...]
    relation: CompatibilityRelation


@dataclass(frozen=True)
class SeoSelection:
    """Canonical include/exclude sets; exclusions take precedence on conflicts."""

    include: frozenset[str]
    exclude: frozenset[str]

    @property
    def selected(self) -> frozenset[str]:
        return self.include - self.exclude if self.include else frozenset()


CURRENT_SEO_EVALUATOR_IDS = frozenset({
    "page-available",
    "metadata",
    "indexability",
    "canonical",
    "hreflang",
    "jsonld",
    "title-length",
    "duplicate-metadata-site",
    "duplicate-content-site",
    "thin-content-site",
    "heading-structure-site",
    "canonical-consistency-site",
    "hreflang-reciprocity-site",
    "link-architecture-site",
    "orphan-candidates-site",
    "link-depth-site",
    "anchor-distribution-site",
    "internal-link-authority-site",
    "image-inventory-site",
    "sitemap-reconciliation-site",
    "robots-reconciliation-site",
    "crawl-coverage",
    "broken-links",
    "redirect-chains",
    "internal-nofollow",
    "ga-no-traffic",
    "ga-bounce-rate",
    "ga-nonindexed-traffic",
    "gsc-no-clicks",
    "gsc-no-impressions",
    "gsc-nonindexed-impressions",
})


SEO_COMPATIBILITY_MAPPINGS: tuple[SeoCompatibilityMapping, ...] = (
    SeoCompatibilityMapping("page-metadata", ("metadata",), CompatibilityRelation.EQUIVALENT),
    SeoCompatibilityMapping("page-indexability", ("indexability",), CompatibilityRelation.EQUIVALENT),
    SeoCompatibilityMapping("duplicate-metadata", ("duplicate-metadata-site",), CompatibilityRelation.COMPOSITE),
    SeoCompatibilityMapping("broken-links", ("broken-links",), CompatibilityRelation.COMPATIBILITY_ONLY),
    SeoCompatibilityMapping("redirect-chains", ("redirect-chains",), CompatibilityRelation.COMPATIBILITY_ONLY),
    SeoCompatibilityMapping("internal-nofollow", ("internal-nofollow",), CompatibilityRelation.COMPATIBILITY_ONLY),
    SeoCompatibilityMapping("link-counts", (), CompatibilityRelation.NON_EQUIVALENT),
    SeoCompatibilityMapping("insecure-links-pages", (), CompatibilityRelation.NON_EQUIVALENT),
)

_MAPPINGS_BY_LEGACY_ID = {item.legacy_id: item for item in SEO_COMPATIBILITY_MAPPINGS}


def compatibility_manifest() -> tuple[dict[str, object], ...]:
    """Return stable metadata for legacy-to-current SEO selection relations."""
    return tuple({
        "legacy_id": item.legacy_id,
        "evaluator_ids": item.evaluator_ids,
        "relation": item.relation.value,
    } for item in SEO_COMPATIBILITY_MAPPINGS)


def resolve_selection_ids(values: tuple[str, ...] | list[str] | set[str]) -> frozenset[str]:
    """Resolve current IDs and explicit legacy aliases for one selection."""
    resolved: set[str] = set()
    for value in values:
        mapping = _MAPPINGS_BY_LEGACY_ID.get(value)
        if mapping is None:
            if value not in CURRENT_SEO_EVALUATOR_IDS:
                raise ValueError(f"unknown SEO check ID: {value}")
            resolved.add(value)
            continue
        if not mapping.evaluator_ids:
            raise ValueError(
                f"SEO check ID '{value}' is {mapping.relation.value} and has no canonical v2 evaluator"
            )
        missing = set(mapping.evaluator_ids) - CURRENT_SEO_EVALUATOR_IDS
        if missing:
            raise ValueError(
                f"SEO compatibility mapping '{value}' references absent evaluator(s): {sorted(missing)}"
            )
        resolved.update(mapping.evaluator_ids)
    return frozenset(resolved)


def normalize_selection(
    include: tuple[str, ...] | list[str] | set[str],
    exclude: tuple[str, ...] | list[str] | set[str],
) -> SeoSelection:
    """Normalize both filters into one canonical namespace."""
    return SeoSelection(resolve_selection_ids(include), resolve_selection_ids(exclude))
