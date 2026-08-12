import sys
from pathlib import Path
from typing import ClassVar

sys.path.insert(0, str(Path(__file__).parent))

from agentready.mobile_checks import (
    MOBILE_CHECK_METADATA,
    check_viewport_meta,
)
from agentready.mobile_models import (
    MobileCheckResult,
    MobilePageReport,
    MobileReport,
)
from agentready.mobile_report import render_mobile, render_mobile_html
from agentready.mobile_scanner import audit_mobile
from agentready.mobile_scoring import rank_mobile_recommendations, score_mobile_checks
from agentready.models import Evidence, Remediation


def _check(check_id: str, status: str, category: str = "configuration", scored: bool = True) -> MobileCheckResult:
    return MobileCheckResult(
        id=check_id,
        title=check_id.replace("-", " ").title(),
        category=category,
        status=status,  # type: ignore[arg-type]
        scored=scored,
        details=f"{check_id} {status}",
        evidence=[Evidence(action="inspect", finding=f"{check_id} finding")],
        remediation=Remediation(
            summary=f"Fix {check_id}.",
            rerun_command="agentready audit 'https://example.com' --mode mobile --render",
            references=["https://example.com/ref"],
        )
        if status in {"fail", "warn", "error"}
        else None,
    )


def _page(url: str, checks: list[MobileCheckResult], rendered: bool = False) -> MobilePageReport:
    score, categories = score_mobile_checks(checks)
    return MobilePageReport(
        url=url,
        rendered=rendered,
        checks=checks,
        score=score,
        categories=categories,
        recommendations=rank_mobile_recommendations(checks),
        started_at="2026-08-08T00:00:00+00:00",
        finished_at="2026-08-08T00:00:01+00:00",
    )


def _report(pages: list[MobilePageReport]) -> MobileReport:
    all_checks = [check for page in pages for check in page.checks]
    score, categories = score_mobile_checks(all_checks)
    return MobileReport(
        schema="agentready.mobile.v2",
        targets=[page.url for page in pages],
        pages=pages,
        score=score,
        categories=categories,
        recommendations=rank_mobile_recommendations(all_checks),
        started_at="2026-08-08T00:00:00+00:00",
        finished_at="2026-08-08T00:00:01+00:00",
        language="en",
    )


def test_mobile_static_checks_run_against_fixture_html():
    class FakeResponse:
        status_code = 200
        content_type = "text/html"
        text = "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body><p>Hello</p></body></html>"
        headers: ClassVar[dict[str, str]] = {}

        def evidence(self, action, **kwargs):
            return Evidence(action=action, url="https://example.com")

    class FakeClient:
        def get(self, url, **kwargs):
            return FakeResponse()

    result = check_viewport_meta("https://example.com", FakeClient())
    assert result.status == "pass"
    assert result.scored is True


def test_mobile_scoring_aggregates_pages():
    page_a = _page("https://a.example", [_check("viewport-meta", "pass"), _check("font-readability", "fail", "content")])
    page_b = _page("https://b.example", [_check("viewport-meta", "pass"), _check("touch-targets", "warn", "usability")])
    report = _report([page_a, page_b])
    assert report.schema == "agentready.mobile.v2"
    assert report.score == 50  # 2 pass of 4 applicable
    assert len(report.categories) == 3
    assert len(report.recommendations) == 2
    assert report.recommendations[0].check_id == "font-readability"  # content fail outranks usability warn


def test_mobile_report_renders_all_formats():
    page = _page("https://example.com", [_check("viewport-meta", "fail"), _check("font-readability", "pass", "content")])
    report = _report([page])
    for fmt in ("console", "json", "markdown", "html"):
        output = render_mobile(report, fmt, "en")
        assert output
    html_output = render_mobile_html(report, "ru")
    assert "Отчёт о мобильной дружественности" in html_output
    assert "viewport-meta" in html_output
    assert "check-table check-table--compact" in html_output
    assert "status-badge status-fail" in html_output
    assert '<h1>Отчёт о мобильной дружественности</h1>\n<p class="report-generated"><small>' in html_output
    assert ".report-generated{margin:.25rem 0 1rem;color:#6b7280;font-size:.85rem}" in html_output


def test_mobile_report_localizes_details_and_remediation():
    """Russian mobile reports must not leak scanner-generated English sentences."""
    page = _page(
        "https://example.com",
        [_check("viewport-meta", "fail"), _check("touch-targets", "warn", "usability")],
    )
    page.checks[0].details = "viewport meta missing or incomplete (need width=device-width and initial-scale)"
    page.checks[1].details = "976 interactive elements detected; keep spacing and size adequate for touch"
    report = _report([page])
    for fmt in ("console", "markdown", "html"):
        output = render_mobile(report, fmt, "ru")
        assert "viewport meta missing or incomplete" not in output, f"{fmt} leaks English details"
        assert "interactive elements detected" not in output, f"{fmt} leaks English details"
        assert "Ensure links, buttons and inputs are at least" not in output, f"{fmt} leaks English remediation"
        assert "viewport meta отсутствует или неполный" in output, f"{fmt} missing Russian detail"
        assert "мишеней касания" in output, f"{fmt} missing Russian detail"


def test_mobile_report_print_uses_a4_and_expands_details():
    report = _report([_page("https://example.com", [_check("viewport-meta", "pass")])])
    output = render_mobile_html(report, "ru")
    assert "@page{size:A4" in output
    assert "details:not([open])>*:not(summary){display:block}" in output
    assert "beforeprint" in output


def test_mobile_audit_rejects_private_targets():
    import pytest

    with pytest.raises(ValueError):
        audit_mobile(["http://127.0.0.1/"], allow_private=False)


def test_mobile_mode_help_is_available_on_canonical_audit_command():
    from agentready.cli import build_parser

    command = next(action for action in build_parser()._actions if action.dest == "command")
    audit_parser = command.choices["audit"]
    assert "--mode" in audit_parser.format_help()
    assert "--render" in audit_parser.format_help()


def test_mobile_server_endpoints_exist():
    from fastapi.testclient import TestClient

    from agentready.server import app

    paths = {route.path for route in app.routes}
    assert {"/mobile/checks", "/v2/mobile/audit", "/v2/mobile/audit/dashboard"} <= paths

    client = TestClient(app)
    response = client.get("/mobile/checks", params={"language": "ru"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 6
    assert all(item["language"] == "ru" for item in payload)
    assert any(item["id"] == "viewport-meta" for item in payload)


def test_mobile_mcp_tools_registered(monkeypatch):
    import asyncio

    import pytest

    pytest.importorskip("mcp")
    import agentready.mcp_server as mcp_module

    async def _tools():
        return await mcp_module.mcp.list_tools()

    names = {tool.name for tool in asyncio.run(_tools())}
    assert {"mobile_audit_v2", "mobile_findings", "mobile_remediation_plan"} <= names

    page = _page("https://example.com", [_check("viewport-meta", "fail")])
    fake_report = _report([page])
    monkeypatch.setattr(mcp_module, "audit_mobile", lambda urls, **kwargs: fake_report)
    payload = mcp_module.mobile_audit_v2(["https://example.com"], language="en")
    assert payload["schema"] == "agentready.mobile.v2"
    assert payload["score"] == 0

    findings = mcp_module.mobile_findings("https://example.com", language="en")
    assert findings["mode"] == "mobile"
    assert findings["findings_count"] == 1

    plan = mcp_module.mobile_remediation_plan("https://example.com", language="en")
    assert plan["mode"] == "mobile"
    assert plan["steps_count"] == 1


def test_mobile_check_metadata_is_localized():
    assert len(MOBILE_CHECK_METADATA) == 6
    for item in MOBILE_CHECK_METADATA:
        assert item["title"]["en"] and item["title"]["ru"]
        assert item["category"]["en"] and item["category"]["ru"]
        assert item["description"]["en"] and item["description"]["ru"]


def test_mobile_render_preserves_exact_optional_dependency_skip(monkeypatch):
    from agentready.browser_pool import CapabilityUnavailableError

    class FakeResponse:
        status_code = 200
        content_type = "text/html"
        text = "<html><head><meta name='viewport' content='width=device-width'></head></html>"
        headers: ClassVar[dict[str, str]] = {}

        def evidence(self, action, **kwargs):
            return Evidence(action=action, url="https://example.com")

    class FakeHttpClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, **kwargs):
            return FakeResponse()

    class MissingBrowserPool:
        def __init__(self, policy):
            pass

        async def start(self):
            raise CapabilityUnavailableError(
                "Playwright browser support",
                "Install the optional browser extra.",
            )

        async def close(self):
            pass

    monkeypatch.setattr("agentready.mobile_scanner.HttpClient", FakeHttpClient)
    monkeypatch.setattr("agentready.mobile_scanner.BrowserPool", MissingBrowserPool)
    report = audit_mobile(["https://example.com"], render=True)

    rendered = [check for check in report.pages[0].checks if check.id.startswith("rendered-")]
    assert len(rendered) == 3
    assert {(check.status, check.scored, check.details) for check in rendered} == {
        ("skip", False, "playwright not installed")
    }


def test_rendered_checks_use_one_shared_async_pool():
    import asyncio
    from contextlib import asynccontextmanager

    from agentready.mobile_render import MOBILE_RENDER_CHECKS

    class FakePage:
        async def evaluate(self, script):
            if "scrollWidth" in script:
                return {"scrollWidth": 360, "clientWidth": 360, "innerWidth": 360}
            if "tooSmall" in script:
                return {"total": 0, "tooSmall": 0}
            return {"fontSizePx": 16, "zoomBlocked": False}

    class FakePool:
        def __init__(self):
            self.pages = 0
            self.navigations = 0

        @asynccontextmanager
        async def page(self, **kwargs):
            assert kwargs["viewport"] == {"width": 360, "height": 640}
            self.pages += 1
            yield FakePage()

        async def goto(self, page, url, **kwargs):
            assert url == "https://example.com"
            assert kwargs["wait_until"] == "networkidle"
            self.navigations += 1

    async def run():
        pool = FakePool()
        results = [await check("https://example.com", pool) for check in MOBILE_RENDER_CHECKS]
        return pool, results

    pool, results = asyncio.run(run())
    assert pool.pages == len(MOBILE_RENDER_CHECKS)
    assert pool.navigations == len(MOBILE_RENDER_CHECKS)
    assert [result.status for result in results] == ["pass", "skip", "pass"]
