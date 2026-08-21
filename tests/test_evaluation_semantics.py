from agentready.audit_core import (
    Applicability,
    EvaluationCompleteness,
    EvaluationOutcome,
    OperationalState,
)
from agentready.report_v2 import Finding, FindingStatus


def test_public_skip_round_trips_to_not_applicable_without_partial_inference():
    contract = Finding(
        id="optional",
        title="Optional",
        status=FindingStatus.SKIP,
        reason="not applicable",
    ).to_contract(target="https://example.test/")
    assert contract.outcome is EvaluationOutcome.NOT_APPLICABLE
    assert contract.applicability is Applicability.NOT_APPLICABLE
    assert contract.completeness is EvaluationCompleteness.NOT_EVALUATED
    assert contract.operational_state is OperationalState.NONE
    assert contract.to_report_finding(title="Optional", reason="not applicable").status is FindingStatus.SKIP


def test_public_unavailable_round_trips_to_unknown_and_operational_unavailable():
    contract = Finding(
        id="provider",
        title="Provider",
        status=FindingStatus.UNAVAILABLE,
        reason="provider unavailable",
    ).to_contract(target="https://example.test/")
    assert contract.outcome is EvaluationOutcome.UNKNOWN
    assert contract.applicability is Applicability.UNKNOWN
    assert contract.completeness is EvaluationCompleteness.NOT_EVALUATED
    assert contract.operational_state is OperationalState.UNAVAILABLE
    assert contract.to_report_finding(title="Provider", reason="provider unavailable").status is FindingStatus.UNAVAILABLE


def test_public_skip_preserves_unknown_vs_not_applicable_with_canonical_metadata():
    unknown = Finding(
        id="uncertain",
        title="Uncertain",
        status=FindingStatus.SKIP,
        reason="insufficient evidence",
        outcome="unknown",
        applicability="unknown",
        completeness="partial",
        operational_state="none",
    ).to_contract(target="https://example.test/")
    not_applicable = Finding(
        id="optional",
        title="Optional",
        status=FindingStatus.SKIP,
        reason="not applicable",
    ).to_contract(target="https://example.test/")

    assert unknown.outcome is EvaluationOutcome.UNKNOWN
    assert unknown.applicability is Applicability.UNKNOWN
    assert unknown.completeness is EvaluationCompleteness.PARTIAL
    assert unknown.operational_state is OperationalState.NONE
    assert not_applicable.outcome is EvaluationOutcome.NOT_APPLICABLE
