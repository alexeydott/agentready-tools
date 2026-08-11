import re

from agentready.dashboard import render_dashboard
from agentready.models import CategoryScore, CheckResult, ScanReport
from agentready.report import render_html
from agentready.report_styles import BASE_REPORT_CSS


def _report() -> ScanReport:
    return ScanReport(
        target="https://example.test/",
        origin="https://example.test",
        preset="all",
        checks=[CheckResult("robots", "Robots", "discovery", "warn", True, "Review robots.txt")],
        score=80,
        level=2,
        level_name="Ready",
        level_model="model",
        categories=[CategoryScore("discovery", 1, 1, 100)],
        next_level=None,
        recommendations=[],
        is_commerce=False,
        commerce_signals=[],
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
    )


def test_dashboard_accessibility_foundation_is_localized_and_live():
    html = render_dashboard("en")

    assert 'class="skip-link" href="#main-content"' in html
    assert '<div class="dashboard-layout" id="main-content">' in html
    assert '<main class="dashboard-main">' in html
    assert "<summary>Advanced parameters <h2 class=\"sr-only\">" in html
    assert 'id="result" hidden role="status" aria-live="polite"' in html
    assert 'id="progress" hidden role="status" aria-live="polite"' in html
    assert 'id="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"' in html
    assert 'id="help-toggle"' in html and 'aria-controls="help-content"' in html
    assert '(visible ? helpContent : helpToggle).focus()' in html
    assert '<noscript><section class="noscript-notice"' in html
    assert "agentready scan https://example.com --format html" in html
    assert "min-height:44px" in html


def test_dashboard_v2_preset_has_hint_and_configurable_crawl_budget():
    for language, profile_hint, budget_label in (
        ("en", "vNext bounded crawl", "vNext page limit"),
        ("ru", "Ограниченный обход vNext", "Лимит страниц vNext"),
    ):
        html = render_dashboard(language)

        assert profile_hint in html
        assert "v2:translations[language.value].profile_v2" in html
        assert budget_label in html
        assert 'id="v2-profile"' in html
        assert 'id="v2-max-pages"' in html
        assert 'id="v2-render"' in html
        assert 'profile:document.getElementById("v2-profile").value' in html
        assert 'max_pages:Number(document.getElementById("v2-max-pages").value)' in html
        assert 'render:document.getElementById("v2-render").checked' in html
        assert 'id="v2-inventory-panel"' in html
        assert 'async function loadV2Inventory' in html
        assert '/v2/runs/" + encodeURIComponent(runId) + "/overview' in html
        assert 'id="v2-inventory-limit"' in html
        assert 'loadNextV2Inventory' in html
        assert 'filterV2Inventory' in html


def test_dashboard_noscript_guidance_is_localized():
    html = render_dashboard("ru")

    assert "JavaScript отключён" in html
    assert "Используйте CLI или локальный API" in html


def test_report_accessibility_foundation_has_landmark_table_semantics_and_responsive_css():
    html = render_html(_report(), "en")

    assert "class='skip-link' href='#report-content'" in html
    assert "id='report-content'" in html
    assert "<div class='table-wrap'><table id='report-checks-table'><caption>Checks</caption>" in html
    assert "scope='col'" in html
    assert "<summary id='report-recommendations'><h3>Prioritized recommendations</h3></summary>" in html
    assert ".table-wrap{width:100%;overflow-x:auto}" in html
    assert ".skip-link:focus" in BASE_REPORT_CSS
    assert "report-status-filter" in html
    assert "report-search" in html
    assert "report-filter-count" in html
    assert "aria-live='polite'" in html
    assert "event.key==='Escape'" in html
    assert "filters.hidden=false" in html
    assert "const activeMain=mains.find(x=>x.dataset.lang===v),skip=document.querySelector('.skip-link')" in html


def test_report_pass3_status_and_score_semantics_are_not_color_only():
    html = render_html(_report(), "en")

    assert "class='status-cell warn'" in html
    assert "<span class='status-marker' aria-hidden='true'>!</span>" in html
    assert "<meter min='0' max='100' value='80'" in html
    assert "role='progressbar'" in html
    assert ".status-cell.fail{background:#fef2f2;color:#991b1b}" in html
    assert "@media(max-width:700px)" in html


def test_report_pass4_preserves_keyboard_print_and_localized_filter_safeguards():
    html = render_html(_report(), "en")

    assert "a:focus-visible" in html
    assert "const filterTemplates={\"en\": \"{visible} of {total} checks shown\", \"ru\": \"Показано проверок: {visible} из {total}\"}" in html
    assert "template=filterTemplates[main.dataset.lang]" in html
    assert "<div class='report-filters' hidden>" in html
    assert "@media print" in html
    assert "aria-labelledby='report-score-title'" in html


def test_report_progressive_filters_bind_each_localized_report_copy():
    html = render_html(_report(), "en")

    assert html.count("class='report-filters' hidden") == 2
    assert "const mains=[...document.querySelectorAll('main[data-lang]')]" in html
    assert "mains.forEach(bindFilters)" in html
    assert "search.addEventListener('keydown'" in html


def test_report_component_contracts_are_wired_into_each_localized_copy():
    html = render_html(_report(), "en")

    assert html.count("class='status-badge status-warn'") == 2
    assert html.count("class='score-panel'") == 2
    assert html.count("role='progressbar'") == 2
    assert html.count("class='table-wrap'><table") == 2
    assert html.count("scope='col'") == 12


def test_report_shell_acceptance_preserves_no_js_and_print_fallbacks():
    html = render_html(_report(), "en")

    assert html.count("<div class='report-filters' hidden>") == 2
    assert "details:not([open])>*:not(summary){display:block}" in html
    assert html.count("class='report-nav'") == 2
    assert html.count("<details class='report-section'>") == 4


def test_report_localized_copies_have_unique_ids_and_local_references():
    html = render_html(_report(), "en")
    ids = re.findall(r"\bid='([^']+)'", html)

    assert len(ids) == len(set(ids))
    assert "id='report-status-filter-ru'" in html
    assert "aria-controls='report-checks-table-ru'" in html
    assert "href='#report-summary-ru'" in html


def test_dashboard_combined_reports_namespace_ids_and_set_document_language():
    html = render_dashboard("en")

    assert "function namespaceReport(root, prefix)" in html
    assert 'namespaceReport(geo.body, "geo")' in html
    assert 'namespaceReport(seo.body, "seo")' in html
    assert 'body.querySelectorAll("script").forEach(script => script.remove())' in html
    assert "data-report-instance='geo'" in html
    assert "document.documentElement.lang=value;mains.forEach" in html
    assert "window.addEventListener('beforeprint'" in html
    assert "<!doctype html><html lang='" in html


def test_dashboard_report_actions_are_shared_by_single_and_combined_exports():
    html = render_dashboard("en")

    assert "function createReportActions(reportText, frame)" in html
    assert html.count("createReportActions(reportText, frame)") == 2
    assert "createReportActions(combined, frame)" in html


def test_combined_report_acceptance_contract_rewrites_internal_references():
    html = render_dashboard("en")

    assert '["for", "aria-controls", "aria-labelledby", "aria-describedby"]' in html
    assert "ids.get(item) || item" in html
    assert 'link.setAttribute("href", "#" + ids.get(target))' in html
    assert "data-report-instance='seo'" in html
    assert 'body.querySelectorAll("script").forEach(script => script.remove())' in html
