import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_i18n import sample_report

from agentready.agentfindings import build_findings, build_remediation_plan
from agentready.models import Evidence, Remediation
from agentready.seo_models import (
    SeoCategoryScore,
    SeoCheckResult,
    SeoRecommendation,
    SeoReport,
)


def _seo_report(language: str = "en") -> SeoReport:
    return SeoReport(
        schema="agentready.seo.v2",
        target="https://example.com/page",
        origin="https://example.com",
        checks=[
            SeoCheckResult(
                "page-metadata",
                "Title, description and headings",
                "metadata",
                "fail",
                True,
                "missing meta description",
                evidence=[Evidence(action="fetch page", finding="missing meta description")],
                remediation=Remediation(
                    summary="Add a unique, descriptive meta description to the page.",
                    rerun_command="agentready audit 'https://example.com/page' --mode seo --checks page-metadata",
                    references=["https://developers.google.com/search/docs/appearance/snippet"],
                ),
            ),
            SeoCheckResult(
                "favicon",
                "Favicon reachability",
                "metadata",
                "pass",
                True,
                "favicon ok",
            ),
        ],
        score=50,
        categories=[SeoCategoryScore("metadata", 0, 2, 0)],
        recommendations=[
            SeoRecommendation(
                check_id="page-metadata",
                title="Title, description and headings",
                action="Add a unique, descriptive meta description to the page.",
                reason="missing meta description",
                impact="medium",
                effort="low",
                priority=1,
            )
        ],
        started_at="2026-08-08T00:00:00+00:00",
        finished_at="2026-08-08T00:00:01+00:00",
        language=language,
    )


def test_findings_include_only_problem_checks_with_instructions():
    payload = build_findings(sample_report("en"), "en")
    assert payload["schema"] == "agentready.findings.v2"
    assert payload["mode"] == "readiness"
    assert payload["findings_count"] == 1
    item = payload["findings"][0]
    assert item["check_id"] == "robots-txt"
    assert item["status"] == "fail"
    assert item["why"]
    assert item["remediation"]["instructions"]
    assert item["remediation"]["rerun_command"] == "agentready audit 'https://example.com/' --mode readiness --include robots-txt"
    assert item["remediation"]["references"] == ["https://www.rfc-editor.org/rfc/rfc9309"]
    assert "robots-txt" in item["remediation"]["agent_prompt"]
    assert item["priority"] == 1
    assert item["impact"] == "high"
    assert item["effort"] == "low"


def test_findings_are_localized_to_russian():
    payload = build_findings(sample_report("ru"), "ru")
    item = payload["findings"][0]
    assert "робот" in item["why"].lower() or "robots.txt" in item["why"]
    assert "Улучшите готовность сайта" in item["remediation"]["agent_prompt"]
    assert "--lang ru" in item["remediation"]["agent_prompt"]


def test_findings_message_when_no_gaps():
    report = sample_report("en")
    ok = report.checks[0]
    report.checks = [
        type(ok)(
            id=ok.id,
            title=ok.title,
            category=ok.category,
            status="pass",
            scored=True,
            details="ok",
        )
    ]
    payload = build_findings(report, "en")
    assert payload["findings_count"] == 0
    assert payload["message"] == "No optimization gaps found. All audited checks passed."


def test_findings_for_seo_mode():
    payload = build_findings(_seo_report(), "en")
    assert payload["mode"] == "seo"
    assert payload["findings_count"] == 1
    item = payload["findings"][0]
    assert item["check_id"] == "page-metadata"
    assert item["category"] == "Metadata"
    assert "missing meta description" in item["evidence"]
    assert "meta description" in item["remediation"]["instructions"]


def test_findings_for_seo_mode_russian_prompt_uses_seo_command():
    payload = build_findings(_seo_report("ru"), "ru")
    prompt = payload["findings"][0]["remediation"]["agent_prompt"]
    assert "agentready audit --mode seo" in prompt
    assert "--include" in prompt
    assert payload["findings"][0]["category"] == "Метаданные"


def test_remediation_plan_orders_steps_by_priority():
    report = sample_report("en")
    plan = build_remediation_plan(report, "en")
    assert plan["schema"] == "agentready.remediation-plan.v2"
    assert plan["mode"] == "readiness"
    assert plan["steps_count"] == 1
    step = plan["steps"][0]
    assert step["step"] == 1
    assert step["check_id"] == "robots-txt"
    assert step["verify"].startswith("agentready audit 'https://example.com/' --mode readiness")
    assert step["references"]
    assert plan["intro"]


def test_remediation_plan_seo_mode():
    plan = build_remediation_plan(_seo_report("ru"), "ru")
    assert plan["mode"] == "seo"
    assert plan["subject"] == "SEO-оптимизации"
    assert plan["steps_count"] == 1
    assert "agentready audit --mode seo" in plan["steps"][0]["agent_prompt"]


def test_mcp_server_registers_agent_tools_and_rejects_bad_mode(monkeypatch):
    pytest.importorskip("mcp")
    import agentready.mcp_server as mcp_module

    async def _tools():
        return await mcp_module.mcp.list_tools()

    names = {tool.name for tool in asyncio.run(_tools())}
    assert {"audit_v2", "seo_audit_v2", "audit_findings", "remediation_plan"} <= names

    monkeypatch.setattr(
        mcp_module,
        "audit_v2",
        lambda url, **kwargs: {
            "schema": "agentready.audit.v2",
            "target": url,
            "coverage": {},
            "findings": [{"id": "robots-txt", "title": "Robots", "status": "fail", "reason": "Missing"}],
        },
    )
    payload = mcp_module.audit_findings("https://example.com", language="ru")
    assert payload["schema"] == "agentready.findings.v2"
    assert payload["language"] == "ru"

    plan = mcp_module.remediation_plan("https://example.com", language="en")
    assert plan["schema"] == "agentready.remediation-plan.v2"

    with pytest.raises(ValueError, match="unsupported mode"):
        mcp_module.audit_findings("https://example.com", mode="bogus")


def test_mcp_seo_audit_exposes_crawl_option(monkeypatch):
    pytest.importorskip("mcp")
    import agentready.mcp_server as mcp_module

    captured: dict = {}

    class FakeReport:
        def to_dict(self):
            return {"schema": "agentready.seo.v2", "checks": []}

    def fake_audit(url, **kwargs):
        captured.update(kwargs)
        return FakeReport()

    monkeypatch.setattr(mcp_module, "audit_seo", fake_audit)
    result = mcp_module.seo_audit_v2("https://example.com", crawl=True, max_pages=7, language="ru")

    assert result["schema"] == "agentready.seo.v2"
    assert captured["crawl"] is True
    assert captured["max_pages"] == 7
    assert captured["language"] == "ru"
