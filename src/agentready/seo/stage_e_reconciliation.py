"""Stage E/F plan-to-catalog reconciliation metadata (#42).

This module is governance metadata only.  It deliberately does not register,
bind, evaluate, or score any frozen rule.  The catalog-authoritative decision
keeps the accepted ``2.1.0-draft.1`` identity unchanged while requiring every
dependent issue to reconcile its plan against the loaded snapshot first.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agentready.audit_core.rule_catalog import RuleCatalogSnapshot

__all__ = [
    "ReconciliationClassification",
    "StageEPlanReference",
    "STAGE_E_PLAN_REFERENCES",
    "build_stage_e_reconciliation_matrix",
    "stage_e_binding_is_blocked",
]


class ReconciliationClassification:
    MATCH = "MATCH"
    SEMANTIC_MISMATCH = "SEMANTIC_MISMATCH"
    MISSING_FROM_CATALOG = "MISSING_FROM_CATALOG"
    PLAN_NO_LONGER_APPLICABLE = "PLAN_NO_LONGER_APPLICABLE"


@dataclass(frozen=True, slots=True)
class StageEPlanReference:
    issue: int
    planned_rule_id: str
    classification: str
    disposition: str
    planned_semantics: str


def _refs(issue: int, rule_ids: tuple[str, ...], classification: str, disposition: str, semantics: str) -> tuple[StageEPlanReference, ...]:
    return tuple(
        StageEPlanReference(issue, rule_id, classification, disposition, semantics)
        for rule_id in rule_ids
    )


STAGE_E_PLAN_REFERENCES: tuple[StageEPlanReference, ...] = (
    *_refs(
        22,
        ("CORE-COVERAGE-001",),
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "replan #22 against the catalog entry before binding; no evaluator is enabled by #42",
        "run-scoped guard-only coverage completeness over audit.coverage",
    ),
    *_refs(
        23,
        (
            "CORE-ROBOTS-001",
            "CORE-ROBOTS-002",
            "CORE-SITEMAP-001",
            "CORE-SITEMAP-002",
            "CORE-SITEMAP-003",
            "CORE-SITEMAP-004",
            "CORE-ROBOTS-003",
            "CORE-ROBOTS-004",
            "CORE-SITEMAP-005",
            "CORE-SITEMAP-008",
        ),
        ReconciliationClassification.MISSING_FROM_CATALOG,
        "retain as blocked plan IDs; replace with explicitly selected robots-sitemap catalog IDs in a follow-up plan",
        "atomic robots/sitemap state and URL validity rules",
    ),
    *_refs(
        24,
        tuple(f"CORE-CANON-{index:03d}" for index in range(1, 9)),
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "rewrite #24 acceptance text from the loaded catalog metadata before implementation",
        "mechanism-specific canonical target, redirect, robots, conflict, and observation checks",
    ),
    *_refs(
        25,
        ("CORE-DUP-001", "CORE-DUP-002"),
        ReconciliationClassification.MISSING_FROM_CATALOG,
        "retain duplicate work as blocked until catalog IDs are intentionally added by a reviewed catalog change",
        "exact and near duplicate cluster semantics",
    ),
    *_refs(
        26,
        ("CORE-CANON-001",),
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "rewrite #26 to the catalog entry; keep review-gating as plan policy until catalog governance changes it",
        "review-gated duplicate-strategy canonical rule",
    ),
    *_refs(
        27,
        tuple(f"CORE-LINK-{index:03d}" for index in range(1, 7)),
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "rewrite #27 per catalog score role, failure policy, and fact requirements",
        "fact-ready link mechanisms plus explicit compatibility-only behavior",
    ),
    *_refs(
        28,
        tuple(f"GOOGLE-HREF-{index:03d}" for index in range(1, 6)),
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "rewrite #28 to the catalog title/fact/role mapping; do not swap meanings by evaluator code",
        "hreflang code, reciprocity, self-reference, x-default, and target consistency",
    ),
    *_refs(
        29,
        (
            "CORE-ROBOTS-004",
            "CORE-SITEMAP-005",
            "CORE-SITEMAP-006",
            "CORE-SITEMAP-007",
            "CORE-SITEMAP-008",
            "CORE-ROBOTS-003",
        ),
        ReconciliationClassification.MISSING_FROM_CATALOG,
        "keep dependent robots/sitemap work blocked until each ID has an explicit catalog disposition",
        "cross-family robots/sitemap consistency rules",
    ),
    StageEPlanReference(
        30,
        "CORE-LINK-002",
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "keep blocked until intent.indexability is explicitly defined and the catalog entry is reconciled",
        "intent-dependent link/indexability rule",
    ),
    *_refs(
        30,
        (
            "CORE-HTTP-002",
            "CORE-ROBOTS-003",
            "GOOGLE-IDX-001",
            "GOOGLE-IDX-002",
            "YANDEX-IDX-001",
            "YANDEX-IDX-002",
        ),
        ReconciliationClassification.MISSING_FROM_CATALOG,
        "keep intent-dependent rules unbound; create no inferred intent fact",
        "intent.indexability-dependent technical and provider rules",
    ),
    *_refs(
        31,
        ("GOOGLE-DESC-001", "GOOGLE-TITLE-001"),
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "rewrite #31 so description remains observation-only and title remains content.main-gated",
        "presentation-source rules without legacy length-threshold claims",
    ),
    *_refs(
        32,
        ("GOOGLE-TITLE-001",),
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "keep #32 as a prerequisite; define content.main before title binding",
        "title suitability requires html.title and content.main",
    ),
    *_refs(
        33,
        ("GOOGLE-TITLE-001",),
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "rewrite #33 against the same content.main-gated title contract",
        "title-source suitability without the legacy 30-65 threshold",
    ),
)


def _catalog_entry(entry: Any) -> dict[str, object]:
    return {
        "rule_id": entry.rule_id,
        "version": entry.version,
        "title": entry.title,
        "scope": entry.scope,
        "fact_requirements": [
            {"family": req.family, "min_schema_version": req.min_schema_version}
            for req in entry.fact_requirements
        ],
        "score_role": entry.score_role,
        "failure_policy": entry.failure_policy,
        "mechanism": entry.mechanism,
        "rule_kind": entry.rule_kind,
        "automation_mode": entry.automation_mode,
    }


def build_stage_e_reconciliation_matrix(
    snapshot: RuleCatalogSnapshot,
) -> dict[str, object]:
    """Build a deterministic machine-readable plan/catalog matrix."""
    by_id = {entry.rule_id: entry for entry in snapshot.entries}
    rows: list[dict[str, object]] = []
    for reference in STAGE_E_PLAN_REFERENCES:
        entry = by_id.get(reference.planned_rule_id)
        row: dict[str, object] = {
            "issue": reference.issue,
            "planned_rule_id": reference.planned_rule_id,
            "classification": reference.classification,
            "disposition": reference.disposition,
            "planned_semantics": reference.planned_semantics,
            "catalog": _catalog_entry(entry) if entry is not None else None,
        }
        rows.append(row)
    return {
        "schema": "agentready.stage-e-reconciliation.v1",
        "authority": "catalog-authoritative",
        "binding_allowed": False,
        "catalog": {
            "schema": snapshot.schema,
            "catalog_version": snapshot.catalog_version,
            "rule_catalog_digest": snapshot.rule_catalog_digest,
        },
        "issues": [22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33],
        "rows": rows,
    }


def stage_e_binding_is_blocked(
    matrix: Mapping[str, object] | None = None,
) -> bool:
    """Return the fail-closed pre-binding state required by issue #42."""
    if matrix is None:
        return True
    return matrix.get("authority") != "catalog-authoritative" or matrix.get("binding_allowed") is not True
