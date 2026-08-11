import pytest

from agentready.models import Evidence, Remediation
from agentready.seo_models import SeoCategoryScore, SeoCheckResult, SeoRecommendation, SeoReport
from agentready.seo_report import render_seo
from agentready.seo_scanner import compare_seo_baseline
from agentready.seo_scoring import score_checks
import agentready.seo_checks as seo_checks


def seo_row(check_id: str, status: str, category: str = "metadata") -> SeoCheckResult:
    return SeoCheckResult(check_id, check_id, category, status, True, status)


def test_seo_score_and_categories_are_independent():
    score, categories = score_checks([seo_row("title", "pass"), seo_row("canonical", "fail", "indexability")])
    assert score == 50
    assert {item.category for item in categories} == {"metadata", "indexability"}


def test_seo_report_has_dedicated_schema_and_renderers():
    report = SeoReport(
        schema="agentready.seo.v1",
        target="https://example.com/",
        origin="https://example.com",
        checks=[seo_row("title", "pass")],
        score=100,
        categories=[SeoCategoryScore("metadata", 1, 1, 100)],
        recommendations=[],
        started_at="now",
        finished_at="now",
    )
    assert "agentready.seo.v1" in render_seo(report, "json")
    assert "<details>" in render_seo(report, "html")
    assert "## Checks" in render_seo(report, "markdown")
    assert "Оценка SEO" in render_seo(report, "console", "ru")


def test_seo_html_localizes_check_name_and_adds_hover_help():
    report = SeoReport(
        schema="agentready.seo.v1",
        target="https://example.com/",
        origin="https://example.com",
        checks=[SeoCheckResult("page-metadata", "fallback title", "metadata", "fail", True, "missing title")],
        score=0,
        categories=[SeoCategoryScore("metadata", 0, 1, 0)],
        recommendations=[],
        started_at="now",
        finished_at="now",
    )
    output = render_seo(report, "html", "ru")
    assert "Title, description и заголовки" in output
    assert "class='check-help'" in output
    assert "Проверяет title, meta description и заголовок H1" in output
    assert '<th scope="col">Проверка</th>' in output
    assert "Оценки по категориям" in output
    assert "<h1>Отчёт по SEO-оптимизации</h1>\n<p class=\"report-generated\"><small>" in output
    assert ".report-generated{margin:.25rem 0 1rem;color:#6b7280;font-size:.85rem}" in output
    assert "class='category-help check-help'" in output
    assert "@media print" in output
    assert ".toolbar{display:none!important}" in output
    assert ".check-help{display:none!important}" in output


def test_seo_report_exposes_expandable_evidence_and_json_metrics():
    evidence = Evidence(
        action="inspect image attributes",
        url="https://example.com/",
        metrics={"images": [{"url": "https://example.com/missing.png", "alt": ""}]},
    )
    report = SeoReport(
        schema="agentready.seo.v1",
        target="https://example.com/",
        origin="https://example.com",
        checks=[SeoCheckResult("image-alt", "Image alt attributes", "content", "warn", True, "one image missing alt text", evidence=[evidence])],
        score=0,
        categories=[SeoCategoryScore("content", 0, 1, 0)],
        recommendations=[],
        started_at="now",
        finished_at="now",
    )
    html = render_seo(report, "html", "ru")
    payload = render_seo(report, "json", "ru")
    markdown = render_seo(report, "markdown", "ru")
    console = render_seo(report, "console", "ru")
    assert "<summary>Дополнительно</summary>" in html
    assert "missing.png" in html
    assert '"metrics": {' in payload
    assert "inspect image attributes" in payload
    assert "missing.png" in markdown
    assert "https://example.com/" in console


def test_seo_html_displays_affected_insecure_link_pages():
    report = SeoReport(
        schema="agentready.seo.v1",
        target="https://example.com/",
        origin="https://example.com",
        checks=[
            SeoCheckResult(
                "insecure-links-pages",
                "HTTPS to HTTP links across crawled pages",
                "technical",
                "warn",
                True,
                "1 page(s) with insecure HTTP links: https://example.com/shop (1)",
                evidence=[
                    Evidence(
                        action="inspect insecure links across crawled pages",
                        url="https://example.com/shop",
                        finding="1 HTTP link(s) on crawled page",
                        metrics={"insecure_links": [{"url": "http://legacy.example.com"}]},
                    )
                ],
            )
        ],
        score=0,
        categories=[SeoCategoryScore("technical", 0, 1, 0)],
        recommendations=[],
        started_at="now",
        finished_at="now",
    )

    output = render_seo(report, "html", "ru")

    assert "Проблемные страницы:" in output
    assert "https://example.com/shop" in output
    assert "http://legacy.example.com" in output


@pytest.mark.parametrize("status", ["pass", "skip"])
def test_seo_report_hides_additional_evidence_for_non_problem_statuses(status):
    report = SeoReport(
        schema="agentready.seo.v1",
        target="https://example.com/",
        origin="https://example.com",
        checks=[
            SeoCheckResult(
                "page-available",
                "Page availability",
                "technical",
                status,
                status == "pass",
                "ok",
                evidence=[Evidence(action="inspect page", finding="diagnostic evidence")],
            )
        ],
        score=100,
        categories=[],
        recommendations=[],
        started_at="now",
        finished_at="now",
    )

    output = render_seo(report, "html", "en")

    assert "<summary>Additional details</summary>" not in output
    assert "diagnostic evidence" not in output


def test_seo_report_localizes_details_recommendations_and_remediation():
    """Russian SEO reports must not leak scanner-generated English sentences."""
    report = SeoReport(
        schema="agentready.seo.v1",
        target="https://example.com/",
        origin="https://example.com",
        checks=[
            SeoCheckResult(
                "page-metadata",
                "fallback title",
                "metadata",
                "fail",
                True,
                "missing meta description; expected one H1, found 0",
                remediation=Remediation(
                    summary="Add a unique descriptive title, meta description and one clear H1.",
                    rerun_command="agentready seo audit 'https://example.com/'",
                ),
            ),
            SeoCheckResult(
                "canonical",
                "Canonical URL",
                "indexability",
                "fail",
                True,
                "canonical is missing, duplicated or points elsewhere",
                remediation=Remediation(
                    summary="Publish one canonical link matching the selected public URL unless a deliberate duplicate strategy applies.",
                    rerun_command="agentready seo audit 'https://example.com/'",
                ),
            ),
        ],
        score=0,
        categories=[SeoCategoryScore("metadata", 0, 1, 0)],
        recommendations=[
            SeoRecommendation(
                check_id="page-metadata",
                title="fallback title",
                action="Add a unique descriptive title, meta description and one clear H1.",
                reason="missing",
                impact="medium",
                effort="low",
                priority=1,
            )
        ],
        started_at="now",
        finished_at="now",
    )
    for fmt in ("html", "console", "markdown"):
        output = render_seo(report, fmt, "ru")
        assert "missing meta description" not in output, f"{fmt} leaks English details"
        assert "expected one H1, found 0" not in output, f"{fmt} leaks English details"
        assert "canonical is missing, duplicated or points elsewhere" not in output, f"{fmt} leaks English details"
        assert "Add a unique descriptive title" not in output, f"{fmt} leaks English remediation"
        assert "отсутствует meta description" in output, f"{fmt} missing Russian detail"
        assert "Добавьте уникальный" in output, f"{fmt} missing Russian recommendation"
    for fmt in ("html", "markdown"):
        output = render_seo(report, fmt, "ru")
        assert "Publish one canonical link" not in output, f"{fmt} leaks English remediation"
        assert "Опубликуйте один canonical link" in output, f"{fmt} missing Russian remediation"


def test_seo_report_print_uses_a4_and_expands_details():
    report = SeoReport(
        schema="agentready.seo.v1",
        target="https://example.com/",
        origin="https://example.com",
        checks=[],
        score=0,
        categories=[],
        recommendations=[],
        started_at="now",
        finished_at="now",
    )
    output = render_seo(report, "html", "ru")
    assert "@page{size:A4" in output
    assert "details:not([open])>*:not(summary){display:block}" in output
    assert "beforeprint" in output


def test_seo_baseline_rejects_agentready_schema(tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"score": 90, "checks": []}', encoding="utf-8")
    report = SeoReport(
        schema="agentready.seo.v1",
        target="https://example.com/",
        origin="https://example.com",
        checks=[],
        score=90,
        categories=[],
        recommendations=[],
        started_at="now",
        finished_at="now",
    )
    try:
        compare_seo_baseline(report, str(baseline))
    except ValueError as exc:
        assert "agentready.seo.v1" in str(exc)
    else:
        raise AssertionError("incompatible baseline was accepted")


def test_seo_recommendation_inputs_remain_typed():
    row = seo_row("title", "fail")
    row.remediation = Remediation("fix title", "agentready seo audit https://example.com")
    assert row.remediation.summary == "fix title"


def test_favicon_malformed_url_does_not_abort_audit(monkeypatch):
    class Parser:
        favicons = ["https://example.com:bad,"]

    class Client:
        def get(self, url):
            raise ValueError("Port could not be cast to integer value as ','")

    monkeypatch.setattr(seo_checks, "_fetch_page", lambda url, client: (Parser(), object(), None))
    result = seo_checks.check_favicon("https://example.com/", Client())
    assert result.status == "warn"
    assert "Port could not be cast" in result.details
