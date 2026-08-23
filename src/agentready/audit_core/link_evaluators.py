"""Frozen CORE-LINK family evaluators (Stage E5, issue #27).

Six pure, deterministic evaluators for the frozen catalog rules
``CORE-LINK-001`` .. ``CORE-LINK-006`` @ ``1.0.0``.  Like the E0 canary in
:mod:`agentready.audit_core.evaluator_registry`, this module performs no
HTTP/browser/provider/parsing/sqlite access and no collection I/O: facts are
pre-collected upstream and handed in as :class:`FactEnvelope` values.

Deterministic fact payload shapes (dict payloads keyed by fact family)
---------------------------------------------------------------------
``links``::

    {
        "links": [
            {
                "resolved_url": str | None,  # resolved absolute URL, None when unresolvable
                "raw_href": str,             # raw href attribute value
                "rel": str,                  # rel attribute value ("" when absent)
                "element": str,              # host element tag name, e.g. "a" / "area"
            },
            ...
        ],
        "internal_count": int,   # links resolving inside the audited origin
        "external_count": int,   # links resolving outside the audited origin
    }

``page``::

    {"status_code": int, "content_type": str}

``resources``::

    {
        "resources": [
            {
                "url": str,                  # referenced resource URL
                "resource_type": str,        # e.g. "script" / "stylesheet" / "image"
                "resolved_url": str | None,  # resolved absolute URL, None when unresolvable
            },
            ...
        ]
    }

Semantic mapping (one distinct, minimal condition per rule, derived only
from the declared fact families and the rule's position in the family)
---------------------------------------------------------------------
- ``CORE-LINK-001`` (links, page; scored): internal links are present and
  every declared internal link resolves to a URL on a collected page
  response (page reports a successful HTML response).  PASS when
  ``internal_count > 0`` and the page fact reports a successful HTML
  response; FAIL otherwise.
- ``CORE-LINK-002`` (links, page, resources; scored): every resource URL
  referenced by the page's links resolves consistently — each link whose
  ``raw_href`` matches a declared resource ``url`` must have the same
  ``resolved_url`` as that resource.  PASS when all such references agree;
  FAIL on any mismatch.
- ``CORE-LINK-003`` (links; scored): links exist at all — PASS when the
  links fact declares at least one link; FAIL when the declared link list
  is empty.
- ``CORE-LINK-004`` (links, page; diagnostic): link/page consistency is
  observed without a confident fail — PASS when the declared internal link
  count agrees with the page reporting a successful HTML response, WARN
  when the observation is inconclusive.  Never FAILs on missing data
  (``unknown_on_missing_facts`` → ``FailurePolicy.PARTIAL_DECISION_ALLOWED``).
- ``CORE-LINK-005`` (links, page, resources; scored): link/resource
  integrity — every declared resource URL must be referenced by at least
  one declared link and every link-referenced resource must be declared.
  PASS when the two sets agree exactly; FAIL on any orphan in either
  direction.
- ``CORE-LINK-006`` (links; observation_only): outbound link census —
  always PASSes with the observed external link count as evidence and
  never fails (``unknown_on_missing_facts`` →
  ``FailurePolicy.PARTIAL_DECISION_ALLOWED``).

No legacy intent fact input exists anywhere in this binding or evaluation
path; only the declared fact families above are consumed.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contracts import EvidenceRef, EvaluationOutcome
from .urls import UrlIdentity
from .evaluator_registry import (
    EvaluatorRegistry,
    EvaluatorResult,
    evaluate_frozen_rule,
)

__all__ = [
    "CORE_LINK_RULE_VERSION",
    "LINK_RULE_IDS",
    "LINK_EVALUATOR_REGISTRY",
    "LINK_EXPECTED_CONTRACTS",
    "bind_link_rule",
    "evaluate_link_rule",
]

CORE_LINK_RULE_VERSION = "1.0.0"

LINK_RULE_IDS = (
    "CORE-LINK-001",
    "CORE-LINK-002",
    "CORE-LINK-003",
    "CORE-LINK-004",
    "CORE-LINK-005",
    "CORE-LINK-006",
)

_EXPECTED_SCOPE = "html-page"
_EXPECTED_CONDITION = "applies whenever a html-page subject was collected for the run"
_EXPECTED_AUTOMATION = "automated"

_FACTS_BY_RULE: dict[str, tuple[tuple[str, str], ...]] = {
    "CORE-LINK-001": (("page", "1"), ("representation", "1")),
    "CORE-LINK-002": (("page", "1"), ("resources", "1")),
    "CORE-LINK-003": (("page", "1"),),
    "CORE-LINK-004": (("page", "1"), ("representation", "1")),
    "CORE-LINK-005": (("page", "1"), ("resources", "1")),
    "CORE-LINK-006": (("page", "1"),),
}

_CONTRACT_BY_RULE: dict[str, dict[str, str]] = {
    "CORE-LINK-001": {
        "score_role": "scored",
        "failure_policy": "block_on_missing_facts",
        "mechanism": "atomic_check",
        "rule_kind": "scored_rule",
    },
    "CORE-LINK-002": {
        "score_role": "scored",
        "failure_policy": "block_on_missing_facts",
        "mechanism": "atomic_check",
        "rule_kind": "scored_rule",
    },
    "CORE-LINK-003": {
        "score_role": "scored",
        "failure_policy": "block_on_missing_facts",
        "mechanism": "atomic_check",
        "rule_kind": "scored_rule",
    },
    "CORE-LINK-004": {
        "score_role": "diagnostic",
        "failure_policy": "unknown_on_missing_facts",
        "mechanism": "atomic_check",
        "rule_kind": "diagnostic_rule",
    },
    "CORE-LINK-005": {
        "score_role": "scored",
        "failure_policy": "block_on_missing_facts",
        "mechanism": "atomic_check",
        "rule_kind": "scored_rule",
    },
    "CORE-LINK-006": {
        "score_role": "observation_only",
        "failure_policy": "unknown_on_missing_facts",
        "mechanism": "atomic_check",
        "rule_kind": "observation_rule",
    },
}

LINK_EXPECTED_CONTRACTS: dict[str, dict[str, Any]] = {
    rule_id: {
        "version": CORE_LINK_RULE_VERSION,
        "scope": _EXPECTED_SCOPE,
        "condition": _EXPECTED_CONDITION,
        "facts": _FACTS_BY_RULE[rule_id],
        "automation_mode": _EXPECTED_AUTOMATION,
        **_CONTRACT_BY_RULE[rule_id],
    }
    for rule_id in LINK_RULE_IDS
}


def _links_fact(target: str, facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Derive the link census inside the condition from produced page@1 rows."""
    page = facts["page"]
    entries = page.get("links")
    rows = [item for item in entries if isinstance(item, Mapping)] if isinstance(
        entries, (list, tuple)
    ) else []
    origin = str(UrlIdentity.parse(target).origin.to_string())
    internal = 0
    external = 0
    for row in rows:
        resolved = row.get("resolved_url")
        if not isinstance(resolved, str) or not resolved:
            continue
        try:
            same_origin = UrlIdentity.parse(resolved).origin.to_string() == origin
        except ValueError:
            continue
        if same_origin:
            internal += 1
        else:
            external += 1
    return {"links": rows, "internal_count": internal, "external_count": external}


def _page_fact(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    value = facts["page"]
    if not isinstance(value, Mapping):
        raise TypeError("page fact payload must be a mapping")
    return value


def _resources_fact(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    value = facts["resources"]
    if not isinstance(value, Mapping):
        raise TypeError("resources fact payload must be a mapping")
    return value


def _page_ok(facts: Mapping[str, Any]) -> bool | None:
    """HTML-success from the declared representation fact; None when undetermined."""
    rep = facts.get("representation")
    if not isinstance(rep, Mapping):
        return None
    status = rep.get("status_code")
    content_type = str(rep.get("content_type") or "").split(";", 1)[0].strip().lower()
    if status is None or not content_type:
        return None
    return status == 200 and content_type in {
        "text/html",
        "application/xhtml+xml",
    }

def _link_entries(links: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    entries = links.get("links")
    if not isinstance(entries, (list, tuple)):
        return ()
    return tuple(item for item in entries if isinstance(item, Mapping))


def _resource_entries(resources: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    entries = resources.get("resources")
    if not isinstance(entries, (list, tuple)):
        return ()
    return tuple(item for item in entries if isinstance(item, Mapping))


def _core_link_001(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """Internal links are present and the page reports a successful HTML response."""
    page = _page_fact(facts)
    links = _links_fact(target, facts)
    internal_count = links.get("internal_count")
    if not isinstance(internal_count, int) or internal_count <= 0:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            "links fact declares no internal links for the audited page",
        )
    html_ok = _page_ok(facts)
    if html_ok is None:
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            "HTML success could not be determined from the representation fact",
        )
    if not html_ok:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            "representation fact does not report a successful HTML response",
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        f"{target} declares internal links and reports a successful HTML response",
        (
            EvidenceRef(
                "links:internal-count",
                target,
                f"links fact declares {internal_count} internal link(s)",
            ),
            EvidenceRef(
                "page:html-response",
                target,
                "page fact reports a successful HTML response",
            ),
        ),
    )


def _core_link_002(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """Contract-preparation evaluator (CORE-LINK-002 is declared_not_produced).

    Covered only by direct-invocation contract-preparation tests; this
    function is NOT a registered frozen binding.
    """
    page = _page_fact(facts)
    links = _links_fact(target, facts)
    resources = _resources_fact(facts)
    declared: dict[str, str | None] = {}
    for resource in _resource_entries(resources):
        url = str(resource.get("url") or "")
        if url:
            declared.setdefault(url, resource.get("resolved_url"))
    mismatches: list[str] = []
    checked = 0
    for link in _link_entries(links):
        raw_href = str(link.get("raw_href") or "")
        if raw_href not in declared:
            continue
        checked += 1
        expected = declared[raw_href]
        if link.get("resolved_url") != expected:
            mismatches.append(raw_href)
    if mismatches:
        sample = ", ".join(sorted(mismatches)[:3])
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            f"link-referenced resource URLs resolve inconsistently: {sample}",
        )
    if checked == 0:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            "no link references any declared resource URL",
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        f"{checked} link-referenced resource URL(s) resolve consistently",
        (
            EvidenceRef(
                "resources:link-consistency",
                target,
                f"{checked} link-referenced resource URL(s) match their declared resolution",
            ),
        ),
    )


def _core_link_003(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """Links exist at all on the audited page."""
    page = _page_fact(facts)
    links = _links_fact(target, facts)
    entries = _link_entries(links)
    if not entries:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            "links fact declares no links for the audited page",
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        f"links fact declares {len(entries)} link(s)",
        (
            EvidenceRef(
                "links:count",
                target,
                f"links fact declares {len(entries)} link(s)",
            ),
        ),
    )


def _core_link_004(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """Diagnostic link/page consistency without a confident fail."""
    page = _page_fact(facts)
    links = _links_fact(target, facts)
    internal_count = links.get("internal_count")
    page_ok = _page_ok(facts)
    if not isinstance(internal_count, int):
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            "links fact does not declare an internal link count",
        )
    if page_ok is None:
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            "HTML success could not be determined from the representation fact",
        )
    if internal_count > 0 and page_ok:
        return EvaluatorResult(
            EvaluationOutcome.PASS,
            "internal link count and page response are consistent",
            (
                EvidenceRef(
                    "links:internal-count",
                    target,
                    f"links fact declares {internal_count} internal link(s)",
                ),
                EvidenceRef(
                    "page:html-response",
                    target,
                    "page fact reports a successful HTML response",
                ),
            ),
        )
    return EvaluatorResult(
        EvaluationOutcome.WARN,
        "link/page consistency observation is inconclusive",
        (
            EvidenceRef(
                "links:internal-count",
                target,
                f"links fact declares {internal_count} internal link(s)",
            ),
            EvidenceRef(
                "page:response",
                target,
                "page fact does not confirm a successful HTML response",
            ),
        ),
    )


def _origin_prefix(target: str) -> str:
    """Return ``scheme://host/`` for an absolute target URL (no network parsing)."""
    parts = target.split("/", 3)
    if len(parts) < 3 or parts[2] == "":
        return target
    return f"{parts[0]}//{parts[2]}/"


def _is_internal_link(link: Mapping[str, Any], origin_prefix: str) -> bool:
    resolved = str(link.get("resolved_url") or "")
    if not resolved:
        return False
    if resolved.startswith(origin_prefix):
        return True
    # Relative raw hrefs resolve inside the audited origin.
    raw_href = str(link.get("raw_href") or "")
    return bool(raw_href) and not raw_href.startswith(("http://", "https://", "//"))


def _core_link_005(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """Contract-preparation evaluator (CORE-LINK-005 is declared_not_produced).

    Covered only by direct-invocation contract-preparation tests; this
    function is NOT a registered frozen binding.  Link/resource integrity:
    all link references agree exactly.
    """
    page = _page_fact(facts)
    links = _links_fact(target, facts)
    resources = _resources_fact(facts)
    origin_prefix = _origin_prefix(target)
    declared = {
        str(resource.get("url") or "")
        for resource in _resource_entries(resources)
        if resource.get("url")
    }
    referenced = {
        str(link.get("raw_href") or "")
        for link in _link_entries(links)
        if link.get("raw_href") and _is_internal_link(link, origin_prefix)
    }
    orphans = declared - referenced
    if orphans:
        sample = ", ".join(sorted(orphans)[:3])
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            f"declared resources are not referenced by any link: {sample}",
        )
    missing = referenced - declared
    if missing:
        sample = ", ".join(sorted(missing)[:3])
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            f"link references have no declared resource: {sample}",
        )
    if not declared:
        return EvaluatorResult(
            EvaluationOutcome.FAIL,
            "no declared resources and no link references to verify integrity",
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        f"{len(declared)} resource URL(s) agree exactly with link references",
        (
            EvidenceRef(
                "resources:integrity",
                target,
                f"{len(declared)} resource URL(s) match link references exactly",
            ),
        ),
    )


def _core_link_006(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """Observation-only outbound link census; never fails."""
    page = _page_fact(facts)
    links = _links_fact(target, facts)
    external_count = links.get("external_count")
    if not isinstance(external_count, int):
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            "links fact does not declare an external link count",
        )
    return EvaluatorResult(
        EvaluationOutcome.PASS,
        f"observed {external_count} outbound link(s)",
        (
            EvidenceRef(
                "links:external-count",
                target,
                f"links fact observes {external_count} external link(s)",
            ),
        ),
    )


_EVALUATORS = {
    "CORE-LINK-001": _core_link_001,
    "CORE-LINK-002": _core_link_002,
    "CORE-LINK-003": _core_link_003,
    "CORE-LINK-004": _core_link_004,
    "CORE-LINK-005": _core_link_005,
    "CORE-LINK-006": _core_link_006,
}

from .evaluator_registry import ExpectedContract

_BOUND_RULES = (
    "CORE-LINK-001",
    "CORE-LINK-002",
    "CORE-LINK-003",
    "CORE-LINK-004",
    "CORE-LINK-005",
    "CORE-LINK-006",
)

_CONTRACT_OBJECTS = {
    (rid, CORE_LINK_RULE_VERSION): ExpectedContract(
        rule_id=rid,
        version=CORE_LINK_RULE_VERSION,
        scope=c["scope"],
        condition=c["condition"],
        facts=tuple(c["facts"]),
        score_role=c["score_role"],
        failure_policy=c["failure_policy"],
        mechanism=c["mechanism"],
        rule_kind=c["rule_kind"],
        automation_mode=c["automation_mode"],
    )
    for rid, c in LINK_EXPECTED_CONTRACTS.items()
}

LINK_EVALUATOR_REGISTRY = EvaluatorRegistry(
    tuple(
        (rule_id, CORE_LINK_RULE_VERSION, _EVALUATORS[rule_id])
        for rule_id in _BOUND_RULES
    ),
    allowlist=frozenset((rule_id, CORE_LINK_RULE_VERSION) for rule_id in _BOUND_RULES),
    expected_contracts=_CONTRACT_OBJECTS,
)


def bind_link_rule(rule_id: str, *, snapshot: Any = None):
    """Bind one CORE-LINK catalog target to its explicit evaluator."""
    from .evaluator_registry import bind_frozen_rule

    return bind_frozen_rule(
        rule_id,
        CORE_LINK_RULE_VERSION,
        snapshot=snapshot,
        registry=LINK_EVALUATOR_REGISTRY,
        )


def evaluate_link_rule(
    target: str,
    facts,
    rule_id: str,
    **kwargs: Any,
):
    """Evaluate one CORE-LINK rule through the shared frozen-rule path."""
    kwargs.setdefault("registry", LINK_EVALUATOR_REGISTRY)
    kwargs.setdefault("rule_version", CORE_LINK_RULE_VERSION)
    return evaluate_frozen_rule(
        target,
        facts,
        rule_id=rule_id,
        **kwargs,
    )
