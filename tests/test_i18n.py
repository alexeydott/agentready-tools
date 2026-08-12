import json

from agentready.i18n import normalize_language
from agentready.models import (
    CategoryScore,
    CheckResult,
    NextLevel,
    Recommendation,
    Remediation,
    ScanReport,
)
from agentready.report import render_console, render_html, render_json, render_markdown


def sample_report(language: str = "ru") -> ScanReport:
    check = CheckResult(
        id="robots-txt",
        title="robots.txt",
        category="Discoverability",
        status="fail",
        scored=True,
        details="robots.txt must be HTTP 200 plain text and contain a User-agent directive",
        remediation=Remediation(
            summary="Publish /robots.txt as plain text with at least one User-agent directive; include your intended crawler policy explicitly.",
            rerun_command="agentready audit 'https://example.com/' --mode readiness --include robots-txt",
            references=["https://www.rfc-editor.org/rfc/rfc9309"],
            agent_prompt="old english prompt",
        ),
    )
    return ScanReport(
        target="https://example.com/",
        origin="https://example.com",
        preset="all",
        checks=[check],
        score=0,
        level=0,
        level_name="Not Agent-Ready",
        level_model="transparent-tiered-v2",
        categories=[CategoryScore("Discoverability", 0, 1, 0)],
        next_level=NextLevel(1, "Basic Web Presence", ["valid robots.txt"], 0, 1, 1),
        recommendations=[
            Recommendation(
                check_id="robots-txt",
                title="robots.txt",
                action=check.remediation.summary,
                reason="Agents need a deterministic way to discover machine-readable resources without scraping the UI.",
                impact="high",
                effort="low",
                priority=30,
            )
        ],
        is_commerce=False,
        commerce_signals=[],
        started_at="2026-08-07T00:00:00+00:00",
        finished_at="2026-08-07T00:00:01+00:00",
        language=language,
    )


def test_language_normalization():
    assert normalize_language("ru-RU") == "ru"
    assert normalize_language("en_US") == "en"


def test_russian_json_keeps_machine_ids_stable():
    payload = json.loads(render_json(sample_report(), "ru"))
    assert payload["language"] == "ru"
    assert payload["checks"][0]["id"] == "robots-txt"
    assert payload["checks"][0]["status"] == "fail"
    assert payload["checks"][0]["category"] == "Обнаружимость"
    assert "должен возвращаться" in payload["checks"][0]["details"]
    assert "Опубликуйте /robots.txt" in payload["checks"][0]["remediation"]["summary"]
    assert "Улучшите готовность сайта" in payload["checks"][0]["remediation"]["agent_prompt"]


def test_russian_text_renderers():
    report = sample_report()
    console = render_console(report, "ru")
    markdown = render_markdown(report, "ru")
    assert "Отчёт о готовности сайта" in console
    assert "Приоритетные рекомендации" in console
    assert "## Проверки" in markdown
    assert "| ошибка |" in markdown


def test_html_dashboard_contains_language_switcher_and_both_locales():
    output = render_html(sample_report(), "ru")
    assert "<select id='lang'>" in output
    assert "data-lang='ru'" in output
    assert "data-lang='en'" in output
    assert "Отчёт о готовности сайта" in output
    assert "Agent Readiness report" in output
    heading_index = output.index("<h1>Отчёт о готовности сайта")
    assert output.index("<p class='report-generated'><small>", heading_index) > heading_index
    assert ".report-generated{margin:.25rem 0 1rem;color:#6b7280;font-size:.85rem}" in output
    assert ".pass,.fail,.error,.warn{font-weight:400}" in output
    assert "class='check-help'" in output
    assert "В файле robots.txt содержатся инструкции" in output
    assert "class='category-help check-help'" in output
    assert "Насколько легко агентам" in output
    assert "@media print" in output
    assert ".toolbar{display:none!important}" in output
    assert ".check-help{display:none!important}" in output
    assert "@page{size:A4" in output
    assert "details:not([open])>*:not(summary){display:block}" in output
    assert "beforeprint" in output
