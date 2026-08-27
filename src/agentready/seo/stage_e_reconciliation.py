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
    RETIRED = "RETIRED"
    PLAN_NO_LONGER_APPLICABLE = "PLAN_NO_LONGER_APPLICABLE"
    UNBLOCKED = "UNBLOCKED"
    INTENTIONALLY_UNBOUND = "INTENTIONALLY_UNBOUND"


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
        ReconciliationClassification.RETIRED,
        "retired from v0.14.0 scope — catalog has ungoverned ROBOTS-SITEMAP-* rules covering same fact families but no semantic/evaluator binding; adding governed rules requires new catalog revision beyond final cutover",
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
        ReconciliationClassification.RETIRED,
        "retired from v0.14.0 scope — duplicate detection remains legacy/current functionality; no frozen evaluator identity created",
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
        ReconciliationClassification.RETIRED,
        "retired from v0.14.0 scope — follows #23 governance disposition; no catalog binding",
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
        ReconciliationClassification.INTENTIONALLY_UNBOUND,
        "intentionally unbound: intent.indexability is out of scope for v0.14.0; rules kept unbound by reviewed governance decision",
        "intent.indexability-dependent technical and provider rules",
    ),
    *_refs(
        31,
        ("GOOGLE-DESC-001", "GOOGLE-TITLE-001"),
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "accept the catalog-defined role/facts exactly; legacy observation-only and content.main-gated semantics are not binding here",
        "catalog-authoritative exact per-rule contract",
    ),
    *_refs(
        32,
        ("GOOGLE-TITLE-001",),
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "accept the catalog-defined title contract exactly; do not add an unrecorded content.main prerequisite",
        "catalog-authoritative exact per-rule contract",
    ),
    *_refs(
        33,
        ("GOOGLE-TITLE-001",),
        ReconciliationClassification.SEMANTIC_MISMATCH,
        "accept the catalog-defined title contract exactly; legacy length-threshold wording is not binding",
        "catalog-authoritative exact per-rule contract",
    ),
)

_MISSING_RULE_SEMANTICS: dict[str, str] = {
    "CORE-ROBOTS-001": "robots.txt fetch state is known",
    "CORE-ROBOTS-002": "robots.txt is parsed under an explicit versioned REP profile",
    "CORE-ROBOTS-003": "robots policy is consistent with explicit intent.indexability",
    "CORE-ROBOTS-004": "robots blocking does not hide a noindex directive",
    "CORE-SITEMAP-001": "sitemap discovery state is known",
    "CORE-SITEMAP-002": "sitemap fetch state is known",
    "CORE-SITEMAP-003": "sitemap parse state is known",
    "CORE-SITEMAP-004": "sitemap URLs are absolute and valid",
    "CORE-SITEMAP-005": "sitemap contains preferred/canonical URLs",
    "CORE-SITEMAP-006": "sitemap URLs are not redirect URLs",
    "CORE-SITEMAP-007": "sitemap URLs do not return 4xx/5xx",
    "CORE-SITEMAP-008": "sitemap preferred URLs are not marked noindex",
    "CORE-DUP-001": "exact duplicate clusters use content.hash and canonical facts",
    "CORE-DUP-002": "near-duplicate clusters use content.signatures as observation-only data",
    "CORE-HTTP-002": "HTTP/indexability consistency is evaluated only with explicit intent.indexability",
    "GOOGLE-IDX-001": "Google indexability intent-dependent rule from issue #30",
    "GOOGLE-IDX-002": "Google indexability outcome rule requiring explicit intent provenance",
    "YANDEX-IDX-001": "Yandex indexability intent-dependent rule from issue #30",
    "YANDEX-IDX-002": "Yandex indexability outcome rule requiring explicit intent provenance",
}


def _catalog_entry(entry: Any) -> dict[str, object]:
    return {
        "rule_id": entry.rule_id,
        "version": entry.version,
        "title": entry.title,
        "scope": entry.scope,
        "applicability_condition": entry.condition,
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
        planned_semantics = (
            reference.planned_semantics
            if entry is not None
            else _MISSING_RULE_SEMANTICS.get(
                reference.planned_rule_id,
                reference.planned_semantics,
            )
        )
        if reference.classification == ReconciliationClassification.RETIRED:
            resolution_status = "retired"
        elif reference.classification == ReconciliationClassification.INTENTIONALLY_UNBOUND:
            resolution_status = "intentionally_unbound"
        elif entry is not None:
            resolution_status = "resolved_catalog_authoritative"
        else:
            resolution_status = "blocked_missing_catalog"
        row: dict[str, object] = {
            "issue": reference.issue,
            "planned_rule_id": reference.planned_rule_id,
            "classification": reference.classification,
            "disposition": reference.disposition,
            "planned_semantics": planned_semantics,
            "catalog": _catalog_entry(entry) if entry is not None else None,
            "effective_contract": _catalog_entry(entry) if entry is not None else None,
            "resolution_status": resolution_status,
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
        "issues": list(range(22, 35)),
        "issue_dispositions": [
            {
                "issue": 23,
                "classification": ReconciliationClassification.RETIRED,
                "disposition": (
                    "governance-only: all planned IDs retired from v0.14.0 scope "
                    "(see docs/governance-disposition-23-25-29.md)"
                ),
            },
            {
                "issue": 25,
                "classification": ReconciliationClassification.RETIRED,
                "disposition": (
                    "governance-only: all planned IDs retired from v0.14.0 scope "
                    "(see docs/governance-disposition-23-25-29.md)"
                ),
            },
            {
                "issue": 29,
                "classification": ReconciliationClassification.RETIRED,
                "disposition": (
                    "governance-only: all planned IDs retired from v0.14.0 scope "
                    "(see docs/governance-disposition-23-25-29.md)"
                ),
            },
            {
                "issue": 30,
                "classification": ReconciliationClassification.INTENTIONALLY_UNBOUND,
                "disposition": (
                    "intent.indexability is out of scope for v0.14.0; all "
                    "dependent rules intentionally unbound by reviewed governance decision"
                ),
            },
            {
                "issue": 34,
                "classification": ReconciliationClassification.UNBLOCKED,
                "disposition": (
                    "final cutover/re-freeze for v0.14.0 is now unblocked — all "
                    "dependent issues have reviewed dispositions (resolved, retired, or intentionally unbound)"
                ),
            },
        ],
        "rows": rows,
    }


def stage_e_binding_is_blocked(
    matrix: Mapping[str, object] | None = None,
    *,
    issue: int | None = None,
    rule_id: str | None = None,
) -> bool:
    """Return the fail-closed pre-binding state required by issue #42.

    The caller cannot bypass unresolved rows by toggling ``binding_allowed``.
    A future binding-capable matrix must have every row resolved to MATCH,
    carry a catalog entry with a version and applicability condition, and
    contain no missing or mismatched issue-level dispositions.
    """
    if matrix is None:
        return True
    if matrix.get("authority") != "catalog-authoritative":
        return True
    rows = matrix.get("rows")
    if not isinstance(rows, list) or not rows:
        return True
    if issue is not None:
        rows = [row for row in rows if isinstance(row, Mapping) and row.get("issue") == issue]
        dispositions = [
            item for item in matrix.get("issue_dispositions", [])
            if isinstance(item, Mapping) and item.get("issue") == issue
        ]
    else:
        dispositions = matrix.get("issue_dispositions", [])
    if rule_id is not None:
        rows = [row for row in rows if row.get("planned_rule_id") == rule_id]
    if not rows:
        return True
    _bindable_statuses = {"resolved_catalog_authoritative"}
    _terminal_statuses = _bindable_statuses | {"retired", "intentionally_unbound"}
    for row in rows:
        if not isinstance(row, Mapping):
            return True
        status = row.get("resolution_status")
        if status not in _terminal_statuses:
            return True
        if status not in _bindable_statuses:
            return True
        contract = row.get("effective_contract")
        if not isinstance(contract, Mapping) or not contract.get("version") or not contract.get("applicability_condition"):
            return True
    if not isinstance(dispositions, list) or any(
        not isinstance(item, Mapping)
        or item.get("classification") == ReconciliationClassification.PLAN_NO_LONGER_APPLICABLE
        for item in dispositions
    ):
        return True
    if matrix.get("binding_allowed") is not True:
        return True
    return False
