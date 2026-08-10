import time

from agentready.jobs_v2 import AuditJobManager, JobStatus
from agentready.report_v2 import (
    AuditConfig,
    AuditReport,
    Coverage,
    Finding,
    FindingStatus,
    diff_reports,
    export_inventory,
    adapt_legacy_baseline,
    paginate_inventory,
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


def test_config_precedence_and_legacy_adapter():
    config = AuditConfig.from_sources(
        target="https://example.com",
        file_values={"network": {"timeout": 4}, "preset": "content"},
        environment={"AGENTREADY_TIMEOUT": "6"},
        cli_values={"timeout": 7},
    )
    assert config.timeout == 7
    assert config.preset == "content"
    legacy = adapt_legacy_baseline({"schema": "agentready.audit.v1", "target": "https://example.com", "checks": []})
    assert legacy.version == "v2"


def test_inventory_pagination_and_exports():
    items = [{"id": str(index)} for index in range(3)]
    assert paginate_inventory(items, page=2, page_size=2)["items"] == [{"id": "2"}]
    assert export_inventory(items).count("\n") == 3
    assert "id" in export_inventory(items, format="csv")


def test_job_manager_completes_work():
    manager = AuditJobManager(max_jobs=1)
    job_id = manager.submit(lambda: {"ok": True})
    snapshot = manager.get(job_id)
    assert snapshot.status in {JobStatus.RUNNING, JobStatus.COMPLETED}
    while manager.get(job_id).status is JobStatus.RUNNING:
        time.sleep(0.001)
    assert manager.get(job_id).result == {"ok": True}
