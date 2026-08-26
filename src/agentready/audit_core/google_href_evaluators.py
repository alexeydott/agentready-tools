"""Frozen GOOGLE-HREF-001/003/004@1.0.0 evaluators (Stage E6).

Binds three frozen catalog rules in the ``google-hreflang`` module following
the E0 canary pattern of :mod:`agentready.audit_core.evaluator_registry`.

Two rules (GOOGLE-HREF-002 and GOOGLE-HREF-005) are
``declared_not_producible`` because their catalog-title conditions require
cross-page facts not available in the declared ``{page}`` or ``{page, links}``
fact families:

- **GOOGLE-HREF-002** ("cluster is reciprocal across all listed URLs"):
  Reciprocity requires hreflang observations from other cluster pages;
  ``{page}`` does not provide the required cross-page facts.
- **GOOGLE-HREF-005** ("target URLs are canonical and not blocked"):
  Canonical/indexability of hreflang target URLs requires facts about the
  target pages; ``{page, links}`` for the current subject cannot establish
  those properties.

Each bound evaluator is a pure offline function operating on pre-collected
page fact values (no HTTP, browser, parsing, or sqlite imports).

Fact-availability semantics (block_on_missing_facts):

- ``page.hreflang`` key absent or not a list → **UNKNOWN** (escalated to
  ``error`` by the block policy).
- ``page.hreflang`` present but empty → **PASS** (vacuously valid —
  single-language page carries no hreflang annotations to violate).
- ``page.hreflang`` present with entries → evaluated per rule condition.

Payload shape (``page@1``)::

    {
        "hreflang": [{"lang": str, "href": str}, ...],
        "canonicals": [str, ...],
        "meta_robots": [str, ...],
        ...
    }
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .contracts import EvaluationOutcome, EvidenceRef
from .evaluator_registry import (
    EvaluatorRegistry,
    EvaluatorResult,
    register_expected_contract,
    _EXPECTED_CONTRACTS,
)
from .evaluator_registry import evaluate_frozen_rule as _evaluate_frozen_rule
from .evaluator_registry import CanaryEvaluation

__all__ = [
    "GOOGLE_HREF_RULE_IDS",
    "GOOGLE_HREF_RULE_VERSION",
    "GOOGLE_HREF_EVALUATOR_REGISTRY",
    "evaluate_google_href",
]

# Only bound rules — 002/005 are declared_not_producible.
GOOGLE_HREF_RULE_IDS = (
    "GOOGLE-HREF-001",
    "GOOGLE-HREF-003",
    "GOOGLE-HREF-004",
)
GOOGLE_HREF_RULE_VERSION = "1.0.0"

# Legacy BCP47 code regex from seo_checks.py line 641.
_HREFLANG_CODE_RE = re.compile(r"^(x-default|[a-z]{2,3}(-[a-zA-Z0-9]{2,8})*)$")


def _value(fact: Any, key: str) -> Any:
    if isinstance(fact, Mapping):
        return fact.get(key)
    return getattr(fact, key, None)


def _hreflang_key_present(fact: Any) -> bool:
    """True when the page fact contains an hreflang key with a list value."""
    if not isinstance(fact, Mapping):
        return False
    rows = fact.get("hreflang")
    return isinstance(rows, (list, tuple))


def _hreflang_rows(fact: Any) -> list[dict[str, str]]:
    rows = _value(fact, "hreflang")
    if not isinstance(rows, (list, tuple)):
        return []
    return [{"lang": str(r.get("lang", "")), "href": str(r.get("href", ""))} for r in rows if isinstance(r, Mapping)]


def _canonicals(page: Any) -> list[str]:
    rows = _value(page, "canonicals")
    if not isinstance(rows, (list, tuple)):
        return []
    return [str(c) for c in rows if isinstance(c, str) and c.strip()]


def _meta_robots(page: Any) -> list[str]:
    rows = _value(page, "meta_robots")
    if not isinstance(rows, (list, tuple)):
        return []
    return [str(r).strip() for r in rows if isinstance(r, str) and r.strip()]


def _is_blocked(meta_robots: list[str]) -> bool:
    return bool({"noindex", "none"} & {r.lower() for r in meta_robots})


def _normalize_href_matches_target(href: str, target: str) -> bool:
    from urllib.parse import urlsplit

    try:
        t = urlsplit(target)._replace(fragment="", query="").geturl().rstrip("/")
        h = urlsplit(href)._replace(fragment="", query="").geturl().rstrip("/")
        return h == t
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Evaluators (bound rules only)
# ---------------------------------------------------------------------------

def _href_001_valid_codes(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """HREF-001: every declared hreflang annotation declares a valid language-region code."""
    page = facts["page"]
    if not _hreflang_key_present(page):
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            "hreflang field unavailable or not a list in page fact",
        )
    rows = _hreflang_rows(page)
    if not rows:
        return EvaluatorResult(
            EvaluationOutcome.PASS,
            "no hreflang annotations; single-language page — vacuously valid",
            (EvidenceRef("page:hreflang", target, "no annotations to validate"),),
        )
    invalid = [r["lang"] for r in rows if not _HREFLANG_CODE_RE.match(r["lang"])]
    if invalid:
        bad = sorted(set(invalid))
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            f"{len(invalid)} hreflang annotation(s) with invalid code(s): {', '.join(bad[:5])}",
            (EvidenceRef("page:hreflang", target, f"invalid codes: {', '.join(bad[:3])}"),),
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        f"all {len(rows)} hreflang annotation(s) declare a valid language code",
        (EvidenceRef("page:hreflang", target, f"{len(rows)} valid annotation(s)"),),
    )


def _href_003_self_reference(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """HREF-003: cluster includes a self-referencing entry."""
    page = facts["page"]
    if not _hreflang_key_present(page):
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            "hreflang field unavailable or not a list in page fact",
        )
    rows = _hreflang_rows(page)
    if not rows:
        return EvaluatorResult(
            EvaluationOutcome.PASS,
            "no hreflang annotations; single-language page — vacuously valid",
            (EvidenceRef("page:hreflang", target, "no annotations to check"),),
        )
    self_refs = [r for r in rows if _normalize_href_matches_target(r["href"], target)]
    if self_refs:
        return EvaluatorResult(
            EvaluationOutcome.PASS,
            f"self-referencing entry found ({self_refs[0]['lang']})",
            (EvidenceRef("page:hreflang", target, f"self-reference: {self_refs[0]['lang']}"),),
        )
    return EvaluatorResult(
        EvaluationOutcome.FAIL,
        "no hreflang annotation references the current URL",
        (EvidenceRef("page:hreflang", target, "no self-referencing hreflang link"),),
    )


def _href_004_x_default(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """HREF-004: x-default hreflang entry is present for language-neutral fallback (diagnostic)."""
    page = facts["page"]
    if not _hreflang_key_present(page):
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            "hreflang field unavailable or not a list in page fact",
        )
    rows = _hreflang_rows(page)
    if not rows:
        return EvaluatorResult(
            EvaluationOutcome.PASS,
            "no hreflang annotations; single-language page — vacuously valid",
            (EvidenceRef("page:hreflang", target, "no annotations to check"),),
        )
    xd = [r for r in rows if r["lang"].lower() == "x-default"]
    if xd:
        return EvaluatorResult(
            EvaluationOutcome.PASS,
            f"x-default hreflang entry present (href: {xd[0]['href']})",
            (EvidenceRef("page:hreflang", target, "x-default present"),),
        )
    return EvaluatorResult(
        EvaluationOutcome.FAIL,
        "no x-default hreflang entry found for language-neutral fallback",
        (EvidenceRef("page:hreflang", target, "x-default missing"),),
    )


# ---------------------------------------------------------------------------
# Deferred rules (not registered — declared_not_producible)
# ---------------------------------------------------------------------------

def _href_002_deferred(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """HREF-002: DEFERRED — reciprocity requires cross-page facts unavailable in {page}."""
    return EvaluatorResult(
        EvaluationOutcome.UNKNOWN,
        "deferred: reciprocity requires hreflang observations from other cluster pages",
    )


def _href_005_deferred(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """HREF-005: DEFERRED — target canonical/indexability requires facts about target pages."""
    return EvaluatorResult(
        EvaluationOutcome.UNKNOWN,
        "deferred: target canonical/indexability requires facts about the target pages",
    )


# ---------------------------------------------------------------------------
# Registry wiring (bound rules only)
# ---------------------------------------------------------------------------

_HREF_EVALUATORS = {
    "GOOGLE-HREF-001": _href_001_valid_codes,
    "GOOGLE-HREF-003": _href_003_self_reference,
    "GOOGLE-HREF-004": _href_004_x_default,
}

# Catalog-exact contract rows for bound rules only.
_HREF_CONTRACTS: list[tuple[str, tuple[tuple[str, str], ...], str, str, str, str]] = [
    ("GOOGLE-HREF-001", (("page", "1"), ("links", "1")), "scored", "block_on_missing_facts", "composite_check", "scored_rule"),
    ("GOOGLE-HREF-003", (("page", "1"), ("links", "1")), "scored", "block_on_missing_facts", "composite_check", "scored_rule"),
    ("GOOGLE-HREF-004", (("page", "1"),),               "diagnostic", "unknown_on_missing_facts", "atomic_check", "diagnostic_rule"),
]

for rule_id, facts, score_role, failure_policy, mechanism, rule_kind in _HREF_CONTRACTS:
    register_expected_contract(
        rule_id,
        GOOGLE_HREF_RULE_VERSION,
        scope="html-page",
        condition="applies whenever a html-page subject was collected for the run",
        facts=facts,
        score_role=score_role,
        failure_policy=failure_policy,
        mechanism=mechanism,
        rule_kind=rule_kind,
        automation_mode="automated",
    )

GOOGLE_HREF_EVALUATOR_REGISTRY = EvaluatorRegistry(
    tuple(
        (rule_id, GOOGLE_HREF_RULE_VERSION, _HREF_EVALUATORS[rule_id])
        for rule_id in GOOGLE_HREF_RULE_IDS
    ),
    allowlist=frozenset((rule_id, GOOGLE_HREF_RULE_VERSION) for rule_id in GOOGLE_HREF_RULE_IDS),
    expected_contracts=dict(_EXPECTED_CONTRACTS),
)


def evaluate_google_href(
    target: str,
    facts,
    **kwargs: Any,
) -> CanaryEvaluation:
    """Named Stage E6 convenience entry point over :func:`evaluate_frozen_rule`."""
    kwargs.setdefault("registry", GOOGLE_HREF_EVALUATOR_REGISTRY)
    kwargs.setdefault("rule_version", GOOGLE_HREF_RULE_VERSION)
    return _evaluate_frozen_rule(target, facts, **kwargs)
