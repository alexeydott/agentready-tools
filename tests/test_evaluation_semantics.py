import json

from agentready.audit_core import (
    Applicability,
    EvaluationCompleteness,
    EvaluationOutcome,
    OperationalState,
)
from agentready.report_v2 import AuditReport, Coverage, Finding, FindingStatus, report_from_dict


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


def test_unknown_public_json_round_trip_remains_distinct_from_not_applicable():
    payload = AuditReport(
        "https://example.test",
        (
            Finding(
                id="uncertain",
                title="Uncertain",
                status=FindingStatus.SKIP,
                reason="insufficient evidence",
                outcome="unknown",
                applicability="unknown",
                completeness="partial",
                operational_state="none",
            ),
            Finding(
                id="optional",
                title="Optional",
                status=FindingStatus.SKIP,
                reason="not applicable",
            ),
        ),
        Coverage(2, 2, 0, 0),
    ).to_dict()
    restored = report_from_dict(json.loads(json.dumps(payload)))

    unknown = restored.findings[0].to_contract(target=restored.target)
    not_applicable = restored.findings[1].to_contract(target=restored.target)

    assert unknown.outcome is EvaluationOutcome.UNKNOWN
    assert unknown.applicability is Applicability.UNKNOWN
    assert unknown.completeness is EvaluationCompleteness.PARTIAL
    assert not_applicable.outcome is EvaluationOutcome.NOT_APPLICABLE
    assert not_applicable.applicability is Applicability.NOT_APPLICABLE
