"""Frozen CORE-CANON-002..008 evaluator bindings (Stage E2, issue #24).

This module binds the seven core-canonical catalog rules to pure,
deterministic evaluators following the E0 canary pattern established in
:mod:`agentready.audit_core.evaluator_registry`. The evaluators perform no
HTTP/browser/provider/parsing/sqlite access and no collection I/O; they are
pure functions over pre-collected fact payloads.

Deterministic fact payload shapes (values of the ``facts`` mapping keyed by
fact family; each value is the payload dict carried by the matching
``FactEnvelope``):

- ``page@1``      -> ``{"status_code": int, "content_type": str,
                     "canonicals": [str], "meta_robots": [str]}``
                    where ``canonicals`` lists every declared canonical URL
                    (link and header declarations in document order) and
                    ``meta_robots`` lists raw robots directive tokens.
- ``links@1``     -> ``{"links": [{"resolved_url": str, "rel": str,
                     "element": str}]}`` with one entry per anchor/link
                    element observed on the page.
- ``transport@1`` -> ``{"final_url": str, "redirect_chain": [str],
                     "origin": str}`` where ``origin`` is the audited
                    scheme://host origin of the run target.

Evaluation semantics per rule (deterministic, no legacy thresholds):

- CORE-CANON-002 PASS iff exactly one canonical is declared and it shares
  scheme+host with the transport ``origin``.
- CORE-CANON-003 PASS iff no robots directive disallows canonicalization
  (no ``noindex``/``none``/``nofollow`` token on the page).
- CORE-CANON-004 diagnostic: PASS iff the single canonical does not appear
  inside the redirect chain; UNKNOWN outcome when facts are ambiguous.
- CORE-CANON-005 PASS iff the single self-referencing canonical equals the
  requested URL for paginated pages.
- CORE-CANON-006 observation_only: PASS iff no parameter-only duplicate
  variant of the canonical exists among resolved links.
- CORE-CANON-007 PASS iff all cross-domain canonical targets across the
  crawl resolve to a single consistent destination.
- CORE-CANON-008 PASS iff exactly one canonical is declared per page.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .contracts import EvidenceRef
from .evaluator_registry import (
    ExpectedContract,
    EvaluatorRegistry,
    EvaluatorResult,
    evaluate_frozen_rule,
)
from .models import EvaluationOutcome

__all__ = [
    "CANON_RULE_VERSION",
    "CANON_RULE_IDS",
    "CANON_EVALUATOR_REGISTRY",
    "CanonEvaluation",
    "evaluate_canon_rule",
]

CANON_RULE_VERSION = "1.0.0"
CANON_RULE_IDS = (
    "CORE-CANON-002",
    "CORE-CANON-003",
    "CORE-CANON-004",
    "CORE-CANON-005",
    "CORE-CANON-006",
    "CORE-CANON-007",
    "CORE-CANON-008",
)

_EXPECTED_SCOPE = "html-page"
_EXPECTED_CONDITION = "applies whenever a html-page subject was collected for the run"
_EXPECTED_AUTOMATION = "automated"

# (rule_id, facts, score_role, failure_policy, mechanism, rule_kind)
_CONTRACT_ROWS: tuple[tuple[str, tuple[tuple[str, str], ...], str, str, str, str], ...] = (
    (
        "CORE-CANON-002",
        (("page", "1"), ("transport", "1")),
        "scored",
        "block_on_missing_facts",
        "composite_check",
        "scored_rule",
    ),
    (
        "CORE-CANON-003",
        (("page", "1"),),
        "scored",
        "block_on_missing_facts",
        "atomic_check",
        "scored_rule",
    ),
    (
        "CORE-CANON-004",
        (("page", "1"), ("transport", "1")),
        "diagnostic",
        "unknown_on_missing_facts",
        "composite_check",
        "diagnostic_rule",
    ),
    (
        "CORE-CANON-005",
        (("page", "1"), ("transport", "1")),
        "scored",
        "block_on_missing_facts",
        "composite_check",
        "scored_rule",
    ),
    (
        "CORE-CANON-006",
        (("page", "1"), ("run-projection", "1")),
        "observation_only",
        "unknown_on_missing_facts",
        "atomic_check",
        "observation_rule",
    ),
    (
        "CORE-CANON-007",
        (("page", "1"), ("run-projection", "1")),
        "scored",
        "block_on_missing_facts",
        "composite_check",
        "scored_rule",
    ),
    (
        "CORE-CANON-008",
        (("page", "1"),),
        "scored",
        "block_on_missing_facts",
        "composite_check",
        "scored_rule",
    ),
)


def _expected_contracts() -> dict[tuple[str, str], ExpectedContract]:
    contracts: dict[tuple[str, str], ExpectedContract] = {}
    for rule_id, facts, score_role, failure_policy, mechanism, rule_kind in _CONTRACT_ROWS:
        contracts[(rule_id, CANON_RULE_VERSION)] = ExpectedContract(
            rule_id=rule_id,
            version=CANON_RULE_VERSION,
            scope=_EXPECTED_SCOPE,
            condition=_EXPECTED_CONDITION,
            facts=facts,
            score_role=score_role,
            failure_policy=failure_policy,
            mechanism=mechanism,
            rule_kind=rule_kind,
            automation_mode=_EXPECTED_AUTOMATION,
        )
    return contracts


def _single(fact: Any, key: str) -> Any:
    if isinstance(fact, Mapping):
        return fact.get(key)
    return getattr(fact, key, None)


def _canonicals(page: Any) -> list[str]:
    canonicals = _single(page, "canonicals")
    if not isinstance(canonicals, (list, tuple)):
        return []
    return [str(item) for item in canonicals]


def _scheme_host(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.scheme.lower(), parts.netloc.lower()


def _canonical_evaluator(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    page = facts["page"]
    transport = facts["transport"]
    canonicals = _canonicals(page)
    if len(canonicals) != 1:
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            f"expected exactly one declared canonical, found {len(canonicals)}",
        )
    canonical_scheme, canonical_host = _scheme_host(canonicals[0])
    origin = str(_single(transport, "origin") or "")
    origin_scheme, origin_host = _scheme_host(origin)
    if (canonical_scheme, canonical_host) == (origin_scheme, origin_host):
        return EvaluatorResult(
            EvaluationOutcome.PASS,
            "the declared canonical shares the scheme and host of the audited origin",
            (
                EvidenceRef("page:canonical", target, f"declared canonical: {canonicals[0]}"),
                EvidenceRef("transport:origin", target, f"audited origin: {origin}"),
            ),
        )
    return EvaluatorResult(
        EvaluationOutcome.FAIL,
        (
            f"canonical {canonicals[0]} uses scheme/host "
            f"{canonical_scheme}://{canonical_host} instead of the audited origin "
            f"{origin_scheme}://{origin_host}"
        ),
    )


def _robots_directives_evaluator(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    page = facts["page"]
    directives = _single(page, "meta_robots")
    tokens: list[str] = []
    if isinstance(directives, (list, tuple)):
        tokens = [str(item).strip().lower() for item in directives]
    blocking = {"noindex", "none"}
    blocked = sorted(token for token in tokens if token in blocking)
    if blocked:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            f"robots directives block indexing/canonicalization: {', '.join(blocked)}",
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        "no robots directive blocks canonicalization of this page",
        (EvidenceRef("page:meta-robots", target, f"robots directives observed on {target}"),),
    )


def _redirect_chain_evaluator(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    page = facts["page"]
    transport = facts["transport"]
    canonicals = _canonicals(page)
    if len(canonicals) != 1:
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            f"expected exactly one declared canonical, found {len(canonicals)}",
        )
    canonical = canonicals[0]
    chain: list[str] = []
    redirect_chain = _single(transport, "redirect_chain")
    if isinstance(redirect_chain, (list, tuple)):
        chain = [str(item) for item in redirect_chain]
    non_initial = chain[1:]
    if canonical in non_initial:
        position = chain.index(canonical) + 1
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            f"canonical {canonical} points into a redirect chain at hop {position}",
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        "the declared canonical is not part of an observed redirect chain",
        (EvidenceRef("page:canonical", target, f"declared canonical: {canonical}"),),
    )


def _self_paginated_evaluator(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    page = facts["page"]
    transport = facts["transport"]
    canonicals = _canonicals(page)
    if len(canonicals) != 1:
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            f"expected exactly one declared canonical, found {len(canonicals)}",
        )
    canonical = canonicals[0]
    final_url = str(_single(transport, "final_url") or "")
    link_rows = page.get("links", []) if isinstance(page.get("links"), (list, tuple)) else []
    paginated = any(
        str(row.get("rel", "")).strip().lower() in {"next", "prev"}
        for row in link_rows
        if isinstance(row, dict)
    )
    if paginated and canonical != final_url:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            (
                f"paginated page declares canonical {canonical} instead of the "
                f"requested URL {final_url}"
            ),
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        "the declared canonical matches the requested URL for this paginated page",
        (EvidenceRef("page:canonical", target, f"declared canonical: {canonical}"),),
    )


def _parameter_duplicates_evaluator(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    page = facts["page"]
    canonicals = _canonicals(page)
    if len(canonicals) != 1:
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            f"expected exactly one declared canonical, found {len(canonicals)}",
        )
    canonical_parts = urlsplit(canonicals[0])
    variants = _single(facts["run-projection"], "parameter_variants")
    variant_urls: list[str] = []
    if isinstance(variants, (list, tuple)):
        variant_urls = [str(item) for item in variants]
    duplicates: list[str] = []
    for variant in variant_urls:
        parts = urlsplit(variant)
        same_path = (parts.scheme, parts.netloc, parts.path) == (
            canonical_parts.scheme,
            canonical_parts.netloc,
            canonical_parts.path,
        )
        if same_path and parts.query:
            duplicates.append(variant)
    if duplicates:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            f"parameter-only duplicate variants exist without distinct canonicals: "
            f"{', '.join(sorted(duplicates))}",
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        "no parameter-only duplicate variant competes with the declared canonical",
        (EvidenceRef("page:canonical", target, f"declared canonical: {canonicals[0]}"),),
    )


def _cross_domain_consistency_evaluator(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    page = facts["page"]
    projection = facts["run-projection"]
    canonicals = _canonicals(page)
    if len(canonicals) != 1:
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            f"expected exactly one declared canonical, found {len(canonicals)}",
        )
    canonical = canonicals[0]
    canonical_scheme, canonical_host = _scheme_host(canonical)
    origin = target
    origin_scheme, origin_host = _scheme_host(origin)
    if (canonical_scheme, canonical_host) == (origin_scheme, origin_host):
        return EvaluatorResult(
            EvaluationOutcome.PASS,
            "the declared canonical stays on the audited origin; cross-domain consistency holds trivially",
            (EvidenceRef("page:canonical", target, f"declared canonical: {canonical}"),),
        )
    targets = _single(projection, "cross_domain_targets")
    observed: list[str] = []
    if isinstance(targets, (list, tuple)):
        observed = [str(item) for item in targets]
    destinations = sorted({canonical, *observed})
    if len(destinations) > 1:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            f"cross-domain canonical targets disagree across the crawl: {', '.join(destinations)}",
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        "cross-domain canonical targets agree on a single destination",
        (EvidenceRef("page:canonical", target, f"declared canonical: {canonical}"),),
    )


def _declared_once_evaluator(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    page = facts["page"]
    canonicals = _canonicals(page)
    if len(canonicals) == 1:
        return EvaluatorResult(
            EvaluationOutcome.PASS,
            "exactly one canonical URL is declared for this page",
            (EvidenceRef("page:canonical", target, f"declared canonical: {canonicals[0]}"),),
        )
    if len(canonicals) == 0:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            "no canonical URL is declared for this page",
        )
    return EvaluatorResult(
        EvaluationOutcome.FAIL,
        f"{len(canonicals)} canonical URLs are declared for this page: {', '.join(canonicals)}",
    )


_EVALUATORS = {
    "CORE-CANON-002": _canonical_evaluator,
    "CORE-CANON-003": _robots_directives_evaluator,
    "CORE-CANON-004": _redirect_chain_evaluator,
    "CORE-CANON-005": _self_paginated_evaluator,
    "CORE-CANON-006": _parameter_duplicates_evaluator,
    "CORE-CANON-007": _cross_domain_consistency_evaluator,
    "CORE-CANON-008": _declared_once_evaluator,
}

CANON_EVALUATOR_REGISTRY = EvaluatorRegistry(
    tuple(
        (rule_id, CANON_RULE_VERSION, _EVALUATORS[rule_id])
        for rule_id in CANON_RULE_IDS
    ),
    allowlist=frozenset((rule_id, CANON_RULE_VERSION) for rule_id in CANON_RULE_IDS),
    expected_contracts=_expected_contracts(),
)


@dataclass(frozen=True, slots=True)
class CanonEvaluation:
    """Named result wrapper mirroring :class:`CanaryEvaluation`."""

    binding: Any
    readiness: Any
    finding: Any
    report: Any


def evaluate_canon_rule(
    rule_id: str,
    target: str,
    facts: Iterable[object],
    **kwargs: Any,
) -> CanonEvaluation:
    """Generic bind/evaluate entry point for the core-canonical family."""
    kwargs.setdefault("rule_id", rule_id)
    kwargs.setdefault("registry", CANON_EVALUATOR_REGISTRY)
    kwargs.setdefault("rule_version", CANON_RULE_VERSION)
    evaluation = evaluate_frozen_rule(target, facts, **kwargs)
    return CanonEvaluation(
        binding=evaluation.binding,
        readiness=evaluation.readiness,
        finding=evaluation.finding,
        report=evaluation.report,
    )
