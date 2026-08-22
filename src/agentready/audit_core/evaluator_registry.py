"""Catalog-bound, side-effect-free frozen rule evaluation.

Catalog discovery and runtime authorization are separate concerns: loading a
frozen catalog never makes a rule executable.  Each :class:`EvaluatorRegistry`
is an explicit allowlist of frozen ``(rule_id, version)`` targets; the default
allowlist remains the single E0 canary target, and additional frozen evaluators
(such as the Stage E google-metadata rules) opt in with their own registries
and expected-contract rows.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .contracts import (
    Effort,
    EvaluationCompleteness,
    EvaluationOutcome,
    EvidenceRef,
    FactEnvelope,
    FindingContract,
    FindingKey,
    FindingStateHash,
    FailurePolicy,
    OperationalState,
    Severity,
    Status,
)
from .fact_schema import FactSchemaRegistry
from .models import Applicability
from .urls import UrlIdentity
from ..report_v2 import AuditReport, Coverage

if TYPE_CHECKING:
    from .rule_catalog import RuleCatalogEntry, RuleCatalogSnapshot
    from .rule_projection import EvaluationReadiness, RuleProjection

__all__ = [
    "CORE_COVERAGE_RULE_ID",
    "CORE_COVERAGE_RULE_VERSION",
    "CanaryEvaluation",
    "EvaluatorResult",
    "EvaluatorBinding",
    "EvaluatorRegistry",
    "FrozenRuleBindingError",
    "UnregisteredRuleError",
    "UnresolvedCatalogTargetError",
    "CANARY_EVALUATOR_REGISTRY",
    "bind_frozen_rule",
    "evaluate_frozen_rule",
    "evaluate_core_coverage",
    "build_canary_report",
    "register_expected_contract",
]

CORE_COVERAGE_RULE_ID = "CORE-COVERAGE-001"
CORE_COVERAGE_RULE_VERSION = "1.0.0"
_EXPECTED_SCOPE = "html-page"
_EXPECTED_CONDITION = "applies whenever a html-page subject was collected for the run"
_EXPECTED_SCORE_ROLE = "scored"
_EXPECTED_FAILURE_POLICY = "block_on_missing_facts"
_EXPECTED_MECHANISM = "atomic_check"
_EXPECTED_RULE_KIND = "scored_rule"
_EXPECTED_AUTOMATION = "automated"

# Table-driven expected contracts for allowlisted frozen evaluator targets.
# Each row pins the exact catalog contract a binding must match; the canary
# row preserves the historical E0 behavior exactly.
_EXPECTED_CONTRACTS: dict[tuple[str, str], dict[str, Any]] = {
    (CORE_COVERAGE_RULE_ID, CORE_COVERAGE_RULE_VERSION): {
        "scope": _EXPECTED_SCOPE,
        "condition": _EXPECTED_CONDITION,
        "facts": (("page", "1"), ("robots.policy", "1")),
        "score_role": _EXPECTED_SCORE_ROLE,
        "failure_policy": _EXPECTED_FAILURE_POLICY,
        "mechanism": _EXPECTED_MECHANISM,
        "rule_kind": _EXPECTED_RULE_KIND,
        "automation_mode": _EXPECTED_AUTOMATION,
    },
}


class FrozenRuleBindingError(ValueError):
    """Base error for catalog-to-evaluator binding failures."""


class UnregisteredRuleError(FrozenRuleBindingError):
    """Raised when a catalog rule has no explicit runtime evaluator binding."""


class UnresolvedCatalogTargetError(FrozenRuleBindingError):
    """Raised when a requested rule/version is absent or stale in the catalog."""


@dataclass(frozen=True, slots=True)
class EvaluatorResult:
    outcome: EvaluationOutcome
    reason: str
    evidence: tuple[EvidenceRef, ...] = ()


Evaluator = Callable[[str, Mapping[str, Any]], EvaluatorResult]


@dataclass(frozen=True, slots=True)
class EvaluatorBinding:
    rule_id: str
    version: str
    title: str
    projection: "RuleProjection"
    evaluator: Evaluator


class EvaluatorRegistry:
    """Explicit evaluator allowlist; catalog rows are never auto-registered.

    The allowlist defaults to the E0 canary target.  A registry for another
    frozen rule must declare its exact ``(rule_id, version)`` targets via
    ``allowlist``; registering any other target is rejected.
    """

    def __init__(
        self,
        bindings: Iterable[tuple[str, str, Evaluator]] = (),
        *,
        allowlist: Iterable[tuple[str, str]] = ((CORE_COVERAGE_RULE_ID, CORE_COVERAGE_RULE_VERSION),),
    ) -> None:
        self._allowlist = frozenset(allowlist)
        self._bindings: dict[tuple[str, str], Evaluator] = {}
        for rule_id, version, evaluator in bindings:
            self.register(rule_id, version, evaluator)

    @property
    def registered_targets(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self._bindings))

    def register(self, rule_id: str, version: str, evaluator: Evaluator) -> None:
        target = (rule_id, version)
        if target not in self._allowlist:
            raise UnregisteredRuleError(
                f"frozen evaluator target is not allowlisted: {rule_id}@{version}"
            )
        if target in self._bindings:
            raise FrozenRuleBindingError(f"evaluator already registered: {rule_id}@{version}")
        self._bindings[target] = evaluator

    def resolve(self, rule_id: str, version: str) -> Evaluator:
        try:
            return self._bindings[(rule_id, version)]
        except KeyError as exc:
            raise UnregisteredRuleError(f"no evaluator binding for {rule_id}@{version}") from exc


def _core_coverage_evaluator(target: str, facts: Mapping[str, Any]) -> EvaluatorResult:
    """Evaluate only the declared page and robots.policy fact values."""
    page = facts["page"]
    robots = facts["robots.policy"]
    page_status = _value(page, "status_code")
    content_type = str(_value(page, "content_type") or "").split(";", 1)[0].lower()
    page_crawlable = _value(page, "crawlable")
    if page_crawlable is None:
        page_crawlable = page_status == 200 and content_type in {"text/html", "application/xhtml+xml"}
    robots_allowed = _value(robots, "root_allowed")
    if robots_allowed is None:
        robots_allowed = _value(robots, "allowed")
    if not isinstance(robots_allowed, bool):
        return EvaluatorResult(
            EvaluationOutcome.UNKNOWN,
            "robots.policy fact does not contain an explicit root_allowed decision",
        )
    if bool(page_crawlable) and robots_allowed:
        return EvaluatorResult(
            EvaluationOutcome.PASS,
            f"{target} returned a crawlable HTML response and robots.policy allows the root",
            (
                EvidenceRef("page:crawlable", target, "page fact reports a crawlable HTML response"),
                EvidenceRef("robots.policy:root-allowed", target, "robots.policy allows the audited root"),
            ),
        )
    reasons: list[str] = []
    if not bool(page_crawlable):
        reasons.append("page fact is not a crawlable HTML response")
    if not robots_allowed:
        reasons.append("robots.policy blocks the audited root")
    return EvaluatorResult(EvaluationOutcome.FAIL, "; ".join(reasons))


def _value(fact: Any, key: str) -> Any:
    if isinstance(fact, Mapping):
        return fact.get(key)
    return getattr(fact, key, None)


CANARY_EVALUATOR_REGISTRY = EvaluatorRegistry(
    ((CORE_COVERAGE_RULE_ID, CORE_COVERAGE_RULE_VERSION, _core_coverage_evaluator),)
)


def _validate_canary_contract(entry: "RuleCatalogEntry") -> None:
    """Validate one catalog entry against its allowlisted expected contract.

    Table-driven by ``rule_id``; the canary row preserves the historical E0
    validation behavior exactly.
    """
    expected = _EXPECTED_CONTRACTS.get((entry.rule_id, entry.version))
    if expected is None:
        raise FrozenRuleBindingError(
            f"catalog contract is not the accepted frozen evaluator contract: "
            f"{entry.rule_id}@{entry.version}"
        )
    facts = tuple((item.family, item.min_schema_version) for item in entry.fact_requirements)
    if (
        entry.scope != expected["scope"]
        or entry.condition != expected["condition"]
        or facts != expected["facts"]
        or entry.score_role != expected["score_role"]
        or entry.failure_policy != expected["failure_policy"]
        or entry.mechanism != expected["mechanism"]
        or entry.rule_kind != expected["rule_kind"]
        or entry.automation_mode != expected["automation_mode"]
    ):
        raise FrozenRuleBindingError(
            f"catalog contract is not the accepted frozen evaluator contract: "
            f"{entry.rule_id}@{entry.version}"
        )


def bind_frozen_rule(
    rule_id: str | None = None,
    version: str | None = None,
    *,
    snapshot: "RuleCatalogSnapshot | None" = None,
    registry: EvaluatorRegistry = CANARY_EVALUATOR_REGISTRY,
) -> EvaluatorBinding:
    """Resolve one exact catalog target and one explicit evaluator binding.

    When no explicit target is requested, the single registered target of the
    supplied registry is used; this preserves the historical E0 canary call
    signature exactly while allowing other single-target frozen registries.
    """
    from .rule_catalog import load_rule_catalog_snapshot
    from .rule_projection import project_entry

    if rule_id is None or version is None:
        targets = registry.registered_targets
        if len(targets) != 1:
            raise FrozenRuleBindingError(
                "registry must expose exactly one frozen target to bind implicitly"
            )
        rule_id = rule_id or targets[0][0]
        version = version or targets[0][1]

    snapshot = snapshot or load_rule_catalog_snapshot()
    entry = snapshot.entry(rule_id)
    if entry is None:
        raise UnresolvedCatalogTargetError(f"catalog target is unresolved: {rule_id}@{version}")
    if entry.version != version:
        raise UnresolvedCatalogTargetError(
            f"catalog target version is stale: requested {rule_id}@{version}, found {entry.version}"
        )
    evaluator = registry.resolve(rule_id, version)
    _validate_canary_contract(entry)
    return EvaluatorBinding(rule_id, version, entry.title, project_entry(entry), evaluator)


def register_expected_contract(
    rule_id: str,
    version: str,
    *,
    scope: str = _EXPECTED_SCOPE,
    condition: str = _EXPECTED_CONDITION,
    facts: tuple[tuple[str, str], ...],
    score_role: str = _EXPECTED_SCORE_ROLE,
    failure_policy: str = _EXPECTED_FAILURE_POLICY,
    mechanism: str = _EXPECTED_MECHANISM,
    rule_kind: str = _EXPECTED_RULE_KIND,
    automation_mode: str = _EXPECTED_AUTOMATION,
) -> None:
    """Declare the exact catalog contract accepted for one frozen target."""
    _EXPECTED_CONTRACTS[(rule_id, version)] = {
        "scope": scope,
        "condition": condition,
        "facts": tuple(facts),
        "score_role": score_role,
        "failure_policy": failure_policy,
        "mechanism": mechanism,
        "rule_kind": rule_kind,
        "automation_mode": automation_mode,
    }


def _finding(
    binding: EvaluatorBinding,
    target: str,
    readiness: EvaluationReadiness,
    result: EvaluatorResult | None,
) -> FindingContract:
    key = FindingKey(binding.rule_id, binding.version, UrlIdentity.parse(target))
    failure_policy = FailurePolicy.BLOCK_ON_MISSING_FACTS
    if readiness.applicability is Applicability.NOT_APPLICABLE:
        status = Status.SKIP
        outcome = EvaluationOutcome.NOT_APPLICABLE
        completeness = EvaluationCompleteness.NOT_EVALUATED
        operational_state = OperationalState.NONE
        reason = "rule is not applicable to the collected subject"
        evidence: tuple[EvidenceRef, ...] = ()
    elif not readiness.can_evaluate:
        status = Status.ERROR
        outcome = EvaluationOutcome.UNKNOWN
        completeness = EvaluationCompleteness.PARTIAL
        operational_state = OperationalState.UNAVAILABLE
        reason = "mandatory catalog facts are unavailable or incompatible"
        evidence = tuple(
            EvidenceRef(
                f"fact:{item.family}",
                target,
                f"{item.family}@{item.required}: {item.compatibility.value}",
            )
            for item in readiness.fact_results
            if not item.usable
        )
    else:
        assert result is not None
        outcome = result.outcome
        if outcome is EvaluationOutcome.UNKNOWN:
            status = Status.ERROR
            completeness = EvaluationCompleteness.PARTIAL
            operational_state = OperationalState.UNAVAILABLE
        else:
            status = Status(outcome.value)
            completeness = EvaluationCompleteness.COMPLETE
            operational_state = OperationalState.NONE
        reason = result.reason
        evidence = result.evidence
    state_hash = FindingStateHash.from_state(
        key,
        status=status,
        applicability=readiness.applicability,
        completeness=completeness,
        outcome=outcome,
        operational_state=operational_state,
        evidence_ids=tuple(item.id for item in evidence),
        fact_ids=tuple(item.id for item in evidence if item.id.startswith("fact:")),
    )
    return FindingContract(
        key=key,
        state_hash=state_hash,
        status=status,
        applicability=readiness.applicability,
        completeness=completeness,
        severity=Severity.HIGH if status is Status.FAIL else Severity.INFO,
        impact="crawlability",
        effort=Effort.LOW,
        priority=20 if status is Status.FAIL else 10,
        evidence=evidence,
        outcome=outcome,
        operational_state=operational_state,
        failure_policy=failure_policy,
    )


@dataclass(frozen=True, slots=True)
class CanaryEvaluation:
    binding: EvaluatorBinding
    readiness: EvaluationReadiness
    finding: FindingContract
    report: AuditReport


def evaluate_frozen_rule(
    target: str,
    facts: Iterable[object],
    *,
    rule_id: str = CORE_COVERAGE_RULE_ID,
    version: str = CORE_COVERAGE_RULE_VERSION,
    subject_kind: str = _EXPECTED_SCOPE,
    snapshot: "RuleCatalogSnapshot | None" = None,
    registry: EvaluatorRegistry = CANARY_EVALUATOR_REGISTRY,
    fact_registry: FactSchemaRegistry | None = None,
    run_id: str | None = None,
    score_model_id: str = "readiness-transparent-v2",
    coverage_classification: str | None = None,
    urls_discovered: int | None = None,
    urls_fetched: int | None = None,
    max_pages_hit: bool | None = None,
) -> CanaryEvaluation:
    """Run the E0 path from catalog projection through a canonical report."""
    from .rule_catalog import load_rule_catalog_snapshot
    from .rule_projection import (
        ApplicabilityContext,
        resolve_evaluation_readiness,
    )

    snapshot = snapshot or load_rule_catalog_snapshot()
    binding = bind_frozen_rule(rule_id, version, snapshot=snapshot, registry=registry)
    fact_bundle = _build_fact_bundle(target, facts)
    schema_registry = _build_fact_schema_registry(fact_bundle, fact_registry)
    readiness = resolve_evaluation_readiness(
        binding.projection,
        ApplicabilityContext(subject_kind=subject_kind),
        schema_registry,
    )
    result = None
    if readiness.can_evaluate:
        values = {
            requirement.family: _fact_value(fact_bundle, requirement.family)
            for requirement in binding.projection.fact_requirements
        }
        result = binding.evaluator(target, values)
    finding = _finding(binding, target, readiness, result)
    report_finding = finding.to_report_finding(
        title=binding.title,
        reason=(
            result.reason
            if result is not None
            else "rule is not applicable to the collected subject"
            if readiness.applicability is Applicability.NOT_APPLICABLE
            else "mandatory catalog facts are unavailable or incompatible"
        ),
        url=target,
        public_id=binding.rule_id,
    )
    applicable = int(readiness.applicability is Applicability.APPLICABLE)
    report = AuditReport(
        target,
        (report_finding,),
        Coverage(
            total_rules=1,
            evaluated_rules=applicable,
            applicable_rules=applicable,
            complete_rules=int(finding.completeness is EvaluationCompleteness.COMPLETE),
            urls_discovered=urls_discovered,
            urls_fetched=urls_fetched,
            max_pages_hit=max_pages_hit,
            classification=coverage_classification,
        ),
        run_id=run_id,
        score_model_id=score_model_id,
        rule_catalog_version=snapshot.catalog_version,
        rule_catalog_digest=snapshot.rule_catalog_digest,
        rule_catalog_digest_kind="content",
    )
    return CanaryEvaluation(binding, readiness, finding, report)


def _build_fact_bundle(target: str, facts: Iterable[object]) -> tuple[FactEnvelope, ...]:
    """Return a deterministic bundle of facts scoped to one requested URL."""
    target_identity = UrlIdentity.parse(target)
    scoped = [
        envelope
        for envelope in facts
        if isinstance(envelope, FactEnvelope)
        and envelope.target.normalized() == target_identity.normalized()
    ]
    return tuple(sorted(scoped, key=_fact_sort_key))


def _fact_sort_key(envelope: FactEnvelope) -> tuple[str, ...]:
    return (
        envelope.schema_family or envelope.kind,
        envelope.schema_version or "",
        envelope.kind,
        envelope.id,
        envelope.observed_at,
        envelope.representation_id or "",
        json.dumps(envelope.value, sort_keys=True, separators=(",", ":"), default=str),
    )


def _build_fact_schema_registry(
    fact_bundle: tuple[FactEnvelope, ...],
    override: FactSchemaRegistry | None,
) -> FactSchemaRegistry:
    """Bundle-observed versions stay authoritative; overrides never upgrade them.

    The caller-supplied registry may only contribute additional ``incompatible``
    metadata for families actually present in the subject-scoped bundle.  It can
    never raise or mask the schema version observed on a real envelope, so an
    old/unknown mandatory fact cannot be promoted past the fail-closed gate.
    """
    bundle_registry = FactSchemaRegistry.from_envelopes(fact_bundle)
    if override is None:
        return bundle_registry
    incompatible = frozenset(
        item for item in override.incompatible if item[0] in bundle_registry.versions
    )
    return FactSchemaRegistry(dict(bundle_registry.versions), incompatible=incompatible)


def _fact_value(envelopes: tuple[FactEnvelope, ...], family: str) -> Any:
    for envelope in envelopes:
        if getattr(envelope, "schema_family", None) == family:
            return getattr(envelope, "value", None)
    raise KeyError(f"required fact value is missing: {family}")


def evaluate_core_coverage(
    target: str,
    facts: Iterable[object],
    **kwargs: Any,
) -> CanaryEvaluation:
    """Named E0 convenience entry point; no legacy check is replaced."""
    return evaluate_frozen_rule(target, facts, **kwargs)


def build_canary_report(target: str, facts: Iterable[object], **kwargs: Any) -> AuditReport:
    """Return only the canonical report projection for callers that need it."""
    return evaluate_frozen_rule(target, facts, **kwargs).report
