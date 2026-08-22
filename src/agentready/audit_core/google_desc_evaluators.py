"""Frozen-rule evaluator binding for GOOGLE-DESC-001@1.0.0.

This module follows the E0 canary pattern of ``evaluator_registry.py``: it is
catalog-bound, side-effect-free, and performs no HTTP/browser/provider/parsing
or sqlite I/O.  The evaluator is a pure function over pre-collected facts.

Chosen recommended-length band (explicit, deterministic)
--------------------------------------------------------
The catalog title says "within recommended length".  Google's documented
Search Central guidance describes good meta descriptions as roughly 120-160
characters (Google does not publish a hard limit; the guidance is that a
description should be long enough to be informative yet short enough not to
be truncated in SERP display).  This binding encodes exactly one explicit,
deterministic band derived from that documented recommendation:

    MIN_DESCRIPTION_LENGTH = 120   # inclusive lower bound
    MAX_DESCRIPTION_LENGTH = 160   # inclusive upper bound

Lengths are measured on the whitespace-collapsed description text.  The band
is not imported from any legacy fixed threshold; it is stated here so callers
and reviewers can audit the decision boundary.

Fact payload shapes (declared by the frozen catalog contract)
-------------------------------------------------------------
page@1 -> mapping with keys:
    "titles": list[str]
    "descriptions": list[str]
    "status_code": int
    "content_type": str

structured-data@1 -> mapping with keys:
    "jsonld_nodes": list[dict]
    "jsonld_errors": list[str]
    "block_count": int

``structured-data@1`` is a declared mandatory fact: its presence and schema
version are gated by evaluation readiness (fail-closed via
``FailurePolicy.BLOCK_ON_MISSING_FACTS``).  The description decision itself
comes only from the page fact; JSON-LD content is never used as evidence.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from .contracts import EvidenceRef
from .evaluator_registry import (
    EvaluatorRegistry,
    EvaluatorResult,
    ExpectedRuleContract,
    register_expected_contract,
    evaluate_frozen_rule,
)
from .models import EvaluationOutcome

if TYPE_CHECKING:
    from .evaluator_registry import CanaryEvaluation

__all__ = [
    "GOOGLE_DESC_RULE_ID",
    "GOOGLE_DESC_RULE_VERSION",
    "MIN_DESCRIPTION_LENGTH",
    "MAX_DESCRIPTION_LENGTH",
    "GOOGLE_DESC_EVALUATOR_REGISTRY",
    "_google_desc_evaluator",
    "evaluate_google_desc",
]

GOOGLE_DESC_RULE_ID = "GOOGLE-DESC-001"
GOOGLE_DESC_RULE_VERSION = "1.0.0"

# Explicit documented band derived from Google Search Central's ~120-160 char
# meta-description guidance.  Both bounds are inclusive; see module docstring.
from .rule_catalog import load_rule_semantics

_DESC_CONDITION = load_rule_semantics().condition("GOOGLE-DESC-001")
assert _DESC_CONDITION is not None and _DESC_CONDITION.length_band is not None
MIN_DESCRIPTION_LENGTH = _DESC_CONDITION.length_band.min
MAX_DESCRIPTION_LENGTH = _DESC_CONDITION.length_band.max


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def _google_desc_evaluator(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """Evaluate exactly one non-empty description within the documented band.

    PASS iff the page fact reports exactly one meta description whose
    whitespace-collapsed length lies within ``[120, 160]``.  Otherwise FAIL
    with a deterministic reason naming every observed condition.
    """
    page = facts["page"]
    descriptions_raw = page.get("descriptions") if isinstance(page, Mapping) else None
    descriptions = [
        _collapse_whitespace(item) for item in (descriptions_raw or []) if isinstance(item, str)
    ]
    non_empty = [item for item in descriptions if item]

    reasons: list[str] = []
    if not descriptions:
        reasons.append("meta description is missing")
        outcome = EvaluationOutcome.FAIL
    elif len(non_empty) != len(descriptions):
        reasons.append("meta description is empty")
        outcome = EvaluationOutcome.FAIL
    elif len(non_empty) > 1:
        reasons.append(f"multiple meta descriptions found ({len(non_empty)})")
        outcome = EvaluationOutcome.FAIL
    else:
        length = len(non_empty[0])
        if length < MIN_DESCRIPTION_LENGTH:
            reasons.append(
                f"meta description is too short ({length} chars, minimum "
                f"{MIN_DESCRIPTION_LENGTH}): {non_empty[0]!r}"
            )
            outcome = EvaluationOutcome.FAIL
        elif length > MAX_DESCRIPTION_LENGTH:
            reasons.append(
                f"meta description is too long ({length} chars, maximum "
                f"{MAX_DESCRIPTION_LENGTH}): {non_empty[0]!r}"
            )
            outcome = EvaluationOutcome.FAIL
        else:
            outcome = EvaluationOutcome.PASS
            reasons.append(
                f"exactly one meta description within the recommended "
                f"{MIN_DESCRIPTION_LENGTH}-{MAX_DESCRIPTION_LENGTH} char band"
            )

    if outcome is EvaluationOutcome.PASS:
        return EvaluatorResult(
            outcome,
            f"{target}: {reasons[0]}",
            (
                EvidenceRef(
                    "page:meta-description",
                    target,
                    "page fact reports exactly one meta description within the recommended band",
                ),
            ),
        )
    return EvaluatorResult(outcome, "; ".join(reasons))


_GOOGLE_DESC_CONTRACT = ExpectedRuleContract(
    rule_id=GOOGLE_DESC_RULE_ID,
    version=GOOGLE_DESC_RULE_VERSION,
    scope="html-page",
    condition="applies whenever a html-page subject was collected for the run",
    facts=(("page", "1"),),
    score_role="scored",
    failure_policy="block_on_missing_facts",
    mechanism="atomic_check",
    rule_kind="scored_rule",
    automation_mode="automated",
)

register_expected_contract(_GOOGLE_DESC_CONTRACT)

GOOGLE_DESC_EVALUATOR_REGISTRY = EvaluatorRegistry(
    ((GOOGLE_DESC_RULE_ID, GOOGLE_DESC_RULE_VERSION, _google_desc_evaluator),),
    allowlist=((GOOGLE_DESC_RULE_ID, GOOGLE_DESC_RULE_VERSION),),
)


def evaluate_google_desc(
    target: str,
    facts: Iterable[object],
    **kwargs: Any,
) -> "CanaryEvaluation":
    """Named E8 entry point reusing the shared frozen-rule evaluation path.

    ``rule_id``/``rule_version`` are always passed explicitly; the registry
    defaults to the frozen GOOGLE-DESC registry but may be overridden by
    callers (e.g. applicability spy registries in tests).
    """
    kwargs.setdefault("registry", GOOGLE_DESC_EVALUATOR_REGISTRY)
    return evaluate_frozen_rule(
        target,
        facts,
        rule_id=GOOGLE_DESC_RULE_ID,
        rule_version=GOOGLE_DESC_RULE_VERSION,
        **kwargs,
    )
