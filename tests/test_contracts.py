from agentready.audit_core import (
    Applicability,
    Effort,
    EvaluationCompleteness,
    EvaluationOutcome,
    EvidenceRef,
    FailurePolicy,
    FindingContract,
    FindingKey,
    FindingStateHash,
    RuleSpec,
    RuleVersion,
    Severity,
    Status,
    UrlIdentity,
    AuthorityLevel,
    RequirementLevel,
    ScoreParticipation,
)
import pytest


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


def test_finding_contract_projects_to_canonical_report_dto():
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


def test_finding_contract_rejects_incomplete_pass_fail_under_failure_policy():
    key = FindingKey("metadata", "1", UrlIdentity.parse("https://example.test/"))
    with pytest.raises(ValueError, match="pass/fail findings require complete evaluation"):
        FindingContract(
            key=key,
            state_hash=FindingStateHash("hash"),
            status=Status.FAIL,
            applicability=Applicability.APPLICABLE,
            completeness=EvaluationCompleteness.PARTIAL,
            severity=Severity.HIGH,
            impact="high",
            effort=Effort.MEDIUM,
            priority=90,
        )

    with pytest.raises(ValueError, match="strict failure policy rejects incomplete pass/fail outcomes"):
        FindingContract(
            key=key,
            state_hash=FindingStateHash("hash"),
            status=Status.WARN,
            applicability=Applicability.APPLICABLE,
            completeness=EvaluationCompleteness.PARTIAL,
            severity=Severity.HIGH,
            impact="high",
            effort=Effort.MEDIUM,
            priority=90,
            outcome=EvaluationOutcome.FAIL,
        )


def test_rule_spec_binds_score_participation_to_score_model_policy():
    rule = RuleSpec(
        "robots",
        "Robots",
        "indexability",
        AuthorityLevel.STANDARD,
        RequirementLevel.REQUIRED,
        RuleVersion("1.0.0", "2026-01-01"),
        ScoreParticipation.INCLUDED,
        score_model_id="readiness-transparent-v2",
        score_policy_version="2026.08",
    )

    assert rule.to_dict()["score_model_id"] == "readiness-transparent-v2"
    assert rule.to_dict()["score_policy_version"] == "2026.08"
    assert rule.to_dict()["failure_policy"] == FailurePolicy.STRICT.value
    with pytest.raises(ValueError, match="score model id"):
        RuleSpec(
            "robots",
            "Robots",
            "indexability",
            AuthorityLevel.STANDARD,
            RequirementLevel.REQUIRED,
            RuleVersion("1.0.0", "2026-01-01"),
            score_model_id="",
        )
