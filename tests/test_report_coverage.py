from types import SimpleNamespace

from agentready.report_v2 import FindingStatus, report_from_checks


def test_failed_but_fully_evaluated_checks_count_as_complete():
    report = report_from_checks(
        "https://example.test/",
        (
            SimpleNamespace(id="rule-fail", title="Fail", status="fail", details="evidence", evidence=()),
            SimpleNamespace(id="rule-skip", title="Skip", status="skip", details="optional", evidence=()),
        ),
    )
    assert report.findings[0].status is FindingStatus.FAIL
    assert report.coverage.applicable_rules == 1
    assert report.coverage.complete_rules == 1
