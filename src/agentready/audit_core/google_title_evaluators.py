"""Frozen GOOGLE-TITLE-001@1.0.0 evaluator (Stage E9).

Binds exactly one frozen catalog rule, ``GOOGLE-TITLE-001@1.0.0`` ("Title tag
is present and within recommended length"), following the E0 canary pattern of
:mod:`agentready.audit_core.evaluator_registry`.  The module is pure: no HTTP,
browser, provider, parsing, or sqlite imports; the page fact is pre-collected
upstream.

Payload shape
-------------
The evaluator consumes the ``page@1`` fact value only.  The expected payload
for a ``page`` envelope is::

    {
        "titles": [str],        # non-empty title texts observed on the page
        "descriptions": [str],  # meta description texts (informational)
        "status_code": int,
        "content_type": str,
    }

Recommended length band
-----------------------
PASS requires the single title's character length to fall within the closed
band ``[30, 65]``.  This matches the deterministic ``title-length`` heuristic
already used by the v2 SEO atomic-rule engine; the upper bound follows Google
Search Central's documented SERP title guidance ("titles should be neither too
long nor too short", commonly operationalized as roughly 50-65 characters),
while the lower bound guards against empty/near-empty titles that cannot
describe a page.  The band is a deterministic constant of this module and is
not derived from any SERP, provider, or AI-similarity input.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import EvaluationOutcome, EvidenceRef
from .evaluator_registry import (
    EvaluatorRegistry,
    EvaluatorResult,
    register_expected_contract,
)
from .evaluator_registry import evaluate_frozen_rule as _evaluate_frozen_rule
from .evaluator_registry import CanaryEvaluation

__all__ = [
    "GOOGLE_TITLE_RULE_ID",
    "GOOGLE_TITLE_RULE_VERSION",
    "GOOGLE_TITLE_MIN_LENGTH",
    "GOOGLE_TITLE_MAX_LENGTH",
    "GOOGLE_TITLE_EVALUATOR_REGISTRY",
    "bind_google_title_rule",
    "evaluate_google_title",
]

GOOGLE_TITLE_RULE_ID = "GOOGLE-TITLE-001"
GOOGLE_TITLE_RULE_VERSION = "1.0.0"

# Deterministic recommended title-length band in characters (inclusive).
from .rule_catalog import load_rule_semantics

_TITLE_CONDITION = load_rule_semantics().condition("GOOGLE-TITLE-001")
assert _TITLE_CONDITION is not None and _TITLE_CONDITION.length_band is not None
GOOGLE_TITLE_MIN_LENGTH = _TITLE_CONDITION.length_band.min
GOOGLE_TITLE_MAX_LENGTH = _TITLE_CONDITION.length_band.max


def _google_title_evaluator(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """Evaluate only the declared page fact value against the title band."""
    page = facts["page"]
    titles = _value(page, "titles")
    if titles is None:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            "page fact does not report any title element",
            _evidence(target),
        )
    if not isinstance(titles, (list, tuple)):
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            "page fact titles payload is malformed",
            _evidence(target),
        )
    cleaned = [str(item).strip() for item in titles]
    non_empty = [item for item in cleaned if item]
    if len(non_empty) == 0:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            "page has no non-empty title",
            _evidence(target),
        )
    if len(non_empty) > 1:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            f"page declares {len(non_empty)} title elements; exactly one is required",
            _evidence(target),
        )
    title = non_empty[0]
    length = len(title)
    if length < GOOGLE_TITLE_MIN_LENGTH:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            f"title is too short ({length} chars; recommended minimum "
            f"{GOOGLE_TITLE_MIN_LENGTH})",
            _evidence(target),
        )
    if length > GOOGLE_TITLE_MAX_LENGTH:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            f"title is too long ({length} chars; recommended maximum "
            f"{GOOGLE_TITLE_MAX_LENGTH})",
            _evidence(target),
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        f"{target} declares exactly one title within the recommended "
        f"{GOOGLE_TITLE_MIN_LENGTH}-{GOOGLE_TITLE_MAX_LENGTH} char band",
        _evidence(target),
    )


def _evidence(target: str) -> tuple[EvidenceRef, ...]:
    return (
        EvidenceRef(
            "page:title",
            target,
            "page fact reports the document title elements",
        ),
    )


def _value(fact: Any, key: str) -> Any:
    if isinstance(fact, Mapping):
        return fact.get(key)
    return getattr(fact, key, None)


register_expected_contract(
    GOOGLE_TITLE_RULE_ID,
    GOOGLE_TITLE_RULE_VERSION,
    facts=(("page", "1"),),
)

GOOGLE_TITLE_EVALUATOR_REGISTRY = EvaluatorRegistry(
    ((GOOGLE_TITLE_RULE_ID, GOOGLE_TITLE_RULE_VERSION, _google_title_evaluator),),
    allowlist=((GOOGLE_TITLE_RULE_ID, GOOGLE_TITLE_RULE_VERSION),),
)


def bind_google_title_rule():
    """Resolve the exact frozen google-title binding from the live catalog."""
    from .evaluator_registry import bind_frozen_rule

    return bind_frozen_rule(
        GOOGLE_TITLE_RULE_ID,
        GOOGLE_TITLE_RULE_VERSION,
        registry=GOOGLE_TITLE_EVALUATOR_REGISTRY,
    )


def evaluate_google_title(
    target: str,
    facts,
    **kwargs: Any,
) -> CanaryEvaluation:
    """Named Stage E9 convenience entry point over :func:`evaluate_frozen_rule`."""
    kwargs.setdefault("registry", GOOGLE_TITLE_EVALUATOR_REGISTRY)
    kwargs.setdefault("rule_id", GOOGLE_TITLE_RULE_ID)
    kwargs.setdefault("version", GOOGLE_TITLE_RULE_VERSION)
    return _evaluate_frozen_rule(
        target,
        facts,
        **kwargs,
    )
