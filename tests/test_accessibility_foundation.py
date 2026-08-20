import re
from pathlib import Path

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
    assert "agentready audit https://example.com --format html" in html
    assert "min-height:44px" in html


def test_dashboard_v2_preset_has_hint_and_configurable_crawl_budget():
    for language, profile_hint, budget_label in (
        ("en", "Bounded crawl through the AuditService pipeline", "Page limit"),
        ("ru", "Ограниченный обход через конвейер AuditService", "Лимит страниц"),
    ):
        html = render_dashboard(language)

        assert profile_hint in html
        assert "v2:translations[language.value].profile_v2" in html
        assert budget_label in html
        assert 'id="v2-profile"' in html
        assert 'id="v2-max-pages"' in html
        assert 'id="crawl-progress"' in html
        assert 'runV2Background' in html
        assert 'discovery_kind:selectedV2Discovery()' in html
        assert 'id="v2-full-discovered"' in html
        assert 'function selectedV2Discovery()' in html
        assert 'cancelActiveV2Job' in html
        assert 'function captureV2Report' in html
        assert 'captureV2Report(html)' in html
        assert 'ai.full_report.open' in html
        assert 'ai_open_full_report_inline' in html
        assert 'function logDashboardAction' in html
        assert 'ai.context.reset' in html
        assert 'DASHBOARD-ACTION' in html
        assert 'inventory.load' in html
        assert 'v2InventoryOverviewRunId' in html
        assert 'inventory.next_page' in html
        assert 'agentready.dashboard.job.v2' in html
        assert 'Service health checked without resetting audit progress' in html
        assert 'const v2ProfileDefaults' in html
        assert 'Profile budget synchronized' in html
        assert 'id="v2-render"' in html
        assert 'profile:document.getElementById("v2-profile").value' in html
        assert 'max_pages:selectedV2MaxPages()' in html
        assert '0 — полный обход' in html or '0 for a full same-origin crawl' in html
        assert 'render:document.getElementById("v2-render").checked' in html
        assert 'crawl:true,max_pages:selectedV2MaxPages()' in html
        assert 'id="v2-inventory-panel"' in html
        assert 'Сводка инвентаря' in html
        assert 'Removed stale localized report' in html
        assert 'async function loadV2Inventory' in html
        assert '/v2/runs/" + encodeURIComponent(runId) + "/overview' in html
        assert 'id="v2-inventory-limit"' in html
        assert 'loadNextV2Inventory' in html
        assert 'filterV2Inventory' in html
        assert 'saveV2InventoryView' in html


def test_dashboard_added_workspaces_have_localized_descriptions_and_help():
    for language, custom_hint, robots_hint in (
        ("en", "Validate a declarative rules document", "Compare the stored robots policy"),
        ("ru", "Проверяет декларативный документ правил", "Сравнивает сохранённую и предлагаемую политику robots"),
    ):
        html = render_dashboard(language)
        assert custom_hint in html
        assert robots_hint in html
        assert "sitemap_reconciliation_hint" in html
        assert "link_graph_hint" in html
        assert "duplicate_clusters_hint" in html
        assert "projects_hint" in html
        custom_panel = html.split('id="custom-rules-panel"', 1)[1].split('</section>', 1)[0]
        projects_panel = html.split('id="projects-panel"', 1)[1].split('</section>', 1)[0]
        assert '<details class="section-help">' not in custom_panel
        assert '<details class="section-help">' not in projects_panel
        tools_open = '<details id="tools-panel" class="panel tools-panel">'
        assert tools_open in html
        assert 'id="tools-panel" class="panel tools-panel" open' not in html
        tools_summary = html.split(tools_open, 1)[1].split('</summary>', 1)[0]
        assert not any(f"<{tag}" in tools_summary for tag in ("button", "input", "select", "textarea"))
        tools_group = html.split(tools_open, 1)[1].split('</div>\n</details>', 1)[0]
        for panel_id in (
            "robots-simulation-panel",
            "sitemap-reconciliation-panel",
            "custom-rules-panel",
            "link-graph-panel",
            "duplicate-clusters-panel",
            "projects-panel",
        ):
            assert f'id="{panel_id}"' in tools_group
        for panel_id in ("robots-simulation-panel", "sitemap-reconciliation-panel", "link-graph-panel", "duplicate-clusters-panel"):
            panel = html.split(f'id="{panel_id}"', 1)[1].split('</section>', 1)[0]
            assert '<details class="section-help">' not in panel
        assert ("Custom rules debugger" in html) if language == "en" else ("Отладчик пользовательских правил" in html)
        assert ("Projects and run history" in html) if language == "en" else ("Проекты и история запусков" in html)
        assert ("Virtual Robots simulation" in html) if language == "en" else ("Симуляция Virtual Robots" in html)
        assert ("Sitemap reconciliation" in html) if language == "en" else ("Сверка sitemap" in html)
        assert ("Link Graph" in html) if language == "en" else ("Граф ссылок" in html)
        assert ("Open the bounded offline" in html) if language == "en" else ("Откройте ограниченные офлайн-инструменты" in html)


def test_dashboard_workspace_guidance_is_documented_in_localized_faqs():
    root = Path(__file__).parents[1]
    english = (root / "docs" / "dashbor_faq_en.md").read_text(encoding="utf-8")
    russian = (root / "docs" / "dashbord_faq_ru.md").read_text(encoding="utf-8")
    assert "## Custom rules debugger" in english
    assert "## Projects and run history" in english
    assert "## Отладчик пользовательских правил" in russian
    assert "## Проекты и история запусков" in russian
    assert "## Virtual Robots simulation" in english
    assert "## Sitemap reconciliation" in english
    assert "## Link Graph" in english
    assert "## Duplicate clusters" in english
    assert "## Симуляция Virtual Robots" in russian
    assert "## Сверка sitemap" in russian
    assert "## Граф ссылок" in russian
    assert "## Кластеры дубликатов" in russian
    assert "Preview matches" in english and "Предпросмотр совпадений" in russian
    assert "Baseline" in english and "Базовый запуск" in russian


def test_dashboard_stored_run_tools_resolve_run_id_per_action():
    html = render_dashboard("en")
    assert "function dashboardRunId()" in html
    for function_name in ("reconcileSitemap", "loadLinkGraph", "loadLinkGraphNode", "loadDuplicateClusters", "loadSitemapCategory"):
        function_start = html.index(f"async function {function_name}")
        function_body = html[function_start : function_start + 900]
        assert "const runId = dashboardRunId();" in function_body


def test_dashboard_tools_localize_visible_controls_and_statuses():
    english = render_dashboard("en")
    russian = render_dashboard("ru")
    for value in ("Dead ends", "Disconnected", "Load graph", "All", "Exact", "Near", "Load clusters", "Change", "Authority algorithm"):
        assert value in english
    for value in ("Тупиковые страницы", "Изолированные страницы", "Загрузить граф", "Все", "Точные", "Близкие", "Загрузить кластеры", "Изменение", "Алгоритм авторитетности"):
        assert value in russian
    tools_group = russian.split('<details id="tools-panel"', 1)[1].split('</details>', 1)[0]
    for value in ("Dead ends", "Disconnected", "Load graph", "Load clusters", "Rules are valid", "Reconciliation complete", "Project saved"):
        assert value not in tools_group
    assert "t.graph_loaded.replace" in russian
    assert "translations[language.value].history_failed" in russian


def test_dashboard_settings_expose_hints_for_scope_and_inventory_controls():
    html = render_dashboard("en")
    for control_id in (
        "v2-discovery",
        "v2-inventory-kind",
        "v2-inventory-limit",
        "v2-inventory-sort",
        "v2-inventory-desc",
        "v2-inventory-columns",
        "v2-saved-view",
        "robots-live",
        "robots-proposed",
        "robots-user-agents",
        "sitemap-reconciliation-origin",
        "sitemap-reconciliation-xml",
        "custom-rules-document",
        "link-graph-dead-end",
        "link-graph-disconnected",
        "duplicate-clusters-kind",
        "project-id",
        "project-name",
    ):
        start = html.index(f'id="{control_id}"')
        context = html[max(0, start - 450): start + 260]
        assert "class='hint'" in context, f"missing hint for {control_id}"
    assert '"ai-provider-name": "ai_provider_name_hint"' in html
    assert '"ai-key": "ai_key_hint"' in html
    assert "addSettingsHints();" in html


def test_tools_child_controls_are_persisted_to_local_and_cache_state():
    html = render_dashboard("en")
    for control_id in (
        "robots-live", "robots-proposed", "robots-user-agents",
        "sitemap-reconciliation-origin", "sitemap-reconciliation-xml",
        "custom-rules-document", "link-graph-dead-end", "link-graph-disconnected",
        "duplicate-clusters-kind", "project-id", "project-name",
    ):
        assert f'"{control_id}"' in html
    assert 'const dashboardStateCacheKey = "/dashboard/state"' in html
    assert 'fetch(dashboardStateCacheKey' in html
    assert "dashboardStateCacheKey" in html
    assert "scheduleSaveDashboardState" in html
    assert "restoreDashboardStateFromCache" in html


def test_dashboard_exposes_full_discovered_page_crawl_mode():
    html = render_dashboard("en")
    assert "All discovered pages" in html
    assert "v2_discovery_hint" in html


def test_dashboard_resets_inventory_cursor_when_query_shape_changes():
    html = render_dashboard("en")

    assert "function resetV2InventoryCursor()" in html
    assert "resetV2InventoryCursor();" in html
    assert "if (cursor !== null) v2InventoryCursor = cursor;" in html
    assert "function safeDashboardTarget(value)" in html
    assert 'raw.startsWith("//") ? "https:" + raw : "https://" + raw' in html
    assert 'Normalized dashboard target protocol' in html
    assert 'target:safeDashboardTarget(document.getElementById("url").value)' in html
    assert 'target:document.getElementById("url").value' not in html


def test_dashboard_stops_new_audit_when_chat_archive_fails():
    html = render_dashboard("en")

    assert "if (aiConversationHistory.length && !(await startNewChat()))" in html
    assert 'console.warn("[FIX:dashboard-context] New audit stopped because the previous chat could not be archived")' in html
    assert "return true;" in html


def test_dashboard_exposes_localized_unlimited_audit_check_limit():
    for language, label, hint in (
        ("en", "Audit check limit", "0 means all selected checks"),
        ("ru", "Ограничение аудита — проверки", "0 — все выбранные проверки"),
    ):
        html = render_dashboard(language)
        assert 'id="check-limit"' in html
        assert label in html
        assert hint in html
        assert 'selectedV2Limits()' in html


def test_dashboard_localizes_inventory_kind_options():
    html = render_dashboard("ru")
    assert '<option value="links">Ссылки</option>' in html
    assert '<option value="resources">Ресурсы</option>' in html
    assert '<option value="findings">Проверки</option>' in html


def test_dashboard_prompt_library_control_is_visible_after_composer_mount():
    html = render_dashboard("ru")

    assert 'select.classList.remove("ai-hidden-compatible")' in html
    assert 'title.classList.remove("ai-hidden-compatible")' in html


def test_dashboard_noscript_guidance_is_localized():
    html = render_dashboard("ru")

    assert "JavaScript отключён" in html
    assert "Используйте CLI или локальный API" in html


def test_report_accessibility_foundation_has_landmark_table_semantics_and_responsive_css():
    html = render_html(_report(), "en")

    assert "class='skip-link' href='#report-content'" in html
    assert "id='report-content'" in html
    assert "<div class='table-wrap'><table id='report-checks-table' class='check-table check-table--full'><caption>Checks</caption>" in html
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
    assert "function createReportFrame(reportText)" in html
    assert "function renderReport(reportText, persist=true)" in html
    assert html.count("createReportActions(reportText, frame)") == 2
    assert "renderReport(combined)" in html
    assert "dashboardReportKey = \"agentready.dashboard.report.v2\"" in html
    assert "boundedV2ReportForStorage" in html
    assert "window.agentreadyV2Report = state.v2Report || null" in html
    assert "if (!window.agentreadyV2Report) captureV2Report(state.html)" in html
    assert "state.preset !== \"v2\" || Boolean(window.agentreadyV2Report)" in html
    assert "restoreReportState();" in html


def test_dashboard_ai_workspace_has_history_conversation_and_context_zones():
    html = render_dashboard("en")

    assert 'class="ai-workspace-grid"' in html
    assert 'class="ai-history-sidebar"' in html
    assert 'class="ai-conversation"' in html
    assert 'class="ai-context-sidebar"' in html
    assert 'class="ai-composer"' in html
    assert 'id="ai-context-chips"' in html
    assert 'id="ai-skills-picker"' in html
    assert 'id="ai-context-picker"' in html
    assert 'function setupPromptComposer()' in html
    assert 'className = "ai-prompt-composer"' in html
    assert 'apply.addEventListener("click", applyPrompt)' in html
    assert 'className = "ai-message-row"' in html
    assert 'className = "ai-composer-links"' in html
    assert 'select.size = 1' in html
    assert '.ai-side-actions #ai-chat-button' in html
    assert '.ai-side-actions input[type=file]' in html
    assert '.ai-composer-links .text-link { margin-right:4px; font-weight:400;' in html
    assert 'function openPromptEditor()' in html
    assert 'ai-prompt-edit-dialog' in html
    assert 'ai-prompt-edit-text' in html
    assert 'AI settings' in html
    history_sidebar = html.split('class="ai-history-sidebar"', 1)[1].split('</aside>', 1)[0]
    assert 'AI settings' not in history_sidebar
    assert 'class="ai-model-actions"' in html
    assert 'id="ai-skills-trigger"' in html
    assert 'id="ai-context-trigger"' in html
    assert 'function toggleAiToolPicker(kind)' in html
    assert 'Optional built-in instructions that shape how the model analyzes the audit.' in html
    assert 'id="ai-chat-search"' in html
    assert 'id="ai-chat-button"' in html
    assert 'event.key === "Enter" && !event.shiftKey' in html
    assert 'onclick="openAiPromptPicker()"' in html
    assert 'function openAiPromptPicker()' in html
    assert 'function toggleAiDrawer(kind)' in html
    assert 'window.aiRequestTimeoutMs' in html
    assert 'timeout_seconds' in html
    assert 'detail && typeof detail === "object"' in html


def test_dashboard_report_navigation_stays_inside_frame():
    html = render_dashboard("en")

    assert "reportDocument.addEventListener(\"click\"" in html
    assert "event.preventDefault();" in html
    assert "target.scrollIntoView({block:\"start\"})" in html
    assert "[FIX:dashboard-report] Local report navigation" in html


def test_dashboard_background_catalog_load_does_not_clear_restored_report():
    html = render_dashboard("en")

    assert "if (showOutput) {" in html
    assert "result.textContent = debugMode()" in html
    assert "loadChecks(false)" in html


def test_combined_report_acceptance_contract_rewrites_internal_references():
    html = render_dashboard("en")

    assert '["for", "aria-controls", "aria-labelledby", "aria-describedby"]' in html
    assert "ids.get(item) || item" in html
    assert 'link.setAttribute("href", "#" + ids.get(target))' in html
    assert "data-report-instance='seo'" in html
    assert 'body.querySelectorAll("script").forEach(script => script.remove())' in html


def test_virtual_robots_session_source_is_prefilled_readonly_only_when_found():
    html = render_dashboard("en")

    assert html.count('class="robots-document-field"') == 2
    assert 'class="robots-document-field"><label for="robots-live">' in html
    assert 'class="robots-document-field"><label for="robots-proposed">' in html
    assert 'async function loadSessionRobots' in html
    assert '/v2/runs/" + encodeURIComponent(runId) + "/robots/source' in html
    assert 'live.readOnly = found' in html
    assert 'live.dataset.userEdited' in html
    assert "Current robots.txt loaded from this audit session." in html


def test_link_graph_filters_use_compact_checkboxes_and_have_hints():
    html = render_dashboard("en")
    assert "#link-graph-panel input[type=checkbox]" in html
    assert "#link-graph-panel input[type=checkbox] { width:auto;" in html
    panel = html.split('id="link-graph-panel"', 1)[1].split('</section>', 1)[0]
    assert 'id="link-graph-dead-end"' in panel and "Show nodes with no outgoing links" in panel
    assert 'id="link-graph-disconnected"' in panel and "Show nodes outside the connected component" in panel


def test_link_graph_has_bounded_local_visual_projection_and_localized_controls():
    english = render_dashboard("en")
    russian = render_dashboard("ru")
    for html, labels in ((english, ("Node cap", "All nodes", "Minimum authority", "Depth", "Visual projection", "renderLinkGraphVisual", "link-graph-visual")), (russian, ("Лимит узлов", "Все узлы", "Минимальная авторитетность", "Глубина", "Визуальная проекция"))):
        for label in labels:
            assert label in html
    assert 'id="link-graph-node-cap"' in english
    assert 'id="link-graph-min-authority"' in english
    assert 'id="link-graph-depth"' in english
    assert 'payload.items = (payload.items || []).filter' in english
    assert 'slice(0, 100)' in english
    assert 'payload.edges || []' in english
    assert 'while (cursor)' in english
