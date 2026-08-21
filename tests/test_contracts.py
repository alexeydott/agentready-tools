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
    ScoreRole,
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


def test_finding_contract_allows_explicit_partial_decision_policy():
    key = FindingKey("metadata", "1", UrlIdentity.parse("https://example.test/"))
    contract = FindingContract(
        key=key,
        state_hash=FindingStateHash("hash"),
        status=Status.FAIL,
        applicability=Applicability.APPLICABLE,
        completeness=EvaluationCompleteness.PARTIAL,
        severity=Severity.HIGH,
        impact="high",
        effort=Effort.MEDIUM,
        priority=90,
        failure_policy=FailurePolicy.PARTIAL_DECISION_ALLOWED,
    )

    assert contract.outcome is EvaluationOutcome.FAIL
    assert contract.failure_policy is FailurePolicy.PARTIAL_DECISION_ALLOWED
    assert contract.to_report_finding(title="Metadata", reason="partial but decisive").status.value == "fail"


def test_finding_contract_allows_evidence_unknown_without_operational_failure():
    key = FindingKey("metadata", "1", UrlIdentity.parse("https://example.test/"))
    contract = FindingContract(
        key=key,
        state_hash=FindingStateHash("hash"),
        status=Status.WARN,
        applicability=Applicability.UNKNOWN,
        completeness=EvaluationCompleteness.PARTIAL,
        severity=Severity.MEDIUM,
        impact="medium",
        effort=Effort.MEDIUM,
        priority=50,
        outcome=EvaluationOutcome.UNKNOWN,
    )

    assert contract.outcome is EvaluationOutcome.UNKNOWN
    assert contract.operational_state.value == "none"
    report = contract.to_report_finding(title="Metadata", reason="insufficient evidence")
    assert report.status.value == "skip"
    assert report.to_contract(target="https://example.test/").outcome is EvaluationOutcome.UNKNOWN


def test_rule_spec_exposes_score_role_without_score_model_policy():
    rule = RuleSpec(
        "robots",
        "Robots",
        "indexability",
        AuthorityLevel.STANDARD,
        RequirementLevel.REQUIRED,
        RuleVersion("1.0.0", "2026-01-01"),
        ScoreParticipation.INCLUDED,
    )

    assert rule.to_dict()["score_role"] == ScoreRole.ELIGIBLE.value
    assert "score_model_id" not in rule.to_dict()
    assert "score_policy_version" not in rule.to_dict()
    assert rule.to_dict()["failure_policy"] == FailurePolicy.STRICT.value
    observation = RuleSpec(
        "observed",
        "Observed",
        "metadata",
        AuthorityLevel.STANDARD,
        RequirementLevel.SUPPLEMENTAL,
        RuleVersion("1.0.0", "2026-01-01"),
        ScoreParticipation.EXCLUDED,
        score_role=ScoreRole.OBSERVATION,
    )
    guard = RuleSpec(
        "guard",
        "Guard",
        "metadata",
        AuthorityLevel.STANDARD,
        RequirementLevel.RECOMMENDED,
        RuleVersion("1.0.0", "2026-01-01"),
        ScoreParticipation.EXCLUDED,
        score_role=ScoreRole.GUARD,
    )
    legacy = RuleSpec(
        "legacy",
        "Legacy",
        "metadata",
        AuthorityLevel.STANDARD,
        RequirementLevel.SUPPLEMENTAL,
        RuleVersion("1.0.0", "2026-01-01"),
        ScoreParticipation.EXCLUDED,
        score_role=ScoreRole.LEGACY_ONLY,
    )
    assert {observation.score_role, guard.score_role, legacy.score_role} == {
        ScoreRole.OBSERVATION,
        ScoreRole.GUARD,
        ScoreRole.LEGACY_ONLY,
    }
    with pytest.raises(ValueError, match="only score-eligible"):
        RuleSpec(
            "robots",
            "Robots",
            "indexability",
            AuthorityLevel.STANDARD,
            RequirementLevel.REQUIRED,
            RuleVersion("1.0.0", "2026-01-01"),
            ScoreParticipation.INCLUDED,
            score_role=ScoreRole.OBSERVATION,
        )
