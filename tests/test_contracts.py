from agentready.audit_core import (
    Applicability,
    EvaluationCompleteness,
    EvidenceRef,
    Effort,
    FindingContract,
    FindingKey,
    FindingStateHash,
    Severity,
    Status,
    UrlIdentity,
)


def test_finding_state_hash_ignores_localized_prose():
    key = FindingKey("robots", "1.0.0", UrlIdentity.parse("https://example.test"))
    english = FindingStateHash.from_state(
        key,
        status=Status.FAIL,
        applicability=Applicability.APPLICABLE,
        completeness=EvaluationCompleteness.COMPLETE,
        evidence_ids=("evidence-1",),
    )
    russian = FindingStateHash.from_state(
        key,
        status=Status.FAIL,
        applicability=Applicability.APPLICABLE,
        completeness=EvaluationCompleteness.COMPLETE,
        evidence_ids=("evidence-1",),
    )
    assert english == russian
    assert english.value


def test_finding_contract_projects_to_legacy_report_dto():
    contract = FindingContract(
        key=FindingKey("metadata", "1", UrlIdentity.parse("https://example.test/")),
        state_hash=FindingStateHash("hash"),
        status=Status.ERROR,
        applicability=Applicability.APPLICABLE,
        completeness=EvaluationCompleteness.PARTIAL,
        severity=Severity.HIGH,
        impact="high",
        effort=Effort.MEDIUM,
        priority=90,
        evidence=(EvidenceRef("e1", "title", "missing title"),),
    )

    report = contract.to_report_finding(title="Metadata", reason="Unavailable")
    assert report.id == "metadata@1:https://example.test/"
    assert report.status.value == "unavailable"
    assert report.evidence[0].id == "e1"
