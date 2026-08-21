import threading
import time

import pytest

from agentready.jobs_v2 import AuditJobManager, JobStatus
from agentready.report_v2 import (
    AuditConfig,
    AuditReport,
    Coverage,
    Finding,
    FindingEvidence,
    FindingStatus,
    classify_finding_changes,
    diff_inventory,
    diff_reports,
    export_inventory,
    paginate_inventory,
    render_audit_report,
    semantic_diff,
)


def _report() -> AuditReport:
    return AuditReport(
        "https://example.com",
        (Finding("robots", "Robots", FindingStatus.PASS, "ok"),),
        Coverage(1, 1, 1, 1),
    )


def test_config_serialization_excludes_secret_material():
    config = AuditConfig("https://example.com", credential_ref="env:GA_TOKEN")
    serialized = config.to_dict()
    assert serialized["credential_ref"] == "env:GA_TOKEN"
    assert "secret_value" not in serialized


def test_report_fingerprint_and_diff_are_stable():
    report = _report()
    payload = report.to_dict()
    assert diff_reports(report, payload).to_dict() == {
        "comparable": True,
        "changed": [],
        "added": [],
        "removed": [],
        "reason": None,
    }


def test_html_report_escapes_target_and_finding_text():
    report = AuditReport(
        "https://example.test/?q=<script>",
        (Finding("<rule>", "Rule", FindingStatus.FAIL, "<script>alert(1)</script>"),),
        Coverage(1, 1, 1, 1),
    )

    rendered = render_audit_report(report, "html")

    assert "&lt;script&gt;" in rendered
    assert "<script>alert(1)</script>" not in rendered


def test_finding_state_hash_ignores_localized_prose():
    first = Finding("rule", "Title EN", FindingStatus.FAIL, "Reason EN", (FindingEvidence("evidence", "EN", "https://example.test"),))
    second = Finding("rule", "Title RU", FindingStatus.FAIL, "Причина", (FindingEvidence("evidence", "RU", "https://example.test"),))
    assert first.state_hash == second.state_hash


def test_report_finding_projects_through_canonical_contract():
    finding = Finding("rule", "Title", FindingStatus.FAIL, "reason", (FindingEvidence("e1", "summary"),))
    contract = finding.to_contract(target="https://example.test/")
    projected = contract.to_report_finding(title=finding.title, reason=finding.reason, public_id=finding.id)
    assert contract.state_hash.value
    assert projected.id == finding.id


def test_classify_finding_changes_uses_state_hash_and_status_direction():
    current = AuditReport(
        "https://example.com",
        (
            Finding("stable", "Localized", FindingStatus.PASS, "different prose"),
            Finding("regress", "Localized", FindingStatus.FAIL, "different prose"),
        ),
        Coverage(2, 2, 2, 2),
    )
    baseline = {
        "schema": "agentready.audit.v2",
        "target": "https://example.com",
        "version": "v2",
        "findings": [
            {"id": "stable", "status": "pass", "state_hash": current.findings[0].state_hash},
            {"id": "regress", "status": "pass", "state_hash": "old-regress"},
        ],
    }
    changes = classify_finding_changes(current, baseline)
    assert changes["regressed"] == ("regress",)


def test_baseline_without_state_hash_uses_fingerprint_compatibility():
    current = _report()
    baseline = {
        "schema": "agentready.audit.v2",
        "target": current.target,
        "version": "v2",
        "findings": [
            {
                "id": "robots",
                "status": "pass",
                "fingerprint": current.findings[0].fingerprint,
            }
        ],
    }

    assert classify_finding_changes(current, baseline)["unchanged"] == ("robots",)
    assert diff_reports(current, baseline).changed == ()


def test_same_status_evidence_change_is_changed_not_resolved():
    current = AuditReport(
        "https://example.com",
        (Finding("robots", "Robots", FindingStatus.WARN, "new evidence"),),
        Coverage(1, 1, 1, 1),
    )
    baseline = {
        "findings": [
            {
                "id": "robots",
                "status": "warn",
                "state_hash": "old-state",
            }
        ]
    }

    changes = classify_finding_changes(current, baseline)

    assert changes["resolved"] == ()
    assert changes["changed"] == ("robots",)


def test_classify_finding_changes_reports_resolved_added_removed_and_unchanged():
    current = AuditReport(
        "https://example.com",
        (
            Finding("resolved", "Resolved", FindingStatus.PASS, "ok"),
            Finding("new", "New", FindingStatus.WARN, "new"),
            Finding("stable", "Stable", FindingStatus.PASS, "same"),
        ),
        Coverage(3, 3, 3, 3),
    )
    baseline = {
        "findings": [
            {"id": "resolved", "status": "fail", "state_hash": "old"},
            {"id": "removed", "status": "warn", "state_hash": "removed"},
            {"id": "stable", "status": "pass", "state_hash": current.findings[2].state_hash},
        ]
    }

    changes = classify_finding_changes(current, baseline)

    assert changes["resolved"] == ("resolved",)
    assert changes["added"] == ("new",)
    assert changes["removed"] == ("removed",)
    assert changes["unchanged"] == ("stable",)


def test_config_precedence_rejects_legacy_adapter():
    config = AuditConfig.from_sources(
        target="https://example.com",
        file_values={"network": {"timeout": 4}, "preset": "content"},
        environment={"AGENTREADY_TIMEOUT": "6"},
        cli_values={"timeout": 7},
    )
    assert config.timeout == 7
    assert config.preset == "content"
    with pytest.raises(ValueError, match="agentready.audit.v2"):
        diff_reports(_report(), {"schema": "agentready.audit.v1", "target": "https://example.com", "findings": []})


def test_inventory_pagination_and_exports():
    items = [{"id": str(index)} for index in range(3)]
    assert paginate_inventory(items, page=2, page_size=2)["items"] == [{"id": "2"}]
    assert export_inventory(items).count("\n") == 3
    assert "id" in export_inventory(items, format="csv")


def test_inventory_diff_classifies_three_changed_rows_in_large_projection():
    baseline = {
        "technical": [
            {"url": f"https://example.test/{index}", "state_hash": f"v1-{index}"}
            for index in range(1000)
        ]
    }
    current = {
        "technical": [
            {"url": f"https://example.test/{index}", "state_hash": f"v2-{index}" if index < 3 else f"v1-{index}"}
            for index in range(1000)
        ]
    }

    diff = diff_inventory(current, baseline)

    assert diff["technical"]["changed"] == tuple(
        f"https://example.test/{index}" for index in range(3)
    )
    assert len(diff["technical"]["unchanged"]) == 997


def test_semantic_diff_categorizes_findings_coverage_inventory_and_rules():
    current = _report().to_dict()
    current["run_id"] = "run-b"
    current["rule_catalog_version"] = "2"
    current["inventory"] = {"pages": [{"url": "https://example.com/a", "state_hash": "new"}]}
    baseline = dict(current)
    baseline["run_id"] = "run-a"
    baseline["rule_catalog_version"] = "1"
    baseline["coverage"] = dict(current["coverage"])
    baseline["coverage"]["urls_fetched"] = 0
    baseline["inventory"] = {"pages": [{"url": "https://example.com/a", "state_hash": "old"}, {"url": "https://example.com/deleted", "state_hash": "old"}]}
    result = semantic_diff(current, baseline)
    assert not result.comparable
    assert result.reason == "rule catalog versions differ"


def test_semantic_diff_ignores_localized_text_and_input_order_but_rejects_incomparable_runs():
    current = AuditReport("https://example.com", (Finding("a", "EN", FindingStatus.PASS, "text"), Finding("b", "B", FindingStatus.WARN, "text")), Coverage(2, 2, 2, 2)).to_dict()
    baseline = dict(current)
    baseline["findings"] = list(reversed(baseline["findings"]))
    baseline["findings"][0] = {**baseline["findings"][0], "title": "RU", "reason": "локализованный текст"}
    assert semantic_diff(current, baseline).findings["unchanged"] == ("a", "b")
    incompatible = {**baseline, "target": "https://other.example"}
    result = semantic_diff(current, incompatible)
    assert not result.comparable
    assert result.reason == "targets differ"


def test_semantic_diff_rejects_same_finding_with_different_rule_version():
    current = AuditReport("https://example.com", (Finding("a", "A", FindingStatus.PASS, "ok", rule_version="2"),), Coverage(1, 1, 1, 1)).to_dict()
    baseline = AuditReport("https://example.com", (Finding("a", "A", FindingStatus.PASS, "ok", rule_version="1"),), Coverage(1, 1, 1, 1)).to_dict()

    result = semantic_diff(current, baseline)

    assert not result.comparable
    assert result.reason == "finding rule versions differ for a"


def test_semantic_diff_rejects_same_digest_with_different_provenance():
    current = AuditReport(
        "https://example.com",
        (Finding("a", "A", FindingStatus.PASS, "ok"),),
        Coverage(1, 1, 1, 1),
        rule_catalog_digest="digest",
        rule_catalog_digest_kind="content",
    ).to_dict()
    baseline = {
        **current,
        "rule_catalog_digest_kind": "synthetic",
    }

    result = semantic_diff(current, baseline)

    assert not result.comparable
    assert result.reason == "rule catalog digest provenance differs"


def test_job_manager_completes_work():
    manager = AuditJobManager(max_jobs=1)
    job_id = manager.submit(lambda: {"ok": True})
    snapshot = manager.get(job_id)
    assert snapshot.status in {JobStatus.RUNNING, JobStatus.COMPLETED}
    while manager.get(job_id).status is JobStatus.RUNNING:
        time.sleep(0.001)
    assert manager.get(job_id).result == {"ok": True}


def test_job_manager_lists_bounded_status_without_result_payload():
    manager = AuditJobManager(max_jobs=1)
    job_id = manager.submit(lambda: {"large": "result"})
    items = manager.list()
    assert items[0]["id"] == job_id
    assert items[0]["status"] in {"running", "completed"}
    assert "result" not in items[0]


def test_job_manager_cancel_removes_task_and_releases_capacity():
    manager = AuditJobManager(max_jobs=1)
    started = threading.Event()
    release = threading.Event()

    def operation(cancel_event):
        started.set()
        while not release.is_set():
            if cancel_event.is_set():
                return None
            time.sleep(0.005)

    job_id = manager.submit(operation)
    assert started.wait(1)
    manager.cancel(job_id)
    assert manager.list() == []
    with pytest.raises(KeyError):
        manager.get(job_id)
    replacement = manager.submit(lambda: None)
    release.set()
    for _ in range(20):
        if manager.get(replacement).status is JobStatus.COMPLETED:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("replacement job did not complete")
