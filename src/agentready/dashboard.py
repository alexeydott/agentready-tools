from __future__ import annotations

import json
from html import escape

from .ai_prompts import ai_skill_catalog

_TEXT = {
    "en": {
        "title": "AgentReady Tools",
        "subtitle": "Configure and run website audits",
        "url": "Website URL",
        "content_url": "Content URL (optional)",
        "commerce_url": "Commerce URL (optional)",
        "preset": "Audit preset",
        "preset_all": "All checks",
        "preset_content": "Content site",
        "preset_api": "API / application",
        "preset_ai_search": "AI Search / GEO",
        "preset_v2": "Bounded site audit",
        "preset_seo": "SEO audit",
        "preset_mobile": "Mobile-friendliness",
        "preset_hint_label": "What the selected audit profile checks",
        "profile_all": "Complete SEO/GEO and AI-agent readiness audit: indexability, structured data, discoverability, content access, bot policies, protocols and commerce signals.",
        "profile_content": "Readiness profile for content sites: llms.txt, Markdown negotiation, content signals and agent-friendly content access.",
        "profile_api": "Readiness profile for APIs and applications: API catalogs, OAuth discovery, MCP/A2A cards and agent integration protocols.",
        "profile_ai_search": "AI Search / GEO profile: indexability, AI crawler access, structured data, dates and citation readiness.",
        "profile_v2": "Bounded crawl through the AuditService pipeline: same-origin discovery under hard caps, page/link/resource inventory, redirect chains and rule-based findings.",
        "v2_profile": "Crawl profile",
        "v2_profile_hint": "Crawl budget for the bounded audit. Quick is shallow and fast, deep discovers more pages. Server hard caps always apply.",
        "v2_profile_quick": "Quick",
        "v2_profile_standard": "Standard",
        "v2_profile_deep": "Deep",
        "v2_max_pages": "Page limit",
        "v2_max_pages_hint": "Maximum pages to fetch (1-25,000). Use 0 for a full same-origin crawl up to the server safety cap.",
        "v2_render": "Browser rendering",
        "v2_render_hint": "Render pages in a headless browser during the crawl. Slower, but captures client-rendered content.",
        "v2_max_depth": "Crawl depth",
        "v2_max_depth_hint": "0 checks the start page and its same-origin resources only; higher values follow same-origin links to that depth.",
        "v2_rows": "Rows",
        "v2_filter": "Filter",
        "v2_filter_hint": "Filter the rows already loaded into the table.",
        "v2_columns": "Columns",
        "v2_sort_status": "Status", "v2_sort_depth": "Depth", "v2_sort_title": "Title", "v2_sort_anchor": "Anchor", "v2_sort_type": "Type", "v2_sort_resource": "Resource",
        "v2_next_page": "Next page",
        "v2_save_view": "Save view",
        "v2_saved_view": "Saved view",
        "v2_delete_view": "Delete view",
        "v2_export_view": "Export view",
        "profile_seo": "Independent SEO audit with optional same-origin crawl: metadata, indexability, links, canonical URL, robots/sitemap, favicon and JSON-LD.",
        "profile_mobile": "Mobile-friendliness audit based on Google Mobile-Friendly signals: viewport, responsive CSS, fixed widths, touch targets, font readability and indexability.",
        "language": "Language",
        "advanced": "Advanced parameters",
        "timeout": "Timeout (seconds)",
        "ai_provider_timeout": "AI provider timeout (seconds)",
        "ai_provider_timeout_hint": "Maximum wait for one AI provider response. Increase it for large audit context or slower models; it does not change the website crawl timeout.",
        "ai_provider_retries": "AI provider retries",
        "ai_provider_retries_hint": "Number of additional provider attempts after a timeout or transient failure. More retries can delay the final result and consume provider quota.",
        "workers": "Workers",
        "threshold": "Level threshold",
        "recommendations": "Recommendation limit",
        "check_limit": "Audit check limit",
        "verify": "Verify Agent Skills digests",
        "debug": "Debug results",
        "advanced_hint": "These settings narrow the audit scope and control request execution.",
        "content_url_hint": "Optional page used for content-oriented checks instead of the site root.",
        "commerce_url_hint": "Optional commerce endpoint used to evaluate commerce discovery signals.",
        "timeout_hint": "Maximum seconds allowed for each network request.",
        "workers_hint": "Number of parallel readiness checks. Higher values can finish faster but create more concurrent requests.",
        "threshold_hint": "Minimum maturity ratio required to advance to the next readiness level.",
        "recommendations_hint": "Maximum number of prioritized recommendations included in the report.",
        "check_limit_hint": "Maximum number of checks evaluated in this audit (0 means all selected checks; range 0-500).",
        "verify_hint": "When enabled, validates Agent Skills digests instead of checking only their links.",
        "refresh_hint": "Reloads the localized list of checks available for the selected profile.",
        "health_hint": "Sends a lightweight request to confirm that the local audit service is responding.",
        "url_hint": "Public URL of the website to audit. The scheme is optional; https is assumed. Private and loopback addresses are rejected.",
        "language_hint": "Switches the dashboard language. Audit reports are generated in the selected language.",
        "run_hint": "Starts the audit for the selected profile and shows an HTML report with download and print actions.",
        "select_all_hint": "Enables every check applicable to the selected profile.",
        "clear_checks_hint": "Disables all checks so you can select only the ones you need.",
        "download_hint": "Saves the generated HTML report as a local file that keeps working offline.",
        "print_hint": "Prints the generated report. The language switcher and help icons are hidden in the printout.",
        "checks_hint": "List of checks included in this run. Disable any check to exclude it from the audit.",
        "debug_hint": "When enabled, the raw JSON response from the server is shown in the result panel for troubleshooting. When disabled, the panel shows only progress, reports and localized status messages.",
        "catalog_updated": "Check catalog updated.",
        "health_ok": "The local audit service is healthy.",
        "scan": "Execute",
        "seo": "Run SEO audit",
        "checks": "Refresh check catalog",
        "health": "Check service health",
        "ai_title": "SEO/GEO AI assistant",
        "ai_message": "Request",
        "ai_run": "Ask AI assistant",
        "ai_simple_ask": "Ask simply",
        "ai_retry_link": "Retry request",
        "ai_export_link": "Export chat",
        "ai_run_hint": "Generate a one-time structured AI report from the current audit.",
        "ai_chat": "Chat with AI assistant",
        "ai_send": "Send",
        "ai_chat_hint": "Send a question and continue a contextual conversation with the selected model.",
        "ai_welcome": "What would you like to improve today?",
        "ai_welcome_hint": "Ask about the current SEO/GEO audit or choose a starting point.",
        "ai_suggestion_seo": "Find the most important SEO issues",
        "ai_suggestion_geo": "How can I improve AI visibility?",
        "ai_suggestion_summary": "Summarize this audit",
        "ai_more": "More actions",
        "ai_model_chip": "Model",
        "ai_prompt_footer": "Prompt library",
        "ai_settings_footer": "AI settings",
        "ai_skills": "Skills",
        "ai_skills_selected": "Skills: none",
        "ai_context_selected": "Context: none",
        "ai_picker_hint": "Select one or more items to add them to the next AI request.",
        "ai_skills_hint": "Optional built-in instructions that shape how the model analyzes the audit.",
        "ai_mcp": "MCP context",
        "ai_mcp_hint": "Optional AgentReady MCP projections added as evidence for the model.",
        "ai_attachments": "Attach files",
        "ai_attach_hint": "JPEG/PNG images and Word, Excel, PDF or text documents can be attached or pasted from the clipboard.",
        "ai_chat_history": "Conversation",
        "ai_chat_history_hint": "The current user and assistant message history used for follow-up questions.",
        "ai_prompt_library": "Prompt library",
        "ai_prompt_apply": "Use prompt",
        "ai_prompt_edit": "Edit prompt",
        "ai_prompt_edit_hint": "Show the prompt title field so this template can be edited and saved.",
        "ai_prompt_edit_dialog": "Edit prompt",
        "ai_prompt_edit_dialog_hint": "Change the prompt title and template text before saving it to the library.",
        "ai_prompt_cancel": "Cancel",
        "ai_prompt_save": "Save prompt",
        "ai_prompt_save_as": "Save as prompt",
        "ai_prompt_title": "Prompt title",
        "ai_chat_save": "Save chat to file",
        "ai_chat_export": "Export OpenAI/DeepSeek JSON",
        "ai_retry": "Retry latest request",
        "ai_new_chat": "Start new chat",
        "ai_saved_chats": "Saved chats",
        "ai_thinking": "AI is thinking...",
        "ai_timeout": "The AI provider did not respond in time. Check the provider or try again.",
        "ai_report_title": "AI audit report",
        "ai_open_full_report": "Show full audit report",
        "ai_open_full_report_inline": "Show full report here",
        "ai_open_full_report_hint": "The complete AI audit report will open in a new window.",
        "ai_summary": "Summary",
        "ai_actions": "Prioritized recommendations",
        "ai_evidence": "Audit evidence",
        "ai_cautions": "Cautions",
        "ai_disclaimer": "Disclaimer",
        "ai_summary_hint": "AI-generated summary based on the selected audit evidence.",
        "ai_actions_hint": "Prioritized actions suggested by the AI assistant.",
        "ai_evidence_hint": "Audit checks and evidence used to support the recommendations.",
        "ai_cautions_hint": "Limitations or warnings returned by the AI assistant.",
        "ai_disclaimer_hint": "Advisory text explaining that AI output should be reviewed before use.",
        "ai_priority_high": "high",
        "ai_priority_medium": "medium",
        "ai_priority_low": "low",
        "ai_status_pass": "pass",
        "ai_status_warn": "warning",
        "ai_status_fail": "fail",
        "ai_status_error": "error",
        "ai_target": "Target",
        "ai_mode_both": "SEO + GEO",
        "ai_mode_seo": "SEO",
        "ai_mode_geo": "GEO",
        "ai_checks": "Checks",
        "ai_error_code": "Error code",
        "ai_json": "JSON details",
        "ai_priority": "Priority",
        "ai_verification": "Verification",
        "ai_usage": "Token usage and cost",
        "ai_session_usage": "AI session total",
        "ai_input_tokens": "Input tokens",
        "ai_output_tokens": "Output tokens",
        "ai_total_tokens": "Total tokens",
        "ai_input_cost": "Input cost",
        "ai_output_cost": "Output cost",
        "ai_total_cost": "Total cost",
        "ai_response_language": "Response language: English. The assistant must answer in this language.",
        "ai_no_actions": "No recommendations were returned.",
        "ai_no_evidence": "No matching audit evidence was returned.",
        "ai_download": "Download AI report",
        "ai_print": "Print AI report",
        "ai_generated": "Generated: agent-ready-tools",
        "ai_generated_with_model": "using",
        "ai_model_unknown": "configured model",
        "ai_mode": "Optimization mode",
        "ai_mode_both_hint": "AI reviews SEO and GEO findings together and returns a combined prioritized action plan.",
        "ai_mode_seo_hint": "AI reviews SEO findings: metadata, indexability, canonical URLs, structured data, and related checks.",
        "ai_mode_geo_hint": "AI reviews GEO findings: AI crawler access, citation readiness, structured data, and content discoverability.",
        "ai_request_hint": "AI receives the selected audit evidence and your optional message. It does not access the website directly and does not make changes.",
        "ai_model": "Model",
        "model_chat": "chat",
        "model_embedding": "embedding",
        "model_rerank": "rerank",
        "model_moderation": "moderation",
        "model_audio": "audio",
        "model_other": "other",
        "model_loading": "Loading provider models...",
        "model_error": "Unable to load provider models; using the configured model.",
        "model_refresh": "Refresh provider models",
        "model_chat_only": "Show chat-capable models only",
        "ai_hint": "Uses the deterministic audit evidence and an explicitly enabled local AI transport.",
        "ai_credentials": "AI",
        "ai_credentials_hint": "Manage named AI providers. Names and base URLs are saved in local configuration; API keys are stored in the operating system credential vault.",
        "ai_provider_url_hint": "OpenAI-compatible API base URL used for model catalog and assistant requests.",
        "ai_model_hint": "Model selected for this provider. The catalog is loaded from the provider and can be refreshed.",
        "ai_input_price": "Input price per 1M tokens",
        "ai_output_price": "Output price per 1M tokens",
        "ai_input_price_hint": "Price used to estimate input token costs for the selected model.",
        "ai_output_price_hint": "Price used to estimate output token costs for the selected model.",
        "model_chat_only_hint": "When enabled, hide embedding, rerank, audio, and other non-chat models from selectors.",
        "ai_enable_hint": "Enables the assistant and its loopback-only HTTP transport for the dashboard, CLI, and MCP.",
        "ai_provider": "Provider",
        "ai_provider_name": "Provider name",
        "ai_provider_name_hint": "A local name used to identify this AI provider configuration.",
        "ai_provider_url": "Base URL",
        "ai_new": "New provider",
        "ai_enable": "Enable AI assistant and local transport",
        "ai_key": "API key",
        "ai_key_hint": "Optional API key stored in the operating system credential vault; it is never shown in reports.",
        "ai_save": "Save provider",
        "ai_activate": "Use selected provider",
        "ai_clear": "Remove provider",
        "ai_close": "Close",
        "ai_saved": "AI provider saved. The API key is stored in the OS credential vault.",
        "ai_cleared": "AI provider removed.",
        "ai_active": "Active AI provider changed.",
        "readiness_desc": "Discoverability, content access, bot policies, APIs, authentication, MCP and commerce protocols.",
        "seo_desc": "Google and Yandex technical SEO signals: metadata, indexability, canonical URLs and structured data.",
        "checks_desc": "Every available check with its purpose, category, preset coverage and configuration state.",
        "health_desc": "Confirm that the local FastAPI service is ready to accept audit requests.",
        "select_checks": "Checks included in this run",
        "all_checks": "Select all applicable",
        "clear_checks": "Clear selection",
        "download_report": "Download report",
        "print_report": "Print report",
        "result": "Operation result",
        "ready": "Configure an audit and choose an operation.",
        "tools": "Tools",
        "tools_hint": "Open the bounded offline and stored-run tools: robots simulation, sitemap reconciliation, custom rules, link graph, duplicate clusters, and project history.",
        "v2_inventory": "Run inventory",
        "robots_simulation": "Virtual Robots simulation",
        "robots_simulation_hint": "Compare the stored robots policy with a proposed policy for selected user agents. This is an offline simulation and does not publish robots.txt.",
        "robots_live": "Current robots.txt",
        "robots_proposed": "Proposed robots.txt",
        "robots_user_agents": "User agents (comma-separated)",
        "robots_simulate": "Simulate policy",
        "robots_empty": "Run an audit before simulating robots policy.",
        "robots_result": "Robots simulation result",
        "robots_live_hint": "robots.txt discovered during this audit is used as the comparison baseline; if none was found, you can enter a policy manually.", "robots_live_loaded": "Current robots.txt loaded from this audit session.", "robots_live_discovered_hint": "Read-only policy discovered during the current audit session.", "robots_proposed_hint": "Candidate robots.txt content to compare offline against the stored policy.", "robots_user_agents_hint": "Comma-separated user-agent names to evaluate in the simulation.",
        "robots_change": "Change", "robots_url": "URL", "robots_no_changes": "No URL changes", "robots_newly_blocked": "Newly blocked", "robots_newly_allowed": "Newly allowed",
        "v2_discovery": "Discovery source",
        "v2_discovery_hint": "Choose how the bounded v2 audit discovers URLs. All discovered pages follows same-origin links up to the page/depth safety caps; set Page limit to 0 to use the server hard cap.",
        "v2_discovery_single": "Single URL",
        "v2_discovery_list": "URL list",
        "v2_discovery_sitemap": "Sitemap XML",
        "v2_discovery_robots": "Robots sitemap",
        "v2_discovery_crawl": "All discovered pages (bounded)",
        "v2_full_discovered": "Audit the full discovered set (up to server cap)",
        "v2_full_discovered_hint": "Runs until the same-origin discovered frontier is exhausted or the server hard cap of 25,000 pages is reached. When enabled, the depth field is ignored and the server depth cap is used.",
        "v2_inventory_hint": "Browse bounded server-side inventory for the latest crawl.",
        "v2_inventory_kind_hint": "Select the inventory projection to inspect for the latest completed run.",
        "v2_rows_hint": "Maximum rows shown in one inventory page.",
        "v2_inventory_sort_hint": "Sort the current inventory projection by a stable field.",
        "v2_inventory_desc_hint": "Reverse the selected inventory sort order.",
        "v2_columns_hint": "Choose which inventory columns are visible in the table.",
        "v2_saved_view_hint": "Select a previously saved bounded inventory view.",
        "sitemap_reconciliation": "Sitemap reconciliation",
        "sitemap_reconciliation_hint": "Compare bounded sitemap XML with the stored run inventory. No sitemap is fetched or submitted by this control.",
        "sitemap_origin": "Origin",
        "sitemap_origin_hint": "Origin used to resolve and classify sitemap URLs against the stored run.", "sitemap_documents_hint": "Bounded sitemap XML documents to compare; separate multiple documents with a blank line.",
        "sitemap_documents": "Sitemap XML (one or more documents separated by a blank line)",
        "sitemap_reconcile": "Reconcile sitemap",
        "run_audit_first": "Run an audit first", "sitemap_reconcile_complete": "Reconciliation complete", "sitemap_reconcile_failed": "Reconciliation failed",
        "custom_rules": "Custom rules debugger",
        "custom_rules_hint": "Validate a declarative rules document, then preview matches against the saved audit representation. These actions do not start a crawl.",
        "custom_rules_help": "Use version 1 YAML with a stable rule id and an assertion. Validate catches schema errors; Preview matches evaluates the rule against saved evidence.",
        "custom_rules_document": "Rules YAML",
        "custom_rules_document_hint": "YAML rules document validated and previewed against the saved audit representation.",
        "custom_rules_validate": "Validate rules",
        "custom_rules_preview": "Preview matches",
        "custom_rules_valid": "Rules are valid", "custom_rules_validation_failed": "Validation failed", "custom_rules_preview_complete": "Preview complete; no crawl started", "custom_rules_preview_failed": "Preview failed",
        "link_graph": "Link Graph",
        "link_graph_hint": "Load a bounded graph projection from stored link occurrences. Filters affect only the displayed page and do not start a crawl.",
        "graph_dead_ends": "Dead ends", "graph_dead_ends_hint": "Show nodes with no outgoing links in the bounded graph projection.", "graph_disconnected": "Disconnected", "graph_disconnected_hint": "Show nodes outside the connected component of the selected graph projection.", "graph_load": "Load graph", "graph_algorithm": "Authority algorithm", "graph_url": "URL", "graph_in": "In", "graph_out": "Out", "graph_authority": "Authority", "graph_loaded": "Loaded {loaded} of {total} nodes", "graph_failed": "Graph failed", "graph_node_inbound": "inbound", "graph_node_outbound": "outbound", "graph_node_cap": "Node cap", "graph_node_cap_hint": "Maximum number of nodes requested and rendered; larger graphs stay bounded.", "graph_min_authority": "Minimum authority", "graph_min_authority_hint": "Display only nodes at or above this normalized authority score.", "graph_depth": "Depth", "graph_depth_hint": "Filter the stored graph projection by crawl depth.", "graph_depth_all": "All depths", "graph_depth_root": "Root (0)", "graph_depth_1": "Depth 1", "graph_depth_2": "Depth 2", "graph_depth_3_plus": "Depth 3+", "graph_visual": "Visual projection", "graph_visual_hint": "A bounded offline projection of stored graph nodes. Node size represents authority; colors distinguish dead ends and disconnected pages.", "graph_no_edges": "No stored edges are available for the visual projection.",
        "duplicate_clusters": "Duplicate clusters",
        "duplicate_clusters_hint": "Compare exact and near-duplicate content signatures from the stored run. Loading results does not start a new crawl.",
        "duplicate_all": "All", "duplicate_exact": "Exact", "duplicate_near": "Near", "duplicate_kind_hint": "Filter clusters by exact or near-duplicate similarity.", "duplicate_load": "Load clusters", "duplicates_loaded": "Loaded {loaded} of {total} clusters", "duplicate_failed": "Duplicate query failed",
        "graph_all_nodes": "All nodes",
        "projects": "Projects and run history",
        "projects_hint": "Create or update a local project and review its stored audit runs. No remote project service is contacted.",
        "project_id_hint": "Stable local identifier used to find this project and its audit history.", "project_name_hint": "Display name shown with the local project and its run history.",
        "project_id": "Project ID",
        "project_name": "Project name",
        "project_save": "Create/update project",
        "project_load_history": "Load history",
        "history_run": "Audit run",
        "history_trigger": "Started by",
        "history_baseline": "Baseline",
        "history_baseline_yes": "Yes",
        "history_baseline_no": "No",
        "projects_count": "Projects: {count}",
        "project_saved": "Project saved", "project_failed": "Project failed", "history_failed": "History failed", "project_default_name": "Default project", "custom_rules_example_title": "Example text",
        "runs_count": "Audit runs: {count}",
        "history_explanation": "Started by shows what created each audit; Baseline marks the run used for comparison.",
        "v2_inventory_load": "Load inventory",
        "v2_inventory_empty": "Run the bounded audit to load inventory.",
        "v2_kind_pages": "Pages", "v2_kind_links": "Links", "v2_kind_resources": "Resources", "v2_kind_redirects": "Redirects", "v2_kind_findings": "Findings", "v2_kind_metrics": "Metrics",
        "v2_inventory_error": "Unable to load inventory",
        "v2_inventory_loading": "Loading this page…",
        "v2_inventory_page": "Page loaded: {count} rows",
        "v2_inventory_kind": "Inventory section", "v2_inventory_sort": "Sort", "v2_inventory_desc": "Descending",
        "v2_inventory_compare": "Compare", "v2_inventory_rescan": "Rescan selected", "v2_inventory_job": "Run as job", "v2_inventory_cancel": "Cancel job",
        "loading": "Loading...",
        "progress_title": "Audit in progress",
        "progress_start": "Preparing audit request",
        "progress_fetch": "Running website checks",
        "progress_render": "Rendering HTML report",
        "progress_crawl": "Crawl: {fetched} fetched / {discovered} discovered",
        "progress_crawl_phase": "Audit stage: {phase}",
        "progress_done": "Audit complete",
        "task_status": "Task status", "task_status_hint": "Open the local task monitor to see running, completed, failed, and cancelled audits.", "task_status_empty": "No audit tasks have been submitted.", "task_status_refresh": "Refresh", "task_status_close": "Close", "task_status_cancel": "Cancel", "task_status_age": "age", "task_status_stale": "no progress for {seconds}s",
        "failed": "Audit failed",
        "no_url": "Enter a website URL first.",
        "catalog_error": "Unable to load the check catalog.",
        "category": "Category",
        "description": "Purpose",
        "scored": "Scored",
        "optional": "Optional",
        "experimental": "Experimental",
        "help": "Help",
        "help_hide": "Hide help",
        "help_title": "Dashboard help",
        "skip_to_content": "Skip to main content",
        "noscript_title": "JavaScript is disabled",
        "noscript_text": "Use the CLI or local API instead: agentready audit https://example.com --format html, or POST an audit request to /v2/audit/dashboard.",
    },
    "ru": {
        "title": "AgentReady Tools",
        "subtitle": "Настройка и запуск аудита сайта",
        "url": "URL сайта",
        "content_url": "URL контентной страницы (необязательно)",
        "commerce_url": "URL commerce-ресурса (необязательно)",
        "preset": "Профиль аудита",
        "preset_all": "Все проверки",
        "preset_content": "Контентный сайт",
        "preset_api": "API / приложение",
        "preset_ai_search": "AI-поиск / GEO",
        "preset_v2": "Ограниченный аудит сайта",
        "preset_seo": "SEO-аудит",
        "preset_mobile": "Мобильная дружественность",
        "preset_hint_label": "Что проверяет выбранный профиль аудита",
        "profile_all": "Полный аудит SEO/GEO и готовности к ИИ-агентам: индексируемость, структурированные данные, обнаружимость, доступ к контенту, правила ботов, протоколы и commerce-сигналы.",
        "profile_content": "Профиль для контентных сайтов: llms.txt, Markdown-negotiation, content-сигналы и удобный для агентов доступ к контенту.",
        "profile_api": "Профиль для API и приложений: каталоги API, OAuth discovery, карточки MCP/A2A и протоколы интеграции агентов.",
        "profile_ai_search": "Профиль AI-поиска / GEO: индексируемость, доступ ИИ-краулеров, структурированные данные, даты и цитируемость.",
        "profile_v2": "Ограниченный обход через конвейер AuditService: обнаружение в пределах одного источника с жёсткими лимитами, инвентарь страниц/ссылок/ресурсов, цепочки редиректов и находки по правилам.",
        "v2_profile": "Профиль обхода",
        "v2_profile_hint": "Бюджет обхода для ограниченного аудита. Quick — быстрый и поверхностный, deep обнаруживает больше страниц. Жёсткие лимиты сервера действуют всегда.",
        "v2_profile_quick": "Быстрый",
        "v2_profile_standard": "Стандартный",
        "v2_profile_deep": "Глубокий",
        "v2_max_pages": "Лимит страниц",
        "v2_max_pages_hint": "Максимальное число страниц (1–25 000). 0 — полный обход в пределах безопасного серверного лимита.",
        "v2_render": "Браузерный рендеринг",
        "v2_render_hint": "Рендерить страницы в headless-браузере во время обхода. Медленнее, но захватывает контент, отрисованный на клиенте.",
        "v2_max_depth": "Глубина обхода",
        "v2_max_depth_hint": "0 — проверка стартовой страницы и её ресурсов в пределах сайта; большее значение разрешает переходы по ссылкам на эту глубину.",
        "v2_rows": "Строки",
        "v2_filter": "Фильтр",
        "v2_filter_hint": "Фильтрует уже загруженные строки таблицы.",
        "v2_columns": "Столбцы",
        "v2_sort_status": "Статус", "v2_sort_depth": "Глубина", "v2_sort_title": "Заголовок", "v2_sort_anchor": "Анкор", "v2_sort_type": "Тип", "v2_sort_resource": "Ресурс",
        "v2_next_page": "Следующая страница",
        "v2_save_view": "Сохранить представление",
        "v2_saved_view": "Сохранённое представление",
        "v2_delete_view": "Удалить представление",
        "v2_export_view": "Экспортировать представление",
        "profile_seo": "Независимый SEO-аудит с дополнительным обходом сайта: метаданные, индексируемость, ссылки, canonical URL, robots/sitemap, favicon и JSON-LD.",
        "profile_mobile": "Аудит мобильной дружественности по сигналам Google Mobile-Friendly: viewport, адаптивный CSS, фиксированная ширина, мишени касания, читаемость шрифта и индексируемость.",
        "language": "Язык",
        "advanced": "Дополнительные параметры",
        "timeout": "Таймаут (секунды)",
        "ai_provider_timeout": "Таймаут AI-провайдера (секунды)",
        "ai_provider_timeout_hint": "Максимальное ожидание одного ответа AI-провайдера. Увеличьте значение для больших контекстов аудита или медленных моделей; таймаут обхода сайта оно не меняет.",
        "ai_provider_retries": "Повторные попытки AI-провайдера",
        "ai_provider_retries_hint": "Число дополнительных попыток после таймаута или временной ошибки. Большие значения увеличивают ожидание и расход квоты провайдера.",
        "workers": "Параллельные задачи",
        "threshold": "Порог уровня",
        "recommendations": "Лимит рекомендаций",
        "check_limit": "Ограничение аудита — проверки",
        "verify": "Проверять digest Agent Skills",
        "debug": "Отладка результатов",
        "advanced_hint": "Эти параметры ограничивают область аудита и управляют выполнением запросов.",
        "content_url_hint": "Необязательная страница для контентных проверок вместо корня сайта.",
        "commerce_url_hint": "Необязательный commerce-ресурс для проверки сигналов обнаружения коммерции.",
        "timeout_hint": "Максимальное время в секундах для каждого сетевого запроса.",
        "workers_hint": "Количество параллельных readiness-проверок. Большее значение ускоряет работу, но увеличивает число одновременных запросов.",
        "threshold_hint": "Минимальная доля выполненных требований для перехода на следующий уровень готовности.",
        "recommendations_hint": "Максимальное число приоритетных рекомендаций в отчёте.",
        "check_limit_hint": "Максимальное число проверок в этом аудите (0 — все выбранные проверки; диапазон 0–500).",
        "verify_hint": "При включении проверяются digest Agent Skills, а не только ссылки на них.",
        "refresh_hint": "Заново загружает локализованный список проверок выбранного профиля.",
        "health_hint": "Выполняет лёгкий запрос и подтверждает, что локальный сервис аудита отвечает.",
        "url_hint": "Публичный URL сайта для аудита. Схему можно не указывать — по умолчанию используется https. Приватные и loopback-адреса отклоняются.",
        "language_hint": "Переключает язык интерфейса дашборда. Отчёты аудита формируются на выбранном языке.",
        "run_hint": "Запускает аудит выбранного профиля и показывает HTML-отчёт с возможностью скачивания и печати.",
        "select_all_hint": "Включает все проверки, применимые к выбранному профилю.",
        "clear_checks_hint": "Отключает все проверки, чтобы вы могли выбрать только нужные.",
        "download_hint": "Сохраняет сформированный HTML-отчёт в локальный файл, который продолжает работать офлайн.",
        "print_hint": "Отправляет сформированный отчёт на печать. Переключатель языка и значки подсказок в распечатке скрываются.",
        "checks_hint": "Список проверок, включённых в запуск. Снимите отметку, чтобы исключить проверку из аудита.",
        "debug_hint": "При включении в панели результата показывается сырой JSON-ответ сервера для диагностики. Без флага панель показывает только прогресс, отчёты и локализованные статусы.",
        "catalog_updated": "Каталог проверок обновлён.",
        "health_ok": "Локальный сервис аудита работает.",
        "scan": "Запустить",
        "seo": "Запустить SEO-аудит",
        "checks": "Обновить каталог проверок",
        "health": "Проверить состояние сервиса",
        "ai_title": "AI-помощник SEO/GEO",
        "ai_message": "Запрос",
        "ai_run": "Спросить AI-помощника",
        "ai_simple_ask": "Просто спросить",
        "ai_retry_link": "Повторить запрос",
        "ai_export_link": "Экспорт чата",
        "ai_run_hint": "Сформировать разовый структурированный AI-отчёт по текущему аудиту.",
        "ai_chat": "Открыть чат с AI-помощником",
        "ai_send": "Отправить",
        "ai_chat_hint": "Отправить вопрос и продолжить контекстный диалог с выбранной моделью.",
        "ai_welcome": "Что улучшим сегодня?",
        "ai_welcome_hint": "Спросите о текущем SEO/GEO-аудите или выберите вариант для начала.",
        "ai_suggestion_seo": "Найди самые важные проблемы SEO",
        "ai_suggestion_geo": "Как улучшить видимость в AI-поиске?",
        "ai_suggestion_summary": "Сделай краткое резюме аудита",
        "ai_more": "Другие действия",
        "ai_model_chip": "Модель",
        "ai_prompt_footer": "Библиотека промтов",
        "ai_settings_footer": "Настройки AI",
        "ai_skills": "Навыки",
        "ai_skills_selected": "Навыки: нет",
        "ai_context_selected": "Контекст: нет",
        "ai_picker_hint": "Выберите один или несколько элементов для добавления в следующий запрос AI.",
        "ai_skills_hint": "Необязательные встроенные инструкции, определяющие анализ аудита моделью.",
        "ai_mcp": "Контекст MCP",
        "ai_mcp_hint": "Необязательные проекции AgentReady MCP, добавляемые в доказательства для модели.",
        "ai_attachments": "Прикрепить файлы",
        "ai_attach_hint": "Можно прикреплять или вставлять из буфера обмена изображения JPEG/PNG и документы Word, Excel, PDF или текстовые файлы.",
        "ai_chat_history": "Диалог",
        "ai_chat_history_hint": "Текущая история сообщений пользователя и помощника для продолжения вопросов.",
        "ai_prompt_library": "Библиотека промтов",
        "ai_prompt_apply": "Использовать промт",
        "ai_prompt_edit": "Изменить промт",
        "ai_prompt_edit_hint": "Показать поле названия промта для редактирования и сохранения шаблона.",
        "ai_prompt_edit_dialog": "Изменить промт",
        "ai_prompt_edit_dialog_hint": "Измените название и текст шаблона перед сохранением в библиотеку.",
        "ai_prompt_cancel": "Отмена",
        "ai_prompt_save": "Сохранить промт",
        "ai_prompt_save_as": "Сохранить как промт",
        "ai_prompt_title": "Название промта",
        "ai_chat_save": "Сохранить чат в файл",
        "ai_chat_export": "Экспорт JSON для OpenAI/DeepSeek",
        "ai_retry": "Повторить последний запрос",
        "ai_new_chat": "Начать новый диалог",
        "ai_saved_chats": "Сохранённые чаты",
        "ai_thinking": "AI-помощник обрабатывает запрос...",
        "ai_timeout": "AI-провайдер не ответил вовремя. Проверьте провайдера или повторите запрос.",
        "ai_report_title": "Отчёт AI-аудита",
        "ai_open_full_report": "Показать полный отчёт аудита",
        "ai_open_full_report_inline": "Показать полный отчёт здесь",
        "ai_open_full_report_hint": "Полный отчёт AI-аудита откроется в новом окне.",
        "ai_summary": "Итог",
        "ai_actions": "Приоритетные рекомендации",
        "ai_evidence": "Данные аудита",
        "ai_cautions": "Предупреждения",
        "ai_disclaimer": "Отказ от ответственности",
        "ai_summary_hint": "Итог, сформированный AI на основе выбранных данных аудита.",
        "ai_actions_hint": "Приоритетные действия, предложенные AI-помощником.",
        "ai_evidence_hint": "Проверки и данные аудита, на которых основаны рекомендации.",
        "ai_cautions_hint": "Ограничения или предупреждения, возвращённые AI-помощником.",
        "ai_disclaimer_hint": "Пояснение о необходимости проверить результат AI перед использованием.",
        "ai_priority_high": "высокий",
        "ai_priority_medium": "средний",
        "ai_priority_low": "низкий",
        "ai_status_pass": "пройдено",
        "ai_status_warn": "предупреждение",
        "ai_status_fail": "ошибка",
        "ai_status_error": "ошибка",
        "ai_target": "Цель",
        "ai_mode_both": "SEO + GEO",
        "ai_mode_seo": "SEO",
        "ai_mode_geo": "GEO",
        "ai_checks": "Проверки",
        "ai_error_code": "Код ошибки",
        "ai_json": "Детали JSON",
        "ai_priority": "Приоритет",
        "ai_verification": "Проверка",
        "ai_usage": "Расход токенов и стоимость",
        "ai_session_usage": "Итого за сессию AI",
        "ai_input_tokens": "Входные токены",
        "ai_output_tokens": "Выходные токены",
        "ai_total_tokens": "Всего токенов",
        "ai_input_cost": "Стоимость ввода",
        "ai_output_cost": "Стоимость вывода",
        "ai_total_cost": "Общая стоимость",
        "ai_response_language": "Язык ответа: русский. Помощник должен отвечать на этом языке.",
        "ai_no_actions": "Рекомендации не получены.",
        "ai_no_evidence": "Связанные данные аудита не получены.",
        "ai_download": "Скачать AI-отчёт",
        "ai_print": "Распечатать AI-отчёт",
        "ai_generated": "Сгенерировано: agent-ready-tools",
        "ai_generated_with_model": "при помощи",
        "ai_model_unknown": "настроенной модели",
        "ai_mode": "Режим оптимизации",
        "ai_mode_both_hint": "AI анализирует результаты SEO и GEO вместе и возвращает общий приоритетный план действий.",
        "ai_mode_seo_hint": "AI анализирует SEO-результаты: метаданные, индексируемость, canonical URL, структурированные данные и связанные проверки.",
        "ai_mode_geo_hint": "AI анализирует GEO-результаты: доступ AI-краулеров, цитируемость, структурированные данные и обнаруживаемость контента.",
        "ai_request_hint": "AI получает выбранные данные аудита и ваш необязательный запрос. Он не обращается к сайту напрямую и не вносит изменения.",
        "ai_model": "Модель",
        "model_chat": "чат",
        "model_embedding": "embedding",
        "model_rerank": "rerank",
        "model_moderation": "moderation",
        "model_audio": "audio",
        "model_other": "другое",
        "model_loading": "Загрузка моделей провайдера...",
        "model_error": "Не удалось загрузить модели провайдера; используется настроенная модель.",
        "model_refresh": "Обновить модели провайдера",
        "model_chat_only": "Показывать только chat-модели",
        "ai_hint": "Использует детерминированные данные аудита и явно включённый локальный AI-транспорт.",
        "ai_credentials": "AI",
        "ai_credentials_hint": "Управляйте именованными AI-провайдерами. Имена и base URL сохраняются в локальной конфигурации, API key — в системном хранилище учётных данных.",
        "ai_provider_url_hint": "Base URL OpenAI-compatible API для загрузки каталога моделей и запросов помощника.",
        "ai_model_hint": "Модель, выбранная для этого провайдера. Каталог загружается у провайдера и обновляется кнопкой.",
        "ai_input_price": "Цена ввода за 1 млн токенов",
        "ai_output_price": "Цена вывода за 1 млн токенов",
        "ai_input_price_hint": "Цена для расчёта стоимости входных токенов выбранной модели.",
        "ai_output_price_hint": "Цена для расчёта стоимости выходных токенов выбранной модели.",
        "model_chat_only_hint": "Скрывает в списках embedding-, rerank-, audio- и другие модели, не предназначенные для чата.",
        "ai_enable_hint": "Включает помощника и loopback-only HTTP-транспорт для dashboard, CLI и MCP.",
        "ai_provider": "Провайдер",
        "ai_provider_name": "Имя провайдера",
        "ai_provider_name_hint": "Локальное имя для идентификации этой конфигурации AI-провайдера.",
        "ai_provider_url": "Base URL",
        "ai_new": "Новый провайдер",
        "ai_enable": "Включить AI-помощника и локальный транспорт",
        "ai_key": "API key",
        "ai_key_hint": "Необязательный API key хранится в системном хранилище учётных данных и не показывается в отчётах.",
        "ai_save": "Сохранить провайдера",
        "ai_activate": "Использовать выбранного провайдера",
        "ai_clear": "Удалить провайдера",
        "ai_close": "Закрыть",
        "ai_saved": "AI-провайдер сохранён. API key хранится в системном хранилище учётных данных.",
        "ai_cleared": "AI-провайдер удалён.",
        "ai_active": "Активный AI-провайдер изменён.",
        "readiness_desc": "Обнаруживаемость, доступность контента, правила ботов, API, аутентификация, MCP и commerce-протоколы.",
        "seo_desc": "Технические SEO-сигналы Google и Яндекса: метаданные, индексация, canonical URL и структурированные данные.",
        "checks_desc": "Все доступные проверки с назначением, категорией, профилями и текущими настройками.",
        "health_desc": "Проверить готовность локального FastAPI-сервиса принимать запросы аудита.",
        "select_checks": "Проверки, включённые в запуск",
        "all_checks": "Выбрать все применимые",
        "clear_checks": "Снять выбор",
        "download_report": "Скачать отчёт",
        "print_report": "Распечатать отчёт",
        "result": "Результат операции",
        "ready": "Настройте аудит и выберите операцию.",
        "tools": "Инструменты",
        "tools_hint": "Откройте ограниченные офлайн-инструменты и инструменты сохранённых запусков: robots, sitemap, пользовательские правила, граф ссылок, дубликаты и историю проектов.",
        "v2_inventory": "Инвентарь запуска",
        "robots_simulation": "Симуляция Virtual Robots",
        "robots_simulation_hint": "Сравнивает сохранённую и предлагаемую политику robots для выбранных user-agent. Это офлайн-симуляция, robots.txt не публикуется.",
        "robots_live": "Текущий robots.txt",
        "robots_proposed": "Предлагаемый robots.txt",
        "robots_user_agents": "User-agent (через запятую)",
        "robots_simulate": "Симулировать политику",
        "robots_empty": "Сначала выполните аудит, затем симулируйте robots-политику.",
        "robots_result": "Результат симуляции robots",
        "robots_live_hint": "robots.txt, найденный в текущем аудите, используется как основа сравнения; если файл не найден, политику можно ввести вручную.", "robots_live_loaded": "Текущий robots.txt загружен из этой сессии аудита.", "robots_live_discovered_hint": "Политика найдена в текущей сессии аудита и доступна только для чтения.", "robots_proposed_hint": "Предлагаемое содержимое robots.txt для офлайн-сравнения с сохранённой политикой.", "robots_user_agents_hint": "Имена user-agent через запятую для проверки в симуляции.",
        "robots_change": "Изменение", "robots_url": "URL", "robots_no_changes": "Изменений URL нет", "robots_newly_blocked": "Новые блокировки", "robots_newly_allowed": "Новые разрешения",
        "v2_discovery": "Источник обнаружения",
        "v2_discovery_hint": "Выберите способ обнаружения URL для ограниченного v2-аудита. «Все обнаруженные страницы» следует по ссылкам в пределах сайта до безопасных лимитов страниц и глубины; установите лимит страниц 0 для жёсткого серверного лимита.",
        "v2_discovery_single": "Один URL",
        "v2_discovery_list": "Список URL",
        "v2_discovery_sitemap": "XML sitemap",
        "v2_discovery_robots": "Sitemap из robots",
        "v2_discovery_crawl": "Все обнаруженные страницы (с ограничениями)",
        "v2_full_discovered": "Проверить полный набор обнаруженных страниц (до лимита сервера)",
        "v2_full_discovered_hint": "Выполняет обход до исчерпания очереди обнаруженных страниц или жёсткого серверного лимита 25 000 страниц. При включении поле глубины игнорируется и используется серверный предел глубины.",
        "v2_inventory_hint": "Просмотр ограниченного серверного инвентаря последнего обхода.",
        "v2_inventory_kind_hint": "Выберите проекцию инвентаря для просмотра в последнем завершённом запуске.",
        "v2_rows_hint": "Максимальное число строк на одной странице инвентаря.",
        "v2_inventory_sort_hint": "Сортирует текущую проекцию инвентаря по стабильному полю.",
        "v2_inventory_desc_hint": "Разворачивает порядок выбранной сортировки инвентаря.",
        "v2_columns_hint": "Выберите видимые столбцы таблицы инвентаря.",
        "v2_saved_view_hint": "Выберите ранее сохранённое ограниченное представление инвентаря.",
        "sitemap_reconciliation": "Сверка sitemap",
        "sitemap_reconciliation_hint": "Сравнивает ограниченные XML-документы sitemap с сохранённым инвентарём запуска. Этот элемент ничего не загружает и не публикует.",
        "sitemap_origin": "Источник",
        "sitemap_origin_hint": "Источник для разрешения и классификации URL sitemap относительно сохранённого запуска.", "sitemap_documents_hint": "Ограниченные XML-документы sitemap для сравнения; несколько документов разделяйте пустой строкой.",
        "sitemap_documents": "XML sitemap (несколько документов разделяйте пустой строкой)",
        "sitemap_reconcile": "Сверить sitemap",
        "run_audit_first": "Сначала выполните аудит", "sitemap_reconcile_complete": "Сверка завершена", "sitemap_reconcile_failed": "Ошибка сверки",
        "custom_rules": "Отладчик пользовательских правил",
        "custom_rules_hint": "Проверяет декларативный документ правил и показывает совпадения с сохранённым представлением аудита. Эти действия не запускают обход.",
        "custom_rules_help": "Используйте YAML версии 1 со стабильным идентификатором правила и утверждением. Проверка находит ошибки схемы, а предпросмотр оценивает правило по сохранённым доказательствам.",
        "custom_rules_document": "YAML правил",
        "custom_rules_document_hint": "Документ правил YAML для проверки и предпросмотра по сохранённому представлению аудита.",
        "custom_rules_validate": "Проверить правила",
        "custom_rules_preview": "Предпросмотр совпадений",
        "custom_rules_valid": "Правила корректны", "custom_rules_validation_failed": "Ошибка проверки", "custom_rules_preview_complete": "Предпросмотр завершён; обход не запускался", "custom_rules_preview_failed": "Ошибка предпросмотра",
        "link_graph": "Граф ссылок",
        "link_graph_hint": "Загружает ограниченную проекцию графа по сохранённым вхождениям ссылок. Фильтры влияют только на экран и не запускают обход.",
        "graph_dead_ends": "Тупиковые страницы", "graph_dead_ends_hint": "Показывает узлы без исходящих ссылок в ограниченной проекции графа.", "graph_disconnected": "Изолированные страницы", "graph_disconnected_hint": "Показывает узлы вне связной компоненты выбранной проекции графа.", "graph_load": "Загрузить граф", "graph_algorithm": "Алгоритм авторитетности", "graph_url": "URL", "graph_in": "Входящие", "graph_out": "Исходящие", "graph_authority": "Авторитетность", "graph_loaded": "Загружено узлов: {loaded} из {total}", "graph_failed": "Ошибка графа", "graph_node_inbound": "входящих", "graph_node_outbound": "исходящих", "graph_node_cap": "Лимит узлов", "graph_node_cap_hint": "Максимальное число запрошенных и отображаемых узлов; большие графы остаются ограниченными.", "graph_min_authority": "Минимальная авторитетность", "graph_min_authority_hint": "Показывает только узлы с нормализованной авторитетностью не ниже указанной.", "graph_depth": "Глубина", "graph_depth_hint": "Фильтрует сохранённую проекцию графа по глубине обхода.", "graph_depth_all": "Все уровни", "graph_depth_root": "Корень (0)", "graph_depth_1": "Уровень 1", "graph_depth_2": "Уровень 2", "graph_depth_3_plus": "Уровень 3+", "graph_visual": "Визуальная проекция", "graph_visual_hint": "Ограниченная offline-проекция сохранённых узлов графа. Размер узла показывает авторитетность, цвет — тупиковые и изолированные страницы.", "graph_no_edges": "Сохранённые связи недоступны для визуальной проекции.",
        "duplicate_clusters": "Кластеры дубликатов",
        "duplicate_clusters_hint": "Сравнивает точные и близкие сигнатуры дубликатов сохранённого запуска. Загрузка результатов не запускает новый обход.",
        "duplicate_all": "Все", "duplicate_exact": "Точные", "duplicate_near": "Близкие", "duplicate_kind_hint": "Фильтрует кластеры по точному или близкому сходству дубликатов.", "duplicate_load": "Загрузить кластеры", "duplicates_loaded": "Загружено кластеров: {loaded} из {total}", "duplicate_failed": "Ошибка запроса дубликатов",
        "graph_all_nodes": "Все узлы",
        "projects": "Проекты и история запусков",
        "projects_hint": "Создаёт или обновляет локальный проект и показывает сохранённые запуски аудита. Внешний сервис проектов не используется.",
        "project_id_hint": "Стабильный локальный идентификатор проекта и его истории аудитов.", "project_name_hint": "Отображаемое имя локального проекта и его истории запусков.",
        "project_id": "Идентификатор проекта",
        "project_name": "Название проекта",
        "project_save": "Создать/обновить проект",
        "project_load_history": "Загрузить историю",
        "history_run": "Запуск аудита",
        "history_trigger": "Источник запуска",
        "history_baseline": "Базовый запуск",
        "history_baseline_yes": "Да",
        "history_baseline_no": "Нет",
        "projects_count": "Проектов: {count}",
        "project_saved": "Проект сохранён", "project_failed": "Ошибка проекта", "history_failed": "Ошибка истории", "project_default_name": "Проект по умолчанию", "custom_rules_example_title": "Пример текста",
        "runs_count": "Запусков аудита: {count}",
        "history_explanation": "«Источник запуска» показывает, что создало аудит; «Базовый запуск» отмечает запуск для сравнения.",
        "v2_inventory_load": "Загрузить инвентарь",
        "v2_inventory_empty": "Запустите ограниченный аудит, чтобы загрузить инвентарь.",
        "v2_kind_pages": "Страницы", "v2_kind_links": "Ссылки", "v2_kind_resources": "Ресурсы", "v2_kind_redirects": "Редиректы", "v2_kind_findings": "Проверки", "v2_kind_metrics": "Метрики",
        "v2_inventory_error": "Не удалось загрузить инвентарь",
        "v2_inventory_loading": "Загрузка страницы…",
        "v2_inventory_page": "Загружено строк: {count}",
        "v2_inventory_kind": "Раздел инвентаря", "v2_inventory_sort": "Сортировка", "v2_inventory_desc": "По убыванию",
        "v2_inventory_compare": "Сравнить", "v2_inventory_rescan": "Повторно проверить выбранные", "v2_inventory_job": "Запустить как задачу", "v2_inventory_cancel": "Отменить задачу",
        "loading": "Загрузка...",
        "progress_title": "Аудит выполняется",
        "progress_start": "Подготовка запроса аудита",
        "progress_fetch": "Выполнение проверок сайта",
        "progress_render": "Формирование HTML-отчёта",
        "progress_crawl": "Обход: загружено {fetched}, найдено {discovered}",
        "progress_crawl_phase": "Этап аудита: {phase}",
        "progress_done": "Аудит завершён",
        "task_status": "Состояние задач", "task_status_hint": "Откройте монитор локальных задач: выполняются, завершены, завершились ошибкой или отменены.", "task_status_empty": "Задачи аудита ещё не запускались.", "task_status_refresh": "Обновить", "task_status_close": "Закрыть", "task_status_cancel": "Отменить", "task_status_age": "возраст", "task_status_stale": "нет прогресса {seconds} с",
        "failed": "Аудит завершился ошибкой",
        "no_url": "Сначала укажите URL сайта.",
        "catalog_error": "Не удалось загрузить каталог проверок.",
        "category": "Категория",
        "description": "Назначение",
        "scored": "В оценке",
        "optional": "Необязательная",
        "experimental": "Экспериментальная",
        "help": "Справка",
        "help_hide": "Скрыть справку",
        "help_title": "Справка по dashboard",
        "skip_to_content": "Перейти к основному содержимому",
        "noscript_title": "JavaScript отключён",
        "noscript_text": "Используйте CLI или локальный API: agentready audit https://example.com --format html или отправьте POST-запрос аудита на /v2/audit/dashboard.",
    },
}


def _hint(text: dict[str, str], key: str) -> str:
    """Render a hover/focus help icon with a localized tooltip (report-style)."""
    value = escape(text[key])
    return f"<span class='hint' tabindex='0' role='img' aria-label='{value}' data-tooltip='{value}'>?</span>"


_FAQ = {
    "en": """
<h2>Dashboard help</h2>
<p>Use the dashboard to audit a public website without the command line.</p>
<h3>1. Start an audit</h3>
<ol><li>Enter a public website address in <strong>Website URL</strong>.</li>
<li>Choose an <strong>Audit preset</strong>.</li>
<li>Click <strong>Execute</strong> and wait for the report.</li></ol>
<h3>2. Configure checks</h3>
<p>Open <strong>Advanced parameters</strong> to set content and commerce URLs,
timeout, workers, maturity threshold, recommendation limit, and Agent Skills
digest verification. Use <strong>Refresh check catalog</strong> to reload
available checks. Open <strong>Checks included in this run</strong> to select
individual checks.</p>
<h3>3. Custom rules debugger</h3>
<p>Open <strong>Custom rules</strong> to validate a YAML rules document before
using it in an audit workflow. Use <code>version: 1</code>, a stable
<code>id</code> for every rule, a title, and an assertion. Click
<strong>Validate rules</strong> to check the structure. Click
<strong>Preview matches</strong> to evaluate the rules against the available
audit representation; preview does not start a crawl.</p>
<h3>4. Projects and run history</h3>
<p>In <strong>Projects and run history</strong>, enter a stable project ID and
display name, then click <strong>Create or update project</strong>. Click
<strong>Load run history</strong> to see recent runs. <strong>Audit run</strong>
identifies the run, <strong>Started by</strong> describes what initiated it,
and <strong>Baseline</strong> says whether it was used for comparison. An
empty history is valid and means no run is saved for that project.</p>
<h3>5. Read and save results</h3>
<p>The result shows progress, score, maturity, checks, recommendations, URLs,
pages, resources, and metrics. Use <strong>Download report</strong> or
<strong>Print report</strong> beside the report.</p>
<h3>6. Virtual Robots simulation</h3>
<p>Open <strong>Virtual Robots simulation</strong> to compare stored and
proposed robots policies for selected user agents. Paste both documents and
click <strong>Simulate</strong>. This is an offline comparison: it neither
fetches nor publishes <code>robots.txt</code>.</p>
<h3>7. Sitemap reconciliation</h3>
<p>Paste bounded sitemap XML and choose the origin used by the stored run,
then click <strong>Reconcile</strong>. The result compares sitemap entries
with the saved inventory. This control does not fetch or submit a sitemap.</p>
<h3>8. Link Graph</h3>
<p>Click <strong>Load graph</strong> to display a bounded projection of stored
link occurrences. The dead-end and disconnected filters change only the
displayed projection; they do not start a crawl.</p>
<h3>9. Duplicate clusters</h3>
<p>Open <strong>Duplicate clusters</strong> to compare exact and near-duplicate
content signatures in the stored run. Choose <strong>All</strong>,
<strong>Exact</strong>, or <strong>Near</strong>, then click
<strong>Load clusters</strong>. This reads the saved inventory and does not
start a new crawl.</p>
<h3>10. Use the AI assistant</h3>
<p>After an audit, choose SEO, GEO, or SEO/GEO mode, then select a provider and
model. Enter a request or use the prompt library. Skills, MCP context, file
attachments, chat history, saved chats, and OpenAI/DeepSeek JSON export are
available in the AI panel.</p>
<h3>11. Language and troubleshooting</h3>
<p>The interface follows the selected language. Without an explicit URL
parameter, Russian is used for a Russian browser locale and English otherwise.
For errors, check the URL, click <strong>Check service health</strong>, enable
<strong>Debug results</strong>, and review the provider URL and model.</p>
""",
    "ru": """
<h2>Справка по dashboard</h2>
<p>Используйте dashboard для аудита публичного сайта без командной строки.</p>
<h3>1. Запуск аудита</h3>
<ol><li>Введите публичный адрес в поле <strong>URL сайта</strong>.</li>
<li>Выберите <strong>Профиль аудита</strong>.</li>
<li>Нажмите <strong>Запустить</strong> и дождитесь отчёта.</li></ol>
<h3>2. Настройка проверок</h3>
<p>В разделе <strong>Дополнительные параметры</strong> можно задать URL
контентной и commerce-страницы, таймаут, число параллельных задач, порог
зрелости, лимит рекомендаций и проверку digest Agent Skills. Ссылка
<strong>Обновить каталог проверок</strong> загружает список заново. В блоке
<strong>Проверки, включённые в запуск</strong> выбираются отдельные проверки.</p>
<h3>3. Отладчик пользовательских правил</h3>
<p>Откройте блок <strong>Пользовательские правила</strong>, чтобы проверить
YAML-документ до использования в рабочем процессе аудита. Используйте
<code>version: 1</code>, стабильный <code>id</code> каждого правила, заголовок
и условие. Кнопка <strong>Проверить правила</strong> проверяет структуру.
Кнопка <strong>Предпросмотр совпадений</strong> оценивает правила по доступному
представлению аудита и не запускает обход сайта.</p>
<h3>4. Проекты и история запусков</h3>
<p>В блоке <strong>Проекты и история запусков</strong> укажите стабильный
идентификатор и название проекта, затем нажмите
<strong>Создать или обновить проект</strong>. Кнопка
<strong>Загрузить историю запусков</strong> показывает последние аудиты.
<strong>Запуск аудита</strong> идентифицирует запуск,
<strong>Источник запуска</strong> объясняет, что его создало, а
<strong>Базовый запуск</strong> показывает, использовался ли он для сравнения.
Пустая история означает, что для проекта ещё нет сохранённых запусков.</p>
<h3>5. Результаты и сохранение</h3>
<p>В результате отображаются прогресс, балл, уровень зрелости, проверки,
рекомендации, URL, страницы, ресурсы и метрики. Рядом с отчётом доступны
<strong>Скачать отчёт</strong> и <strong>Распечатать отчёт</strong>.</p>
<h3>6. Симуляция Virtual Robots</h3>
<p>Откройте <strong>Симуляция Virtual Robots</strong>, чтобы сравнить
сохранённую и предлагаемую политики robots для выбранных user-agent.
Вставьте оба документа и нажмите <strong>Симулировать</strong>. Это офлайн-
сравнение: инструмент не загружает и не публикует <code>robots.txt</code>.</p>
<h3>7. Сверка sitemap</h3>
<p>Вставьте XML sitemap и укажите origin сохранённого запуска, затем нажмите
<strong>Сверить</strong>. Результат сравнивает записи sitemap с сохранённым
инвентарём. Инструмент ничего не загружает и не отправляет на публикацию.</p>
<h3>8. Граф ссылок</h3>
<p>Нажмите <strong>Загрузить граф</strong>, чтобы показать ограниченную
проекцию сохранённых вхождений ссылок. Фильтры тупиков и disconnected меняют
только отображение и не запускают обход.</p>
<h3>9. Кластеры дубликатов</h3>
<p>Откройте <strong>Кластеры дубликатов</strong>, чтобы сравнить точные и
близкие сигнатуры содержимого сохранённого запуска. Выберите
<strong>Все</strong>, <strong>Точные</strong> или <strong>Близкие</strong>,
затем нажмите <strong>Загрузить кластеры</strong>. Используется сохранённый
инвентарь; новый обход не запускается.</p>
<h3>10. AI-помощник</h3>
<p>После аудита выберите режим SEO, GEO или SEO/GEO, затем провайдера и
модель. Напишите запрос или выберите prompt из библиотеки. В AI-панели также
доступны skills, контекст MCP, вложения, история и сохранение чатов, а также
экспорт OpenAI/DeepSeek JSON.</p>
<h3>11. Язык и диагностика</h3>
<p>Интерфейс использует выбранный язык. Если язык не указан в URL, для русской
локали браузера выбирается русский, для остальных — английский. При ошибке
проверьте URL, нажмите <strong>Проверить состояние сервиса</strong>, включите
<strong>Отладка результатов</strong> и проверьте URL провайдера и модель.</p>
""",
}


def render_dashboard(language: str = "en") -> str:
    lang = language if language in _TEXT else "en"
    text = _TEXT[lang]
    faq = _FAQ[lang]
    translations = json.dumps(_TEXT, ensure_ascii=False).replace("</", "<\\/")
    skill_options = "".join(
        f'<option value="{escape(item["id"])}" title="{escape(item["description"])}" data-label="{escape(item["title"])}">{escape(item["title"])} — {escape(item["description"])}</option>'
        for item in ai_skill_catalog(lang)
    )
    return fr"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(text["title"])}</title>
<style>
:root {{ color-scheme:light; font-family:Inter,Segoe UI,Arial,sans-serif; color:#441d0c; background:#fffaf6; }}
* {{ box-sizing:border-box; }} html,body {{ min-height:100%; }} body {{ width:100%; min-height:100vh; margin:0; padding:30px clamp(20px,3vw,48px); }}
.skip-link {{ position:absolute; left:-9999px; top:8px; z-index:30; padding:10px 14px; background:#24130d; color:#fff; border-radius:8px; }}
.skip-link:focus {{ left:8px; }}
.sr-only {{ position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }}
header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:20px; margin-bottom:24px; }}
h1 {{ margin:0 0 8px; font-size:clamp(28px,4vw,46px); }} h2 {{ margin:0 0 12px; }}
p {{ line-height:1.5; }} label {{ display:block; font-weight:600; margin-bottom:6px; }}
input,select,button {{ width:100%; min-height:44px; border:1px solid #efcdb8; border-radius:10px; padding:12px 14px; font:inherit; }}
button {{ background:#ed4308; color:white; border:0; cursor:pointer; font-weight:700; }}
button.secondary {{ background:#fff; color:#9e2f0b; border:1px solid #ed4308; }}
.panel {{ background:#fff; border:1px solid #efcdb8; border-radius:16px; padding:22px; margin-bottom:20px; box-shadow:0 4px 14px #8e3b1612; }}
.form-grid {{ display:grid; grid-template-columns:minmax(0,2fr) minmax(150px,1fr) minmax(210px,auto); gap:14px; align-items:end; }}
.model-control {{ display:flex; gap:6px; align-items:center; }} .model-control select {{ min-width:0; flex:1 1 auto; }} .model-control button {{ width:auto; flex:0 0 46px; min-width:46px; padding-left:8px; padding-right:8px; }}
.form-grid.three {{ grid-template-columns:repeat(3,minmax(0,1fr)); }} .form-grid.four {{ grid-template-columns:repeat(4,minmax(0,1fr)); }} .robots-document-field {{ display:flex; flex-direction:column; min-width:0; }} .robots-document-field textarea {{ width:100%; box-sizing:border-box; }}
details summary {{ cursor:pointer; font-weight:700; margin-bottom:16px; }} details summary h2,details summary h3 {{ display:inline; font:inherit; margin:0; }} .actions {{ display:flex; gap:10px; margin-top:16px; }}
.advanced-links {{ display:flex; flex-wrap:wrap; gap:18px; margin-top:18px; padding-top:14px; border-top:1px solid #efcdb8; }} .advanced-link-row {{ display:flex; align-items:center; gap:6px; position:relative; }}
.inventory-toolbar {{ display:grid; grid-template-columns:minmax(150px,1.2fr) repeat(4,minmax(110px,1fr)) minmax(180px,1.5fr) minmax(150px,1fr); gap:10px; align-items:end; }} .inventory-toolbar > label {{ min-width:0; }} .inventory-toolbar > select,.inventory-toolbar > input {{ min-width:0; box-sizing:border-box; }} .inventory-toolbar > button {{ width:auto; min-width:120px; }} .inventory-toolbar input[type=checkbox] {{ width:auto; min-height:20px; padding:0; }}
.text-link {{ color:#9e2f0b; font-weight:700; text-decoration:underline; cursor:pointer; }} .checks-toolbar {{ display:flex; justify-content:space-between; gap:12px; align-items:center; }}
#checks {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin-top:14px; }}
.check {{ border:1px solid #efcdb8; border-radius:10px; padding:12px; display:grid; grid-template-columns:auto 1fr; gap:10px; }}
.check input {{ width:auto; margin-top:4px; }} .check strong {{ display:inline; }} .check small {{ display:block; line-height:1.4; margin-top:4px; color:#6c554b; }}
#link-graph-panel input[type=checkbox] {{ width:auto; min-width:20px; min-height:20px; padding:0; margin:0 6px 0 0; vertical-align:middle; }} #link-graph-panel label {{ display:inline-flex; align-items:center; gap:4px; margin:0 14px 10px 0; }} .link-graph-visual {{ min-height:300px; overflow:auto; border:1px solid #d7dee7; border-radius:8px; background:#f8fafc; }} .link-graph-visual svg {{ display:block; min-width:520px; }} .link-graph-edge {{ stroke:#94a3b8; stroke-width:1; stroke-opacity:.55; }} .link-graph-node {{ cursor:pointer; outline:none; }} .link-graph-node:focus circle, .link-graph-node:hover circle {{ stroke:#111827; stroke-width:2; }}
.hint {{ position:relative; display:inline-flex; align-items:center; justify-content:center; width:21px; height:21px; min-width:21px; min-height:21px; margin-left:6px; border:1px solid #ed4308; border-radius:50%; background:#fff8f2; color:#9e2f0b; font-size:.82rem; font-weight:700; line-height:1; cursor:help; vertical-align:middle; }}
.hint:hover::after,.hint:focus::after {{ content:attr(data-tooltip); position:absolute; z-index:20; left:0; top:26px; width:min(340px,80vw); padding:10px 12px; border-radius:10px; background:#24130d; color:#ffe8d8; font-size:.85rem; font-weight:400; line-height:1.45; white-space:pre-line; text-align:left; box-shadow:0 6px 18px #0005; }}
#result {{ min-height:80px; background:#fff8f2; color:#441d0c; border:1px solid #efcdb8; border-radius:12px; padding:18px; }}
#progress {{ border:1px solid #efcdb8; border-radius:12px; padding:14px; margin-bottom:14px; background:#fff8f2; }}
#progress[hidden] {{ display:none; }} .progress-track {{ height:8px; background:#f1d8c8; border-radius:8px; overflow:hidden; margin:10px 0; }}
#progress-bar {{ display:block; height:100%; width:8%; background:#ed4308; transition:width .3s ease; }}
#task-status-dialog {{ width:min(760px,calc(100% - 32px)); border:1px solid #efcdb8; border-radius:12px; padding:20px; }} #task-status-dialog::backdrop {{ background:#1f293766; }} .task-status-list {{ display:grid; gap:8px; max-height:55vh; overflow:auto; }} .task-status-row {{ display:grid; grid-template-columns:minmax(120px,1fr) auto minmax(180px,2fr) auto; gap:10px; align-items:center; border:1px solid #efcdb8; border-radius:8px; padding:9px; }} .task-status-row small {{ color:#765b4d; }}
#ai-credentials-dialog.provider-busy {{ opacity:.72; }} #ai-credentials-dialog.provider-busy .model-control::after {{ content:""; width:14px; height:14px; border:2px solid #efcdb8; border-top-color:#ed4308; border-radius:50%; animation:provider-spin .8s linear infinite; }} @keyframes provider-spin {{ to {{ transform:rotate(360deg); }} }}
#progress-steps {{ display:flex; justify-content:space-between; gap:8px; font-size:.85rem; color:#765b4d; }}
#report-frame {{ width:100%; min-height:720px; border:0; background:#fff; border-radius:8px; }}
.report-actions {{ display:flex; gap:12px; margin-bottom:12px; align-items:center; }} .report-actions a {{ color:#9e2f0b; font-weight:700; }}
.ai-report {{ background:#fff; border:1px solid #efcdb8; border-radius:12px; padding:20px; }}
.ai-report h3 {{ margin:22px 0 10px; }} .ai-report h3:first-child {{ margin-top:0; }}
.ai-report-meta {{ color:#765b4d; font-size:.92rem; margin-bottom:16px; }}
.ai-full-report-link {{ display:inline-flex; align-items:center; margin:4px 0 12px; color:#9e2f0b; font-weight:700; text-decoration:underline; }}
.ai-full-report-link::after {{ content:" ↗"; font-size:.9em; }}
.ai-report-summary {{ font-size:1.05rem; line-height:1.55; white-space:pre-wrap; }}
.ai-report-list {{ display:grid; gap:12px; padding:0; list-style:none; }}
.ai-report-card {{ border:1px solid #efcdb8; border-radius:10px; padding:14px; }}
.ai-report-card strong {{ display:block; margin-bottom:6px; }} .ai-report-card p {{ margin:6px 0; }}
.ai-report-card small {{ color:#765b4d; }} .ai-report-card[data-priority="high"] {{ border-left:5px solid #c82f18; }}
.ai-report-card[data-priority="medium"] {{ border-left:5px solid #ed8a08; }} .ai-report-card[data-priority="low"] {{ border-left:5px solid #629b55; }}
.ai-report-evidence {{ margin:0; padding-left:20px; }} .ai-report-cautions {{ color:#7b3f00; }}
.ai-chat-history {{ display:flex; flex-direction:column; gap:8px; max-height:260px; overflow:auto; margin:8px 0 14px; }}
#ai-message {{ width:100%; min-height:100px; resize:vertical; box-sizing:border-box; }}
.ai-chat-message {{ padding:10px 12px; border-radius:10px; white-space:pre-wrap; }}
.ai-chat-message.user {{ background:#fff0e7; align-self:flex-end; max-width:85%; }}
.ai-chat-message.assistant {{ background:#f4f4f4; align-self:flex-start; max-width:85%; }}
.ai-mode-hint {{ display:block; margin-top:6px; color:#765b4d; line-height:1.4; font-weight:400; }}
.ai-thinking {{ display:flex; align-items:center; gap:10px; min-height:60px; color:#765b4d; font-weight:700; }}
.ai-thinking::before {{ content:""; width:18px; height:18px; border:3px solid #efcdb8; border-top-color:#ed4308; border-radius:50%; animation:ai-spin .8s linear infinite; }}
@keyframes ai-spin {{ to {{ transform:rotate(360deg); }} }}
.ai-workspace {{ padding:0; overflow:hidden; }}
.ai-workspace-header {{ display:flex; align-items:center; justify-content:space-between; gap:16px; padding:18px 22px; border-bottom:1px solid #efcdb8; }}
.ai-workspace-header h2 {{ margin:0; }} .ai-workspace-header small {{ color:#765b4d; }}
.ai-header-title {{ min-width:0; }} .ai-header-meta {{ display:flex; align-items:center; gap:8px; margin-top:6px; }}
.ai-model-chip {{ display:inline-flex; align-items:center; max-width:230px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding:4px 9px; border-radius:999px; background:#fff0e7; color:#8f3215; font-size:.8rem; font-weight:700; }}
.ai-drawer-toggle {{ display:none; width:auto; min-height:36px; padding:7px 10px; }}
.ai-mode-switch {{ display:flex; gap:4px; align-items:center; flex-wrap:wrap; justify-content:flex-end; }}
.ai-mode-segmented {{ display:flex; gap:3px; padding:3px; border:1px solid #efcdb8; border-radius:11px; background:#fffaf6; }}
.ai-mode-segmented button {{ width:auto; min-height:32px; padding:5px 9px; border-radius:8px; background:transparent; color:#765b4d; font-size:.85rem; }}
.ai-mode-segmented button.active {{ background:#ed4308; color:#fff; }}
.ai-mode-switch > #ai-mode {{ position:absolute !important; width:1px !important; height:1px !important; overflow:hidden !important; clip:rect(0 0 0 0) !important; }}
.ai-workspace-grid {{ display:grid; grid-template-columns:220px minmax(0,1fr) 260px; min-height:640px; }}
.ai-history-sidebar,.ai-context-sidebar {{ padding:18px; background:#fffaf6; }}
.ai-history-sidebar {{ border-right:1px solid #efcdb8; }} .ai-context-sidebar {{ border-left:1px solid #efcdb8; }}
.ai-sidebar-title {{ display:flex; align-items:center; justify-content:space-between; gap:8px; margin:0 0 12px; font-size:1rem; }}
.ai-sidebar-title button {{ width:auto; min-height:34px; padding:7px 10px; }}
.ai-chat-search {{ min-height:38px; padding:8px 10px; margin-bottom:12px; }}
#ai-saved-chats {{ min-height:180px; background:#fff; }} #ai-saved-chats option {{ padding:8px; }}
.ai-conversation {{ min-width:0; display:flex; flex-direction:column; padding:18px 24px 0; background:#fff; }}
.ai-conversation-empty {{ color:#765b4d; padding:28px 0 10px; }}
.ai-welcome {{ max-width:720px; margin:26px auto 12px; text-align:center; }}
.ai-welcome-icon {{ display:grid; place-items:center; width:48px; height:48px; margin:0 auto 12px; border-radius:15px; background:#fff0e7; color:#ed4308; font-size:1.45rem; font-weight:800; }}
.ai-welcome h3 {{ margin:0 0 7px; color:#441d0c; font-size:1.35rem; }} .ai-welcome p {{ margin:0; color:#765b4d; }}
.ai-suggestions {{ display:flex; flex-wrap:wrap; justify-content:center; gap:8px; margin-top:18px; }}
.ai-suggestion {{ width:auto; min-height:38px; padding:8px 12px; border:1px solid #e5c7b4; border-radius:12px; background:#fffaf6; color:#6f321c; text-align:left; }}
.ai-suggestion:hover {{ background:#fff0e7; }}
.ai-chat-history {{ flex:1 1 auto; max-height:380px; min-height:150px; overflow:auto; margin:8px 0 14px; }}
.ai-chat-message {{ max-width:min(86%,760px); }}
.ai-composer {{ position:sticky; bottom:0; margin:14px 0 0; padding:14px 0 18px; background:#fff; border-top:1px solid #f3dfd2; }}
.ai-composer textarea {{ min-height:92px; border-color:#d9b9a5; border-radius:14px; padding:14px; }}
.ai-prompt-composer {{ margin-top:8px; padding:10px; border:1px solid #efcdb8; border-radius:12px; background:#fffaf6; }}
.ai-message-row {{ display:grid; grid-template-columns:minmax(0,1fr) 150px; gap:8px; align-items:stretch; }}
.ai-message-row textarea,.ai-message-row #ai-message {{ min-height:260px; height:100%; }}
.ai-side-actions {{ display:flex; flex-direction:column; justify-content:space-between; gap:8px; height:100%; }}
.ai-side-actions > * {{ width:100%; min-height:68px; box-sizing:border-box; }}
.ai-side-actions input[type=file] {{ display:none; }}
.ai-side-actions #ai-chat-button {{ min-height:88px; font-size:1.15rem; }}
.ai-side-actions label,.ai-side-actions button {{ display:flex; align-items:center; justify-content:center; padding:8px; text-align:center; }}
.ai-side-actions label {{ border:1px solid #efcdb8; border-radius:9px; cursor:pointer; font-weight:600; }}
.ai-prompt-composer {{ margin-top:14px; padding:0; border:0; background:transparent; }}
.ai-prompt-composer-row {{ display:flex; align-items:stretch; gap:8px; }}
.ai-prompt-composer-row select {{ flex:1 1 auto; min-width:0; min-height:54px; padding:8px 10px; border-color:#d9b9a5; border-radius:10px; background:#fff; }}
.ai-prompt-composer-row button {{ flex:0 0 145px; align-self:stretch; }}
.ai-prompt-management {{ display:flex; gap:8px; align-items:center; margin-top:8px; }} .ai-prompt-management input {{ flex:1 1 auto; min-width:0; min-height:34px; }} .ai-prompt-management button {{ width:auto; min-height:34px; padding:6px 10px; }}
.ai-prompt-edit-field {{ display:none; }} .ai-prompt-edit-field.open {{ display:block; }}
.ai-prompt-edit-dialog {{ width:min(620px,calc(100vw - 32px)); border:1px solid #efcdb8; border-radius:16px; padding:22px; color:#441d0c; box-shadow:0 16px 50px #0003; }}
.ai-prompt-edit-dialog::backdrop {{ background:#24130d66; }} .ai-prompt-edit-dialog h2 {{ margin-top:0; }}
.ai-prompt-edit-dialog input,.ai-prompt-edit-dialog textarea {{ width:100%; box-sizing:border-box; }}
.ai-prompt-edit-dialog textarea {{ min-height:180px; resize:vertical; }} .ai-prompt-edit-dialog .actions {{ justify-content:flex-end; }}
.ai-composer-links {{ margin-top:12px; color:#765b4d; line-height:1.6; }} .ai-composer-links .text-link {{ margin-right:4px; font-weight:400; }} .ai-composer-links .text-link + .text-link::before {{ content:", "; color:#765b4d; text-decoration:none; display:inline-block; margin-right:4px; }}
.ai-composer-links .text-link.is-disabled {{ opacity:.5; pointer-events:none; }}
.ai-composer-toolbar {{ display:none; }}
.ai-composer-toolbar[hidden] {{ display:none !important; }}
.ai-composer-toolbar {{ display:flex; align-items:center; justify-content:space-between; gap:10px; margin-top:8px; }}
.ai-composer-tools {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; }} .ai-composer-tools input[type=file] {{ display:none; }}
.ai-composer-tools label,.ai-composer-tools button {{ width:auto; min-height:36px; padding:7px 10px; font-size:.9rem; }}
.ai-composer-tools label {{ border:1px solid #efcdb8; border-radius:9px; cursor:pointer; font-weight:600; }}
.ai-tool-picker {{ position:relative; }} .ai-tool-picker > button {{ max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.ai-tool-picker-panel {{ position:absolute; bottom:44px; left:0; z-index:30; display:none; width:min(320px,calc(100vw - 36px)); max-height:300px; overflow:auto; padding:10px; border:1px solid #efcdb8; border-radius:12px; background:#fff; box-shadow:0 10px 28px #0002; }}
.ai-tool-picker.open .ai-tool-picker-panel {{ display:grid; gap:4px; }}
.ai-tool-picker-panel > p {{ margin:0 0 6px; color:#765b4d; font-size:.82rem; line-height:1.35; }}
.ai-tool-option {{ display:flex; align-items:flex-start; gap:8px; padding:8px; border-radius:8px; cursor:pointer; }} .ai-tool-option:hover {{ background:#fff0e7; }}
.ai-tool-option input {{ width:auto; margin-top:3px; flex:0 0 auto; }} .ai-tool-option span {{ line-height:1.3; }}
.ai-composer-primary {{ width:auto; min-width:108px; }} .ai-context-chips {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:6px; }}
.ai-composer-more {{ position:relative; }} .ai-composer-more summary {{ list-style:none; cursor:pointer; border:1px solid #efcdb8; border-radius:9px; padding:7px 10px; color:#9e2f0b; font-weight:700; }} .ai-composer-more summary::-webkit-details-marker {{ display:none; }}
.ai-composer-more .ai-more-menu {{ position:absolute; bottom:42px; left:0; z-index:20; display:grid; gap:6px; min-width:220px; padding:8px; border:1px solid #efcdb8; border-radius:10px; background:#fff; box-shadow:0 8px 22px #0002; }}
.ai-composer-more .ai-more-menu button {{ text-align:left; }}
.ai-context-chip {{ display:inline-flex; align-items:center; gap:4px; padding:5px 9px; border:1px solid #e5c7b4; border-radius:16px; color:#765b4d; font-size:.82rem; background:#fffaf6; }}
.ai-context-chips {{ align-items:flex-start; }} .ai-context-chips .ai-tool-picker > button {{ min-height:32px; padding:5px 12px; border:1px solid #e5c7b4; border-radius:16px; background:#fffaf6; color:#765b4d; font-size:.9rem; font-weight:400; }}
.ai-context-chips .ai-tool-picker > button:hover,.ai-context-chips .ai-tool-picker.open > button {{ background:#fff0e7; color:#9e2f0b; }}
.ai-files-chip {{ cursor:default; }}
.ai-context-sidebar details {{ border-top:1px solid #efcdb8; padding-top:14px; margin-top:14px; }}
.ai-context-sidebar details:first-child {{ border-top:0; padding-top:0; margin-top:0; }} .ai-context-sidebar summary {{ margin-bottom:10px; }}
.ai-sidebar-footer {{ display:grid; gap:8px; margin-top:20px; padding-top:14px; border-top:1px solid #efcdb8; }} .ai-sidebar-footer button {{ width:100%; text-align:left; }}
.ai-context-sidebar select[multiple] {{ min-height:110px; padding:6px; }} .ai-context-sidebar .form-field {{ margin-top:10px; }}
.ai-prompt-library-panel {{ min-height:360px; }} .ai-prompt-library-panel select {{ min-height:230px; }}
.ai-hidden-compatible {{ position:absolute !important; width:1px !important; height:1px !important; overflow:hidden !important; clip:rect(0 0 0 0) !important; white-space:nowrap !important; }}
@media (max-width:1279px) {{ .ai-drawer-toggle.context-toggle {{ display:inline-flex; }} .ai-workspace-grid {{ grid-template-columns:220px minmax(0,1fr); }} .ai-context-sidebar {{ display:none; }} .ai-workspace.context-open .ai-context-sidebar {{ display:block; position:absolute; right:18px; z-index:25; width:min(320px,calc(100% - 36px)); border:1px solid #efcdb8; border-radius:12px; box-shadow:0 8px 28px #0002; }} .ai-workspace-grid {{ position:relative; }} }}
@media (max-width:900px) {{ .ai-drawer-toggle.history-toggle {{ display:inline-flex; }} .ai-workspace-grid {{ grid-template-columns:1fr; }} .ai-history-sidebar {{ display:none; }} .ai-workspace.history-open .ai-history-sidebar {{ display:block; position:absolute; left:18px; right:18px; z-index:25; border:1px solid #efcdb8; border-radius:12px; box-shadow:0 8px 28px #0002; }} .ai-conversation {{ padding:16px; }} }}
@media (max-width:600px) {{ .ai-workspace-header {{ align-items:flex-start; flex-direction:column; }} .ai-mode-switch {{ width:100%; justify-content:flex-start; }} .ai-mode-segmented {{ width:100%; }} .ai-mode-segmented button {{ flex:1; }} .ai-message-row {{ grid-template-columns:1fr; }} .ai-side-actions {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); }} .ai-side-actions > * {{ min-height:48px; }} .ai-prompt-composer-row {{ flex-wrap:wrap; }} .ai-prompt-composer-row select {{ flex-basis:100%; }} .ai-prompt-composer-row button {{ flex:1 1 0; }} .ai-chat-message {{ max-width:100%; }} }}
.dashboard-layout {{ display:grid; grid-template-columns:minmax(0,1fr) 0; gap:20px; align-items:start; }}
.dashboard-layout.help-open {{ grid-template-columns:minmax(0,1fr) minmax(220px,auto); }}
.dashboard-main {{ min-width:0; }}
.help-sidebar {{ position:sticky; top:20px; width:300px; min-width:220px; max-width:50vw; min-height:calc(100vh - 70px); resize:horizontal; overflow:auto; }}
.dashboard-layout:not(.help-open) .help-sidebar {{ width:0; min-width:0; overflow:hidden; }}
.help-content {{ max-height:calc(100vh - 150px); overflow:auto; }}
.help-content h2 {{ margin-top:0; }} .help-content h3 {{ margin:18px 0 8px; }}
.help-content p,.help-content li {{ line-height:1.5; }}
.tools-panel {{ padding:0; }} .tools-panel > summary {{ padding:18px 20px; font-size:1.1rem; font-weight:700; cursor:pointer; }} .tools-panel > summary .hint {{ margin-left:6px; }} .tools-content {{ display:grid; gap:14px; padding:0 14px 14px; }} .tools-content > .panel {{ margin:0; }}
header .header-actions {{ display:flex; align-items:center; gap:8px; }}
header .help-header-button {{ width:auto; min-width:120px; }}
@media (max-width:900px) {{ .dashboard-layout,.dashboard-layout.help-open {{ grid-template-columns:1fr; }} .help-sidebar,.dashboard-layout:not(.help-open) .help-sidebar {{ position:static; width:auto; max-width:none; min-width:0; min-height:0; resize:none; }} .help-content {{ max-height:none; }} .form-grid,.form-grid.three,.form-grid.four,.inventory-toolbar {{ grid-template-columns:1fr 1fr; }} }}
@media (max-width:600px) {{ body {{ padding:16px; }} header {{ display:block; }} header select {{ margin-top:12px; }} #checks,.form-grid,.form-grid.three,.form-grid.four {{ grid-template-columns:1fr; }} .actions {{ display:grid; }} }}
</style>
</head>
<body>
<a class="skip-link" href="#main-content">{escape(text["skip_to_content"])}</a>
<header><div><h1>{escape(text["title"])}</h1><p>{escape(text["subtitle"])}</p></div>
<div class="header-actions"><select id="language" aria-label="{escape(text["language"])}" style="width:auto"><option value="en">English</option><option value="ru">Русский</option></select><button id="help-toggle" type="button" class="secondary help-header-button" aria-expanded="false" aria-controls="help-content">{escape(text["help"])}</button></div></header>
<div class="dashboard-layout" id="main-content">
<main class="dashboard-main">
<section class="panel">
<div class="form-grid">
<div><label for="url">{escape(text["url"])} {_hint(text, "url_hint")}</label><input id="url" type="url" placeholder="https://example.com"></div>
<div><label for="preset">{escape(text["preset"])} {_hint(text, "preset_hint_label")}</label><select id="preset"><option value="all">{escape(text["preset_all"])}</option><option value="content">{escape(text["preset_content"])}</option><option value="api">{escape(text["preset_api"])}</option><option value="ai-search">{escape(text["preset_ai_search"])}</option><option value="v2">{escape(text["preset_v2"])}</option><option value="seo">{escape(text["preset_seo"])}</option><option value="mobile">{escape(text["preset_mobile"])}</option></select></div>
<div style="display:flex;align-items:flex-end;gap:8px"><button onclick="runScan()">{escape(text["scan"])}</button>{_hint(text, "run_hint")}</div>
</div>
<details><summary>{escape(text["advanced"])} <h2 class="sr-only">{escape(text["advanced"])}</h2></summary><div class="section-hint">{_hint(text, "advanced_hint")}</div>
<div class="form-grid three">
<div><label for="content-url">{escape(text["content_url"])} {_hint(text, "content_url_hint")}</label><input id="content-url" type="url"></div>
<div><label for="commerce-url">{escape(text["commerce_url"])} {_hint(text, "commerce_url_hint")}</label><input id="commerce-url" type="url"></div>
<div><label for="timeout">{escape(text["timeout"])} {_hint(text, "timeout_hint")}</label><input id="timeout" type="number" min="1" max="30" value="5"></div>
<div><label for="ai-provider-timeout">{escape(text["ai_provider_timeout"])} {_hint(text, "ai_provider_timeout_hint")}</label><input id="ai-provider-timeout" type="number" min="1" max="120" value="120"></div>
<div><label for="ai-provider-retries">{escape(text["ai_provider_retries"])} {_hint(text, "ai_provider_retries_hint")}</label><input id="ai-provider-retries" type="number" min="0" max="5" value="2"></div>
</div><div class="form-grid four" style="margin-top:14px">
<div><label for="workers">{escape(text["workers"])} {_hint(text, "workers_hint")}</label><input id="workers" type="number" min="1" max="24" value="8"></div>
<div><label for="threshold">{escape(text["threshold"])} {_hint(text, "threshold_hint")}</label><input id="threshold" type="text" inputmode="decimal" data-decimal min="0.01" max="1" step="0.01" value="0.8"></div>
<div><label for="recommendations">{escape(text["recommendations"])} {_hint(text, "recommendations_hint")}</label><input id="recommendations" type="number" min="0" max="50" value="10"></div>
<div><label for="check-limit">{escape(text["check_limit"])} {_hint(text, "check_limit_hint")}</label><input id="check-limit" type="number" min="0" max="500" value="0" inputmode="numeric"></div>
<label><input id="verify" type="checkbox" style="width:auto;margin-right:8">{escape(text["verify"])} {_hint(text, "verify_hint")}</label>
</div><div class="form-grid three" style="margin-top:14px">
<div><label for="v2-profile">{escape(text["v2_profile"])} {_hint(text, "v2_profile_hint")}</label><select id="v2-profile"><option value="quick">{escape(text["v2_profile_quick"])}</option><option value="standard">{escape(text["v2_profile_standard"])}</option><option value="deep">{escape(text["v2_profile_deep"])}</option></select></div>
<div><label for="v2-discovery">{escape(text["v2_discovery"])} {_hint(text, "v2_discovery_hint")}</label><select id="v2-discovery" onchange="syncFullDiscoveredControl()"><option value="single">{escape(text["v2_discovery_single"])}</option><option value="list">{escape(text["v2_discovery_list"])}</option><option value="sitemap">{escape(text["v2_discovery_sitemap"])}</option><option value="robots-sitemap">{escape(text["v2_discovery_robots"])}</option><option value="crawl">{escape(text["v2_discovery_crawl"])}</option></select></div>
<div><label for="v2-max-pages">{escape(text["v2_max_pages"])} {_hint(text, "v2_max_pages_hint")}</label><input id="v2-max-pages" type="number" min="0" max="25000" value="3"></div>
<div><label for="v2-max-depth">{escape(text["v2_max_depth"])} {_hint(text, "v2_max_depth_hint")}</label><input id="v2-max-depth" type="number" min="0" max="32" placeholder="профиль"></div>
<label><input id="v2-render" type="checkbox" style="width:auto;margin-right:8">{escape(text["v2_render"])} {_hint(text, "v2_render_hint")}</label>
<label><input id="v2-full-discovered" type="checkbox" style="width:auto;margin-right:8">{escape(text["v2_full_discovered"])} {_hint(text, "v2_full_discovered_hint")}</label>
</div></details>
<div class="advanced-links"><div class="advanced-link-row"><a href="#" class="text-link" onclick="loadChecks(); return false;">{escape(text["checks"])}</a>{_hint(text, "refresh_hint")}</div><div class="advanced-link-row"><a href="#" class="text-link" onclick="runHealth(); return false;">{escape(text["health"])}</a>{_hint(text, "health_hint")}</div><div class="advanced-link-row"><a href="#" class="text-link" onclick="openAiCredentials(); return false;">{escape(text["ai_credentials"])}</a>{_hint(text, "ai_credentials_hint")}</div><div class="advanced-link-row"><button type="button" class="text-link" onclick="openTaskStatus()">{escape(text["task_status"])}</button>{_hint(text, "task_status_hint")}</div><div class="advanced-link-row"><label style="font-weight:700;margin:0"><input id="debug" type="checkbox" style="width:auto;margin-right:6px">{escape(text["debug"])}</label>{_hint(text, "debug_hint")}</div></div>
</section>
<dialog id="ai-credentials-dialog"><form method="dialog" onsubmit="return false;"><h2>{escape(text["ai_credentials"])}</h2><p>{escape(text["ai_credentials_hint"])}</p><label for="ai-provider">{escape(text["ai_provider"])}</label><select id="ai-provider" onchange="selectAiProvider()"></select><div class="actions"><button type="button" class="secondary" onclick="newAiProvider()">{escape(text["ai_new"])}</button></div><div class="form-grid four" style="margin-top:14px"><div><label for="ai-provider-name">{escape(text["ai_provider_name"])}</label><input id="ai-provider-name" maxlength="100"></div><div><label for="ai-provider-url">{escape(text["ai_provider_url"])} {_hint(text, "ai_provider_url_hint")}</label><input id="ai-provider-url" type="url" maxlength="500"></div><div><label for="ai-provider-model">{escape(text["ai_model"])} {_hint(text, "ai_model_hint")}</label><div class="model-control"><select id="ai-provider-model"></select><button id="ai-provider-model-refresh" type="button" class="secondary" title="{escape(text["model_refresh"])}" aria-label="{escape(text["model_refresh"])}" onclick="refreshAiModels()">↻</button></div></div><div><label for="ai-key">{escape(text["ai_key"])}</label><input id="ai-key" type="password" autocomplete="off" maxlength="1000"></div></div><label style="margin-top:14px"><input id="ai-provider-chat-only" type="checkbox" onchange="toggleChatOnly()" style="width:auto;margin-right:8px">{escape(text["model_chat_only"])} {_hint(text, "model_chat_only_hint")}</label><label style="margin-top:14px"><input id="ai-enable" type="checkbox" style="width:auto;margin-right:8px">{escape(text["ai_enable"])} {_hint(text, "ai_enable_hint")}</label><div class="actions"><button type="button" onclick="saveAiProvider()">{escape(text["ai_save"])}</button><button type="button" class="secondary" onclick="activateAiProvider()">{escape(text["ai_activate"])}</button><button type="button" class="secondary" onclick="clearAiProvider()">{escape(text["ai_clear"])}</button><button type="button" class="secondary" onclick="document.getElementById('ai-credentials-dialog').close()">{escape(text["ai_close"])}</button></div><p id="ai-credentials-result" role="status" aria-live="polite"></p></form></dialog>
<section class="panel"><details><summary>{escape(text["select_checks"])} <h2 class="sr-only">{escape(text["select_checks"])}</h2></summary><div class="section-hint">{_hint(text, "checks_hint")}</div><div class="checks-toolbar"><div></div><div class="actions"><span><button class="secondary" onclick="selectApplicable(true)">{escape(text["all_checks"])}</button>{_hint(text, "select_all_hint")}</span><span><button class="secondary" onclick="selectApplicable(false)">{escape(text["clear_checks"] )}</button>{_hint(text, "clear_checks_hint")}</span></div></div><div id="checks"></div></details></section>
<section id="result-panel" class="panel" hidden><h2>{escape(text["result"])}</h2>
<div id="progress" hidden role="status" aria-live="polite"><strong>{escape(text["progress_title"])}</strong><button type="button" class="secondary" onclick="openTaskStatus()" title="{escape(text["task_status_hint"])}">{escape(text["task_status"])}</button><div id="crawl-progress" class="progress-substatus" hidden><span id="crawl-progress-phase"></span><span id="crawl-progress-count"></span></div><div class="progress-track"><span id="progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0" aria-valuetext="{escape(text["progress_start"])}"></span></div><div id="progress-steps"><span>{escape(text["progress_start"])}</span><span>{escape(text["progress_fetch"])}</span><span>{escape(text["progress_render"])}</span></div></div>
<div id="result" hidden role="status" aria-live="polite">{escape(text["ready"])}</div></section>
<dialog id="task-status-dialog" aria-labelledby="task-status-title"><h2 id="task-status-title">{escape(text["task_status"])}</h2><p>{escape(text["task_status_hint"])}</p><div id="task-status-list" class="task-status-list" role="region" aria-live="polite"></div><div class="actions"><button type="button" class="secondary" onclick="refreshTaskStatus()">{escape(text["task_status_refresh"])}</button><button type="button" class="secondary" onclick="document.getElementById('task-status-dialog').close()">{escape(text["task_status_close"])}</button></div></dialog>
<section id="v2-inventory-panel" class="panel" hidden aria-labelledby="v2-inventory-title">
<h2 id="v2-inventory-title">{escape(text["v2_inventory"])} {_hint(text, "v2_inventory_hint")}</h2>
<div class="inventory-toolbar">
<button type="button" class="secondary" onclick="loadV2Inventory()">{escape(text["v2_inventory_load"])}</button>
<label for="v2-inventory-kind">{escape(text["v2_inventory_kind"])} {_hint(text, "v2_inventory_kind_hint")}</label>
<select id="v2-inventory-kind" onchange="loadV2Inventory(this.value)"><option value="pages">{escape(text["v2_kind_pages"])}</option><option value="links">{escape(text["v2_kind_links"])}</option><option value="resources">{escape(text["v2_kind_resources"])}</option><option value="redirects">{escape(text["v2_kind_redirects"])}</option><option value="findings">{escape(text["v2_kind_findings"])}</option><option value="metrics">{escape(text["v2_kind_metrics"])}</option></select>
<label for="v2-inventory-limit">{escape(text["v2_rows"])} {_hint(text, "v2_rows_hint")}</label>
<select id="v2-inventory-limit" onchange="loadV2Inventory()"><option value="25">25</option><option value="50">50</option><option value="100" selected>100</option></select>
<label for="v2-inventory-sort">{escape(text["v2_inventory_sort"])} {_hint(text, "v2_inventory_sort_hint")}</label><select id="v2-inventory-sort" onchange="loadV2Inventory()"><option value="url">URL</option><option value="status">{escape(text["v2_sort_status"])}</option><option value="depth">{escape(text["v2_sort_depth"])}</option><option value="title">{escape(text["v2_sort_title"])}</option><option value="anchor">{escape(text["v2_sort_anchor"])}</option></select>
<label><input id="v2-inventory-desc" type="checkbox" style="width:auto;margin-right:6px" onchange="loadV2Inventory()">{escape(text["v2_inventory_desc"])} {_hint(text, "v2_inventory_desc_hint")}</label>
<label for="v2-inventory-filter">{escape(text["v2_filter"])} {_hint(text, "v2_filter_hint")}</label>
<input id="v2-inventory-filter" type="search" placeholder="{escape(text["v2_filter_hint"])}" oninput="filterV2Inventory()">
<label for="v2-inventory-columns">{escape(text["v2_columns"])} {_hint(text, "v2_columns_hint")}</label><select id="v2-inventory-columns" multiple size="3" aria-label="{escape(text["v2_columns"])}"><option value="url" selected>URL</option><option value="status" selected>Status</option><option value="title" selected>Title</option><option value="depth">{escape(text["v2_sort_depth"])}</option><option value="anchor">{escape(text["v2_sort_anchor"])}</option></select>
<button id="v2-inventory-next" type="button" class="secondary" onclick="loadNextV2Inventory()" hidden>{escape(text["v2_next_page"])}</button>
<button type="button" class="secondary" onclick="saveV2InventoryView()">{escape(text["v2_save_view"])}</button>
<label for="v2-saved-view">{escape(text["v2_saved_view"])} {_hint(text, "v2_saved_view_hint")}</label><select id="v2-saved-view" onchange="loadSavedV2View(this.value)"><option value="">—</option></select>
<button type="button" class="secondary" onclick="deleteSavedV2View()">{escape(text["v2_delete_view"])}</button>
<button type="button" class="secondary" onclick="exportSavedV2View()">{escape(text["v2_export_view"])}</button>
<button type="button" class="secondary" onclick="compareV2Inventory()">{escape(text["v2_inventory_compare"])}</button>
<button type="button" class="secondary" onclick="rescanV2Selection()">{escape(text["v2_inventory_rescan"])}</button>
<button type="button" class="secondary" onclick="runV2InventoryJob()">{escape(text["v2_inventory_job"])}</button>
<button type="button" class="secondary" onclick="cancelV2InventoryJob()">{escape(text["v2_inventory_cancel"])}</button>
</div>
<div id="v2-inventory-status" role="status" aria-live="polite"></div>
<div id="v2-inventory" role="region" aria-live="polite">{escape(text["v2_inventory_empty"])}</div>
</section>
<details id="tools-panel" class="panel tools-panel">
<summary>{escape(text["tools"])} {_hint(text, "tools_hint")}</summary>
<div class="tools-content">
<section id="robots-simulation-panel" class="panel" hidden aria-labelledby="robots-simulation-title">
<h2 id="robots-simulation-title">{escape(text["robots_simulation"])} {_hint(text, "robots_simulation_hint")}</h2>
<div class="form-grid three"><div class="robots-document-field"><label for="robots-live">{escape(text["robots_live"])} {_hint(text, "robots_live_hint")}</label><textarea id="robots-live" rows="5"></textarea></div><div class="robots-document-field"><label for="robots-proposed">{escape(text["robots_proposed"])} {_hint(text, "robots_proposed_hint")}</label><textarea id="robots-proposed" rows="5"></textarea></div><div><label for="robots-user-agents">{escape(text["robots_user_agents"])} {_hint(text, "robots_user_agents_hint")}</label><input id="robots-user-agents" value="*"><button type="button" class="secondary" onclick="simulateRobots()">{escape(text["robots_simulate"])}</button></div></div>
<div id="robots-simulation-status" role="status" aria-live="polite">{escape(text["robots_empty"])}</div><div id="robots-simulation-result" role="region" aria-live="polite"></div>
</section>
<section id="sitemap-reconciliation-panel" class="panel" hidden aria-labelledby="sitemap-reconciliation-title">
<h2 id="sitemap-reconciliation-title">{escape(text["sitemap_reconciliation"])} {_hint(text, "sitemap_reconciliation_hint")}</h2>
<p class="section-hint">{escape(text["sitemap_reconciliation_hint"])}</p>
<label for="sitemap-reconciliation-origin">{escape(text["sitemap_origin"])} {_hint(text, "sitemap_origin_hint")}</label><input id="sitemap-reconciliation-origin" type="url" placeholder="https://example.test">
<label for="sitemap-reconciliation-xml">{escape(text["sitemap_documents"])} {_hint(text, "sitemap_documents_hint")}</label><textarea id="sitemap-reconciliation-xml" rows="6"></textarea>
<button type="button" class="secondary" onclick="reconcileSitemap()">{escape(text["sitemap_reconcile"])}</button>
<div id="sitemap-reconciliation-status" role="status" aria-live="polite"></div><div id="sitemap-reconciliation-result" role="region" aria-live="polite"></div>
</section>
<section id="custom-rules-panel" class="panel" aria-labelledby="custom-rules-title">
<h2 id="custom-rules-title">{escape(text["custom_rules"])} {_hint(text, "custom_rules_hint")}</h2>
<p class="section-hint">{escape(text["custom_rules_hint"])}</p>
<label for="custom-rules-document">{escape(text["custom_rules_document"])} {_hint(text, "custom_rules_document_hint")}</label><textarea id="custom-rules-document" rows="8">version: 1
rules:
  - id: example
    title: {text["custom_rules_example_title"]}
    assert:
      kind: text
      pattern: agent</textarea>
<div><button type="button" class="secondary" onclick="validateCustomRules()">{escape(text["custom_rules_validate"])}</button><button type="button" class="secondary" onclick="debugCustomRules()">{escape(text["custom_rules_preview"])}</button></div>
<div id="custom-rules-status" role="status" aria-live="polite"></div><pre id="custom-rules-result" role="region" aria-live="polite"></pre>
</section>
<section id="link-graph-panel" class="panel" hidden aria-labelledby="link-graph-title">
<h2 id="link-graph-title">{escape(text["link_graph"])} {_hint(text, "link_graph_hint")}</h2>
<p class="section-hint">{escape(text["link_graph_hint"])}</p>
<div class="form-grid four"><label for="link-graph-node-cap">{escape(text["graph_node_cap"])} {_hint(text, "graph_node_cap_hint")}</label><select id="link-graph-node-cap"><option value="25">25</option><option value="50">50</option><option value="100" selected>100</option><option value="all">{escape(text["graph_all_nodes"])}</option></select><label for="link-graph-min-authority">{escape(text["graph_min_authority"])} {_hint(text, "graph_min_authority_hint")}</label><input id="link-graph-min-authority" type="number" min="0" max="1" step="0.01" value="0"></div>
<div class="form-grid four"><label for="link-graph-depth">{escape(text["graph_depth"])} {_hint(text, "graph_depth_hint")}</label><select id="link-graph-depth"><option value="all">{escape(text["graph_depth_all"])}</option><option value="0">{escape(text["graph_depth_root"])}</option><option value="1">{escape(text["graph_depth_1"])}</option><option value="2">{escape(text["graph_depth_2"])}</option><option value="3+">{escape(text["graph_depth_3_plus"])}</option></select><label><input id="link-graph-dead-end" type="checkbox"> {escape(text["graph_dead_ends"])} {_hint(text, "graph_dead_ends_hint")}</label><label><input id="link-graph-disconnected" type="checkbox"> {escape(text["graph_disconnected"])} {_hint(text, "graph_disconnected_hint")}</label><button type="button" class="secondary" onclick="loadLinkGraph()">{escape(text["graph_load"])}</button></div>
<div id="link-graph-status" role="status" aria-live="polite"></div><div id="link-graph-result" role="region" aria-live="polite"></div><h3>{escape(text["graph_visual"])} {_hint(text, "graph_visual_hint")}</h3><div id="link-graph-visual" role="img" aria-label="{escape(text["graph_visual"])}" class="link-graph-visual"></div>
</section>
<section id="duplicate-clusters-panel" class="panel" hidden aria-labelledby="duplicate-clusters-title">
<h2 id="duplicate-clusters-title">{escape(text["duplicate_clusters"])} {_hint(text, "duplicate_clusters_hint")}</h2>
<p class="section-hint">{escape(text["duplicate_clusters_hint"])}</p>
<div><label class="sr-only" for="duplicate-clusters-kind">{escape(text["duplicate_clusters"])} {_hint(text, "duplicate_kind_hint")}</label><select id="duplicate-clusters-kind"><option value="all">{escape(text["duplicate_all"])}</option><option value="exact">{escape(text["duplicate_exact"])}</option><option value="near">{escape(text["duplicate_near"])}</option></select><button type="button" class="secondary" onclick="loadDuplicateClusters()">{escape(text["duplicate_load"])}</button></div>
<div id="duplicate-clusters-status" role="status" aria-live="polite"></div><div id="duplicate-clusters-result" role="region" aria-live="polite"></div>
</section>
<section id="projects-panel" class="panel" aria-labelledby="projects-title">
<h2 id="projects-title">{escape(text["projects"])} {_hint(text, "projects_hint")}</h2>
<p class="section-hint">{escape(text["projects_hint"])}</p>
<div><label for="project-id">{escape(text["project_id"])} {_hint(text, "project_id_hint")}</label><input id="project-id" value="default-project"><label for="project-name">{escape(text["project_name"])} {_hint(text, "project_name_hint")}</label><input id="project-name" value="{escape(text["project_default_name"])}"><button type="button" class="secondary" onclick="createDashboardProject()">{escape(text["project_save"])}</button><button type="button" class="secondary" onclick="loadDashboardProjects()">{escape(text["project_load_history"])}</button></div>
<div id="projects-status" role="status" aria-live="polite"></div><div id="projects-result" role="region" aria-live="polite"></div>
</section>
</div>
</details>
<section id="ai-assistant-panel" class="panel ai-workspace" hidden aria-labelledby="ai-workspace-title">
<div class="ai-workspace-header"><div class="ai-header-title"><h2 id="ai-workspace-title">{escape(text["ai_title"])}</h2><div class="ai-header-meta"><small>{escape(text["ai_hint"])}</small><span id="ai-model-chip" class="ai-model-chip" title="{escape(text["ai_model_chip"])}">{escape(text["ai_model_chip"])}: —</span></div></div><div class="ai-mode-switch"><button type="button" class="secondary ai-drawer-toggle history-toggle" title="{escape(text["ai_saved_chats"])}" onclick="toggleAiDrawer('history')">{escape(text["ai_saved_chats"])}</button><button type="button" class="secondary ai-drawer-toggle context-toggle" title="{escape(text["ai_mcp_hint"])}" onclick="toggleAiDrawer('context')">{escape(text["ai_mcp"])}</button><label class="sr-only" for="ai-mode">{escape(text["ai_mode"])}</label><div class="ai-mode-segmented" role="group" aria-label="{escape(text["ai_mode"])}"><button type="button" data-ai-mode="both" title="{escape(text["ai_mode_both_hint"])}" onclick="setAiMode('both')">{escape(text["ai_mode_both"])}</button><button type="button" data-ai-mode="seo" title="{escape(text["ai_mode_seo_hint"])}" onclick="setAiMode('seo')">{escape(text["ai_mode_seo"])}</button><button type="button" data-ai-mode="geo" title="{escape(text["ai_mode_geo_hint"])}" onclick="setAiMode('geo')">{escape(text["ai_mode_geo"])}</button></div><select id="ai-mode" onchange="updateAiModeHint()"><option value="both">{escape(text["ai_mode_both"])}</option><option value="seo">{escape(text["ai_mode_seo"])}</option><option value="geo">{escape(text["ai_mode_geo"])}</option></select><small id="ai-mode-hint" class="ai-mode-hint"></small></div></div>
<div class="ai-workspace-grid">
<aside class="ai-history-sidebar" aria-label="{escape(text["ai_saved_chats"])}"><h3 class="ai-sidebar-title">{escape(text["ai_saved_chats"])}<button type="button" class="secondary" title="{escape(text["ai_new_chat"])}" onclick="startNewChat()">{escape(text["ai_new_chat"])}</button></h3><input id="ai-chat-search" class="ai-chat-search" type="search" placeholder="{escape(text["ai_saved_chats"])}" aria-label="{escape(text["ai_saved_chats"])}" title="{escape(text["ai_saved_chats"])}"><label class="sr-only" for="ai-saved-chats">{escape(text["ai_saved_chats"])}</label><select id="ai-saved-chats" size="8"></select></aside>
<main class="ai-conversation"><div id="ai-welcome" class="ai-welcome"><div class="ai-welcome-icon" aria-hidden="true">✦</div><h3>{escape(text["ai_welcome"])}</h3><p>{escape(text["ai_welcome_hint"])}</p><div class="ai-suggestions"><button type="button" class="ai-suggestion" title="{escape(text["ai_suggestion_seo"])}" onclick="useAiSuggestedPrompt(this.textContent)">{escape(text["ai_suggestion_seo"])}</button><button type="button" class="ai-suggestion" title="{escape(text["ai_suggestion_geo"])}" onclick="useAiSuggestedPrompt(this.textContent)">{escape(text["ai_suggestion_geo"])}</button><button type="button" class="ai-suggestion" title="{escape(text["ai_suggestion_summary"])}" onclick="useAiSuggestedPrompt(this.textContent)">{escape(text["ai_suggestion_summary"])}</button></div></div><div id="ai-chat-history" class="ai-chat-history" aria-live="polite"></div><div id="ai-result" class="ai-report" hidden role="status" aria-live="polite"></div><div class="ai-composer"><div id="ai-context-chips" class="ai-context-chips"><div id="ai-skills-picker" class="ai-tool-picker"><button type="button" class="secondary" id="ai-skills-trigger" title="{escape(text["ai_skills_hint"])}" onclick="toggleAiToolPicker('skills')">{escape(text["ai_skills_selected"])}</button><div class="ai-tool-picker-panel" role="group" aria-label="{escape(text["ai_skills"])}"><p>{escape(text["ai_picker_hint"])}</p><div id="ai-skills-options"></div></div></div><div id="ai-context-picker" class="ai-tool-picker"><button type="button" class="secondary" id="ai-context-trigger" title="{escape(text["ai_mcp_hint"])}" onclick="toggleAiToolPicker('context')">{escape(text["ai_context_selected"])}</button><div class="ai-tool-picker-panel" role="group" aria-label="{escape(text["ai_mcp"])}"><p>{escape(text["ai_picker_hint"])}</p><div id="ai-context-options"></div></div></div></div><label class="sr-only" for="ai-message">{escape(text["ai_message"])}</label><textarea id="ai-message" placeholder="{escape(text["ai_message"])}"></textarea><div class="ai-composer-toolbar"><div class="ai-composer-tools"><label for="ai-attachments" title="{escape(text["ai_attach_hint"])}">＋ {escape(text["ai_attachments"])}<input id="ai-attachments" type="file" multiple accept=".jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx,.pdf,.txt,.md,.markdown,.json,.csv,.yaml,.yml,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,image/jpeg,image/png"></label><button type="button" class="secondary" title="{escape(text["ai_prompt_library"])}" onclick="openAiPromptPicker()">{escape(text["ai_prompt_apply"])}</button><details class="ai-composer-more"><summary title="{escape(text["ai_more"])}">⋯ <span class="sr-only">{escape(text["ai_more"])}</span></summary><div class="ai-more-menu"><button type="button" class="secondary" onclick="exportChat()">{escape(text["ai_chat_export"])}</button><button id="ai-run-button" type="button" class="secondary" title="{escape(text["ai_run_hint"])}" aria-label="{escape(text["ai_run_hint"])}" onclick="runAi('/ai/recommend')">{escape(text["ai_run"])}</button><button id="ai-retry-button" type="button" class="secondary" title="{escape(text["ai_retry"])}" onclick="runAi('/ai/chat', true)">{escape(text["ai_retry"])}</button></div></details></div><button id="ai-chat-button" type="button" class="ai-composer-primary" title="{escape(text["ai_chat_hint"])}" aria-label="{escape(text["ai_chat_hint"])}">{escape(text["ai_send"])}</button></div></div></main>
<aside class="ai-context-sidebar" aria-label="{escape(text["ai_hint"])}"><details class="ai-hidden-compatible" open><summary title="{escape(text["ai_mcp_hint"])}">{escape(text["ai_mcp"])}</summary><label for="ai-mcp-tool" class="sr-only">{escape(text["ai_mcp"])}</label><select id="ai-mcp-tool" multiple size="3"><option value="agentready.seo_findings" title="Найденные проблемы SEO и связанные доказательства">AgentReady MCP: SEO findings</option><option value="agentready.remediation_plan" title="План исправлений, сформированный по результатам аудита">AgentReady MCP: remediation plan</option></select></details><details class="ai-hidden-compatible" open><summary title="{escape(text["ai_skills_hint"])}">{escape(text["ai_skills"])}</summary><label for="ai-skill" class="sr-only">{escape(text["ai_skills"])}</label><select id="ai-skill" multiple size="4">{skill_options}</select></details><details open><summary>{escape(text["ai_model"])}</summary><label for="ai-chat-provider">{escape(text["ai_provider"])}</label><select id="ai-chat-provider" onchange="selectChatProvider()"></select><label for="ai-model">{escape(text["ai_model"])}</label><select id="ai-model"></select><div class="ai-model-actions"><button type="button" class="secondary" title="{escape(text["ai_credentials_hint"])}" onclick="openAiCredentials()">{escape(text["ai_settings_footer"])}</button></div></details></aside>
</div></section>
</main>
<aside class="help-sidebar" aria-label="{escape(text["help_title"])}"><section id="help-content" class="panel help-content" hidden tabindex="-1">{faq}</section></aside>
</div>
<noscript><section class="noscript-notice" aria-labelledby="noscript-title"><h2 id="noscript-title">{escape(text["noscript_title"])}</h2><p>{escape(text["noscript_text"])}</p></section></noscript>
<script>
const translations = {translations};
function addSettingsHints() {{
  const hints = {{
    "ai-provider-name": "ai_provider_name_hint",
    "ai-key": "ai_key_hint",
  }};
  let added = 0;
  Object.entries(hints).forEach(([id, key]) => {{
    const control = document.getElementById(id);
    const label = control && document.querySelector(`label[for="${{id}}"]`);
    if (!label || label.querySelector(".hint")) return;
    const value = translations[language.value][key];
    if (!value) return;
    const hint = document.createElement("span");
    hint.className = "hint";
    hint.tabIndex = 0;
    hint.setAttribute("role", "img");
    hint.setAttribute("aria-label", value);
    hint.dataset.tooltip = value;
    hint.textContent = "?";
    label.appendChild(hint);
    added += 1;
  }});
  console.info("[FIX:dashboard-hints] Settings hints attached", {{added}});
}}
const language = document.getElementById("language");
language.value = "{lang}";
const languageExplicit = new URLSearchParams(location.search).has("language");
const helpToggle = document.getElementById("help-toggle");
const helpContent = document.getElementById("help-content");
const helpSidebar = document.querySelector(".help-sidebar");
helpToggle.onclick = () => {{
  const visible = helpContent.hidden;
  helpContent.hidden = !visible;
  helpSidebar.parentElement.classList.toggle("help-open", visible);
  helpToggle.textContent = visible ? translations[language.value].help_hide : translations[language.value].help;
  helpToggle.setAttribute("aria-expanded", String(visible));
  (visible ? helpContent : helpToggle).focus();
  console.info("Dashboard help toggled", {{visible, language:language.value}});
}};
const dashboardStateKey = "agentready.dashboard.state.v2";
const dashboardStateCacheKey = "/dashboard/state";
const dashboardReportKey = "agentready.dashboard.report.v2";
const dashboardStateIds = ["url","content-url","commerce-url","preset","timeout","ai-provider-timeout","ai-provider-retries","workers","threshold","recommendations","check-limit","verify","debug","v2-profile","v2-discovery","v2-max-pages","v2-max-depth","v2-render","v2-full-discovered","ai-mode","ai-chat-provider","ai-model","ai-message","ai-provider","ai-provider-chat-only","robots-live","robots-proposed","robots-user-agents","sitemap-reconciliation-origin","sitemap-reconciliation-xml","custom-rules-document","link-graph-node-cap","link-graph-min-authority","link-graph-depth","link-graph-dead-end","link-graph-disconnected","duplicate-clusters-kind","project-id","project-name"];
let dashboardStateSaveTimer = null;
function readDashboardState() {{
  try {{
    const raw = localStorage.getItem(dashboardStateKey);
    return raw ? JSON.parse(raw) : {{}};
  }} catch (error) {{
    console.warn("Unable to read dashboard state", {{error:String(error)}});
    return {{}};
  }}
}}
function scheduleSaveDashboardState(state) {{
  clearTimeout(dashboardStateSaveTimer);
  dashboardStateSaveTimer = setTimeout(() => {{
    fetch(dashboardStateCacheKey, {{method:"PUT", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify(state)}})
      .then(response => {{ if (!response.ok) throw new Error("HTTP " + response.status); console.info("[FIX:dashboard-state] State mirrored to cache", {{fields:Object.keys(state).length}}); }})
      .catch(error => console.warn("[FIX:dashboard-state] Unable to mirror state to cache", {{error:String(error)}}));
  }}, 250);
}}
function saveDashboardState() {{
  try {{
    const state = readDashboardState();
    dashboardStateIds.forEach(id => {{
      const element = document.getElementById(id);
      if (!element) return;
      state[id] = element.type === "checkbox" ? element.checked : element.value;
    }});
    const toolsPanel = document.getElementById("tools-panel");
    if (toolsPanel) state["tools-open"] = toolsPanel.open;
    state.language = language.value;
    localStorage.setItem(dashboardStateKey, JSON.stringify(state));
    scheduleSaveDashboardState(state);
  }} catch (error) {{
    console.warn("Unable to save dashboard state", {{error:String(error)}});
  }}
}}
function restoreDashboardState() {{
  const state = readDashboardState();
  if (!languageExplicit && state.language && [...language.options].some(option => option.value === state.language)) language.value = state.language;
  dashboardStateIds.forEach(id => {{
    const element = document.getElementById(id);
    if (!element || state[id] === undefined) return;
    if (element.type === "checkbox") element.checked = Boolean(state[id]);
    else element.value = element.dataset.decimal !== undefined ? normalizeDecimalString(state[id]) : state[id];
    if (id === "robots-live" && typeof state[id] === "string" && state[id].trim()) element.dataset.userEdited = "true";
  }});
  const toolsPanel = document.getElementById("tools-panel");
    if (toolsPanel && typeof state["tools-open"] === "boolean") toolsPanel.open = state["tools-open"];
  syncFullDiscoveredControl();
  return state;
}}
async function restoreDashboardStateFromCache() {{
  try {{
    const response = await fetch(dashboardStateCacheKey);
    if (!response.ok) return;
    const payload = await response.json();
    const cached = payload && payload.state && typeof payload.state === "object" ? payload.state : {{}};
    const local = readDashboardState();
    const merged = {{...cached, ...local}};
    dashboardStateIds.forEach(id => {{
      const element = document.getElementById(id);
      if (!element || merged[id] === undefined || local[id] !== undefined) return;
      if (element.type === "checkbox") element.checked = Boolean(merged[id]);
      else element.value = merged[id];
    }});
    const toolsPanel = document.getElementById("tools-panel");
    if (toolsPanel && local["tools-open"] === undefined && typeof cached["tools-open"] === "boolean") toolsPanel.open = cached["tools-open"];
    syncFullDiscoveredControl();
    console.info("[FIX:dashboard-state] State restored from cache", {{fields:Object.keys(cached).length}});
  }} catch (error) {{ console.warn("[FIX:dashboard-state] Unable to restore state from cache", {{error:String(error)}}); }}
}}
const restoredDashboardState = restoreDashboardState();
restoreDashboardStateFromCache();
language.onchange = () => {{ saveDashboardState(); location.search = "?language=" + language.value; }};
dashboardStateIds.forEach(id => {{
  const element = document.getElementById(id);
  if (element) element.addEventListener(element.type === "checkbox" ? "change" : "input", () => {{ if (id === "v2-full-discovered") syncFullDiscoveredControl(); saveDashboardState(); }});
}});
let catalog = [];
const result = document.getElementById("result");
const resultPanel = document.getElementById("result-panel");
const aiPanel = document.getElementById("ai-assistant-panel");
let auditCompleted = false;
const presetLabels = {{all:translations[language.value].preset_all, content:translations[language.value].preset_content, api:translations[language.value].preset_api, "ai-search":translations[language.value].preset_ai_search, v2:translations[language.value].preset_v2, seo:translations[language.value].preset_seo, mobile:translations[language.value].preset_mobile}};
const profileHints = {{all:translations[language.value].profile_all, content:translations[language.value].profile_content, api:translations[language.value].profile_api, "ai-search":translations[language.value].profile_ai_search, v2:translations[language.value].profile_v2, seo:translations[language.value].profile_seo, mobile:translations[language.value].profile_mobile}};
const progress = document.getElementById("progress"); const progressBar = document.getElementById("progress-bar"); const crawlProgress = document.getElementById("crawl-progress"); const crawlProgressPhase = document.getElementById("crawl-progress-phase"); const crawlProgressCount = document.getElementById("crawl-progress-count");
let activeV2JobId = localStorage.getItem("agentready.dashboard.job.v2") || null;
if (activeV2JobId === "null" || activeV2JobId === "undefined") activeV2JobId = null;
function debugMode() {{ return document.getElementById("debug").checked; }}
function updateAiModeHint() {{
  const mode = document.getElementById("ai-mode").value;
  const hint = document.getElementById("ai-mode-hint");
  if (hint) hint.textContent = translations[language.value]["ai_mode_" + mode + "_hint"] || translations[language.value].ai_request_hint;
  document.querySelectorAll("[data-ai-mode]").forEach(button => button.classList.toggle("active", button.dataset.aiMode === mode));
}}
function setAiMode(mode) {{
  const select = document.getElementById("ai-mode");
  if (!select || ![...select.options].some(option => option.value === mode)) return;
  select.value = mode;
  updateAiModeHint();
  saveDashboardState();
  console.info("[AI-UX] Mode selected", {{mode}});
}}
function useAiSuggestedPrompt(prompt) {{
  const message = document.getElementById("ai-message");
  if (!message) return;
  message.value = String(prompt || "").trim();
  message.focus();
  message.scrollIntoView({{block:"nearest", behavior:"smooth"}});
  console.info("[AI-UX] Suggested prompt selected");
}}
function toggleAiDrawer(kind) {{
  const panel = document.getElementById("ai-assistant-panel");
  const className = kind === "context" ? "context-open" : "history-open";
  panel.classList.toggle(className);
  console.info("[AI-UX] Drawer toggled", {{kind, open:panel.classList.contains(className)}});
}}
function openAiPromptPicker() {{
  const panel = document.getElementById("ai-assistant-panel");
  panel.classList.add("context-open");
  const picker = document.getElementById("ai-prompt-library");
  picker.focus();
  console.info("[AI-UX] Prompt picker opened from composer");
}}
function updatePresetHint() {{
  const value = profileHints[document.getElementById("preset").value] || "";
  const icon = document.querySelector("label[for='preset'] .hint");
  if (icon) icon.dataset.tooltip = value;
  console.info("Audit profile selected", {{preset:document.getElementById("preset").value}});
}}
function selectedChecks() {{ return [...document.querySelectorAll("#checks input:checked")].map(item => item.value); }}
function decimalValue(id, fallback=0) {{
  const element = document.getElementById(id);
  const normalized = String(element ? element.value : "").trim().replace(",", ".");
  const value = Number(normalized);
  return Number.isFinite(value) ? value : fallback;
}}
function normalizeDecimalInput(event) {{
  const element = event.currentTarget;
  element.value = normalizeDecimalString(element.value);
}}
function normalizeDecimalString(value) {{
  return String(value).trim().replace(",", ".").replace(/^(-?)\./, "$10.");
}}
document.querySelectorAll("[data-decimal]").forEach(element => element.addEventListener("blur", normalizeDecimalInput));
function showResult() {{ resultPanel.hidden = false; result.hidden = false; }}
function setAiAvailability(available) {{
  auditCompleted = available;
  const enabled = Boolean(available && document.getElementById("url").value.trim());
  aiPanel.hidden = !enabled;
  ["ai-mode","ai-chat-provider","ai-model","ai-message"].forEach(id => {{
    const element = document.getElementById(id);
    if (element) element.disabled = !enabled;
  }});
  aiPanel.open = false;
}}
function setAiBusy(busy) {{
  const output = document.getElementById("ai-result");
  ["ai-run-button","ai-chat-button"].forEach(id => {{
    const button = document.getElementById(id);
    if (button) {{ button.disabled = busy; button.setAttribute("aria-disabled", String(busy)); button.classList.toggle("is-disabled", busy); }}
  }});
  if (busy) {{
    output.hidden = false;
    output.className = "ai-report";
    const thinking = document.createElement("div");
    thinking.className = "ai-thinking";
    thinking.setAttribute("role", "status");
    thinking.setAttribute("aria-live", "polite");
    thinking.textContent = translations[language.value].ai_thinking;
    output.replaceChildren(thinking);
  }} else {{
    const thinking = output.querySelector(".ai-thinking");
    if (thinking) {{
      thinking.remove();
      console.warn("AI thinking state cleared after request completion");
    }}
  }}
}}
function selectApplicable(value) {{
  const preset = document.getElementById("preset").value;
  document.querySelectorAll("#checks input").forEach(item => {{
    const spec = catalog.find(candidate => candidate.id === item.value);
    item.checked = value && (preset === "seo" || preset === "mobile" || (spec.presets || []).includes(preset));
  }});
}}
function scanPayload() {{
  const preset = document.getElementById("preset").value;
  const applicable = catalog.filter(item => item.presets.includes(preset)).map(item => item.id);
  const selected = selectedChecks();
  const payload = {{url:document.getElementById("url").value, preset, profile:document.getElementById("v2-profile").value, discovery_kind:selectedV2Discovery(),
    max_pages:selectedV2MaxPages(), language:language.value,
    content_url:document.getElementById("content-url").value || null, commerce_url:document.getElementById("commerce-url").value || null,
    include:selected.filter(id => !applicable.includes(id)), exclude:applicable.filter(id => !selected.includes(id)),
    timeout:Number(document.getElementById("timeout").value), workers:Number(document.getElementById("workers").value),
    level_threshold:decimalValue("threshold", .8), recommendation_limit:Number(document.getElementById("recommendations").value),
    limits:selectedV2Limits(),
    verify_skill_digests:document.getElementById("verify").checked}};
  return payload;
}}
function setProgress(percent, message) {{ showResult(); progress.hidden = false; progressBar.style.width = percent + "%"; progressBar.setAttribute("aria-valuenow", String(percent)); progressBar.setAttribute("aria-valuetext", message); result.textContent = message; }}
function setCrawlProgress(progressData) {{ if (!progressData) return; crawlProgress.hidden = false; crawlProgressPhase.textContent = translations[language.value].progress_crawl_phase.replace("{{phase}}", progressData.phase || "crawl"); crawlProgressCount.textContent = translations[language.value].progress_crawl.replace("{{fetched}}", String(progressData.fetched || 0)).replace("{{discovered}}", String(progressData.discovered || 0)); }}
let taskStatusTimer = null;
function taskStatusLabel(status) {{ const labels = {{running:language.value === "ru" ? "выполняется" : "running",pending:language.value === "ru" ? "ожидает" : "pending",completed:language.value === "ru" ? "завершена" : "completed",failed:language.value === "ru" ? "ошибка" : "failed",cancelled:language.value === "ru" ? "отменена" : "cancelled"}}; return labels[status] || status; }}
async function refreshTaskStatus() {{
  const host = document.getElementById("task-status-list");
  if (!host) return;
  try {{
    const response = await fetch("/v2/jobs");
    if (!response.ok) throw new Error("HTTP " + response.status);
    const items = (await response.json()).items || [];
    const t = translations[language.value];
    host.innerHTML = items.length ? items.map(item => {{
      const progress = item.progress || {{}};
      const stale = item.status === "running" && Number(item.updated_age_seconds || 0) >= 30 ? `<small>${{escapeHtml(t.task_status_stale.replace("{{seconds}}", String(item.updated_age_seconds)))}}</small>` : "";
      const cancel = ["running", "pending"].includes(item.status) ? `<button type="button" class="secondary" onclick="cancelTaskStatus('${{escapeHtml(item.id)}}')">${{escapeHtml(t.task_status_cancel)}}</button>` : "";
      return `<div class="task-status-row"><code>${{escapeHtml(item.id.slice(0,12))}}</code><strong>${{escapeHtml(taskStatusLabel(item.status))}}</strong><span>${{escapeHtml(String(progress.phase || "—"))}} · ${{escapeHtml(String(progress.fetched || 0))}}/${{escapeHtml(String(progress.discovered || 0))}} ${{stale}}</span>${{cancel}}</div>`;
    }}).join("") : `<p>${{escapeHtml(t.task_status_empty)}}</p>`;
  }} catch (error) {{ host.textContent = translations[language.value].failed + ": " + error.message; }}
}}
async function cancelTaskStatus(jobId) {{ try {{ await fetch("/v2/jobs/" + encodeURIComponent(jobId) + "/cancel", {{method:"POST"}}); await refreshTaskStatus(); }} catch (error) {{ console.warn("[FIX:dashboard-progress] Task cancellation failed", {{job_id:jobId, error:String(error)}}); }} }}
function openTaskStatus() {{ const dialog = document.getElementById("task-status-dialog"); if (!dialog) return; dialog.showModal(); refreshTaskStatus(); clearInterval(taskStatusTimer); taskStatusTimer = setInterval(refreshTaskStatus, 2000); dialog.addEventListener("close", () => {{ clearInterval(taskStatusTimer); taskStatusTimer = null; }}, {{once:true}}); }}
function safeDashboardTarget(value) {{
  try {{
    const raw = String(value || "").trim();
    const candidate = /^https?:\/\//i.test(raw)
      ? raw
      : (raw.startsWith("//") ? "https:" + raw : "https://" + raw);
    const parsed = new URL(candidate, window.location.origin);
    if (!/^https?:$/.test(parsed.protocol)) return "[invalid-target]";
    if (!/^https?:\/\//i.test(raw)) console.info("[FIX:dashboard-redaction] Normalized dashboard target protocol", {{protocol:parsed.protocol}});
    return parsed.origin + (parsed.pathname || "/");
  }} catch (error) {{
    return "[invalid-target]";
  }}
}}
function logDashboardAction(action, details={{}}) {{
  const entry = {{at:new Date().toISOString(), action, ...details}};
  console.info("[DASHBOARD-ACTION]", entry);
  try {{
    const key = "agentready.dashboard.actions.v1";
    const history = JSON.parse(localStorage.getItem(key) || "[]");
    history.push(entry);
    localStorage.setItem(key, JSON.stringify(history.slice(-200)));
  }} catch (error) {{ console.warn("[DASHBOARD-ACTION] Unable to persist action", {{action, error:String(error)}}); }}
}}
function resetV2InventoryCursor() {{
  v2InventoryCursor = null;
  console.debug("[FIX:v2-cursor] inventory cursor reset");
}}
function finishProgress(success) {{ const percent = success ? 100 : 0; progressBar.style.width = percent + "%"; progressBar.setAttribute("aria-valuenow", String(percent)); }}
function hintIcon(text) {{ const span = document.createElement("span"); span.className = "hint"; span.tabIndex = 0; span.setAttribute("role", "img"); span.setAttribute("aria-label", text); span.dataset.tooltip = text; span.textContent = "?"; return span; }}
function reportFilename(site) {{
  let slug = "site";
  try {{
    const parsed = new URL(site.includes("://") ? site : "https://" + site);
    slug = (parsed.hostname + parsed.pathname).replace(/[\/\\:*?"<>|#%&=+@!~'()\[\]{{}},;^`$\s]+/g, "-").replace(/^-+|-+$/g, "") || "site";
  }} catch (error) {{ console.info("Using fallback report filename", {{site}}); }}
  return "agentready-report-" + slug + ".html";
}}
function createReportActions(reportText, frame) {{
  const actions = document.createElement("div"); actions.className = "report-actions";
  const download = document.createElement("a"); download.href = URL.createObjectURL(new Blob([reportText], {{type:"text/html;charset=utf-8"}})); download.download = reportFilename(document.getElementById("url").value); download.textContent = translations[language.value].download_report; download.onclick = () => console.info("Downloading audit report", {{language:language.value, filename:download.download}});
  const print = document.createElement("a"); print.href = "#"; print.textContent = translations[language.value].print_report; print.onclick = (event) => {{ event.preventDefault(); console.info("Printing audit report", {{language:language.value}}); frame.contentWindow.print(); }};
  actions.append(download, hintIcon(translations[language.value].download_hint), print, hintIcon(translations[language.value].print_hint));
  return actions;
}}
const v2ProfileDefaults = {{quick:3, standard:25, deep:100}};
let v2LastProfile = document.getElementById("v2-profile").value;
function selectedV2MaxPages() {{ if (document.getElementById("v2-full-discovered")?.checked) return 25000; const value = Number(document.getElementById("v2-max-pages").value); return Number.isFinite(value) && value >= 0 ? value : 3; }}
function selectedV2Discovery() {{ return document.getElementById("v2-full-discovered")?.checked ? "crawl" : document.getElementById("v2-discovery").value; }}
function syncFullDiscoveredControl() {{ const full = document.getElementById("v2-full-discovered"); const limit = document.getElementById("v2-max-pages"); const depth = document.getElementById("v2-max-depth"); const discovery = document.getElementById("v2-discovery"); if (!full || !limit || !depth || !discovery) return; const applicable = discovery.value === "crawl"; if (!applicable) full.checked = false; full.disabled = !applicable; limit.disabled = full.checked; limit.setAttribute("aria-readonly", full.checked ? "true" : "false"); depth.disabled = full.checked; depth.setAttribute("aria-readonly", full.checked ? "true" : "false"); }}
function selectedV2Limits() {{ const value = document.getElementById("v2-max-depth").value.trim(); const full = document.getElementById("v2-full-discovered")?.checked; if (full) return {{check_limit:Number(document.getElementById("check-limit").value) || 0,max_depth:32}}; return value === "" ? {{check_limit:Number(document.getElementById("check-limit").value) || 0}} : {{check_limit:Number(document.getElementById("check-limit").value) || 0,max_depth:Math.max(0,Math.min(32,Number(value)))}}; }}
async function cancelActiveV2Job() {{
  const jobId = activeV2JobId;
  if (!jobId) return;
  activeV2JobId = null;
  localStorage.removeItem("agentready.dashboard.job.v2");
  try {{ await fetch("/v2/jobs/" + encodeURIComponent(jobId) + "/cancel", {{method:"POST"}}); console.info("[FIX:dashboard-progress] Previous audit job cancelled", {{job_id:jobId}}); }}
  catch (error) {{ console.warn("[FIX:dashboard-progress] Unable to cancel previous audit job", {{job_id:jobId, error:String(error)}}); }}
}}
function inventoryColumnLabel(column) {{ const labels = {{url:"URL",status:translations[language.value].v2_sort_status,depth:translations[language.value].v2_sort_depth,title:translations[language.value].v2_sort_title,anchor:translations[language.value].v2_sort_anchor,type:translations[language.value].v2_sort_type,resource:translations[language.value].v2_sort_resource}}; return labels[column] || column; }}
function syncV2ProfileBudget() {{
  const profile = document.getElementById("v2-profile").value;
  const pageLimit = document.getElementById("v2-max-pages");
  const previousDefault = v2ProfileDefaults[v2LastProfile];
  if (Number(pageLimit.value) === previousDefault || !pageLimit.value) {{
    pageLimit.value = String(v2ProfileDefaults[profile] || 25);
    saveDashboardState();
    console.info("[FIX:dashboard-crawl] Profile budget synchronized", {{profile, max_pages:Number(pageLimit.value)}});
  }}
  v2LastProfile = profile;
}}
function createReportFrame(reportText) {{
  const frame = document.createElement("iframe");
  frame.id = "report-frame";
  frame.title = translations[language.value].result;
  frame.srcdoc = reportText;
  frame.addEventListener("load", () => {{
    const reportDocument = frame.contentDocument;
    if (!reportDocument) {{
      console.warn("[FIX:dashboard-report] Report frame document unavailable");
      return;
    }}
    reportDocument.addEventListener("click", event => {{
      const link = event.target.closest("a[href^='#']");
      if (!link) return;
      const targetId = decodeURIComponent(link.getAttribute("href").slice(1));
      const target = targetId ? reportDocument.getElementById(targetId) : null;
      if (!target) return;
      event.preventDefault();
      target.scrollIntoView({{block:"start"}});
      console.info("[FIX:dashboard-report] Local report navigation", {{target:targetId}});
    }});
  }});
  return frame;
}}
function boundedV2ReportForStorage(report) {{
  if (!report) return null;
  try {{
    const serialized = JSON.stringify(report);
    if (serialized.length > 180000) {{
      console.warn("[FIX:dashboard-report] V2 context exceeds browser persistence limit", {{bytes:serialized.length}});
      return null;
    }}
    return report;
  }} catch (error) {{
    console.warn("[FIX:dashboard-report] Unable to prepare V2 context", {{error:String(error)}});
    return null;
  }}
}}
function saveReportState(reportText) {{
  try {{
    const v2Report = boundedV2ReportForStorage(window.agentreadyV2Report);
    localStorage.setItem(dashboardReportKey, JSON.stringify({{html:reportText, url:document.getElementById("url").value, preset:document.getElementById("preset").value, language:language.value, v2Report}}));
    console.info("[FIX:dashboard-report] Report persisted", {{preset:document.getElementById("preset").value, language:language.value, v2Context:Boolean(v2Report)}});
  }} catch (error) {{
    console.warn("[FIX:dashboard-report] Unable to persist report", {{error:String(error)}});
  }}
}}
function renderReport(reportText, persist=true) {{
  const frame = createReportFrame(reportText);
  const actions = createReportActions(reportText, frame);
  result.replaceChildren(actions, frame);
  showResult();
  finishProgress(true);
  if (persist) saveReportState(reportText);
  return frame;
}}
function restoreReportState() {{
  try {{
    const raw = localStorage.getItem(dashboardReportKey);
    if (!raw) return false;
    const state = JSON.parse(raw);
    if (!state || typeof state.html !== "string" || !state.html.includes("<html")) return false;
    // Invalidate reports generated before the Russian inventory heading was
    // localized; otherwise localStorage would keep showing stale report HTML.
    if (state.html.includes("Сводка инвентаря")) {{
      localStorage.removeItem(dashboardReportKey);
      console.info("[FIX:dashboard-report] Removed stale localized report", {{reason:"legacy inventory heading"}});
      return false;
    }}
    window.agentreadyV2Report = state.v2Report || null;
    // Browser persistence may omit the bounded copy for a large report, while
    // the embedded canonical v2 JSON is still present in the saved HTML.
    // Recover that exact report before deciding whether AI context is ready.
    if (!window.agentreadyV2Report) captureV2Report(state.html);
    if (window.agentreadyV2Report && window.agentreadyV2Report.run) loadSessionRobots(window.agentreadyV2Report.run.id);
    renderReport(state.html, false);
    const contextReady = state.preset !== "v2" || Boolean(window.agentreadyV2Report);
    setAiAvailability(Boolean(state.url && document.getElementById("url").value.trim() && contextReady));
    console.info("[FIX:dashboard-report] Report restored", {{preset:state.preset || "unknown", language:state.language || "unknown", v2Context:contextReady}});
    return true;
  }} catch (error) {{
    console.warn("[FIX:dashboard-report] Unable to restore report", {{error:String(error)}});
    return false;
  }}
}}
async function restoreActiveV2Job() {{
  if (!activeV2JobId) return;
  setProgress(35, translations[language.value].progress_fetch);
  try {{
    const status = await (await fetch("/v2/jobs/" + encodeURIComponent(activeV2JobId))).json();
    if (["running", "pending"].includes(status.status)) {{ setCrawlProgress(status.progress); runV2BackgroundPollOnly(); }}
    else if (status.status === "completed" && status.html) {{ captureV2Report(status.html); renderReport(status.html); activeV2JobId = null; localStorage.removeItem("agentready.dashboard.job.v2"); }}
  }} catch (error) {{ console.warn("[FIX:dashboard-progress] Unable to restore job", {{error:String(error)}}); }}
}}
function captureV2Report(reportText, required=false) {{
  try {{
    const doubleQuotedMarker = '<script id="agentready-v2-report" type="application/json">';
    const singleQuotedMarker = "<script id='agentready-v2-report' type='application/json'>";
    const v2Marker = reportText.includes(doubleQuotedMarker) ? doubleQuotedMarker : singleQuotedMarker;
    const start = reportText.indexOf(v2Marker);
    const end = reportText.indexOf("<" + "/script>", start);
    if (start >= 0 && end > start) {{
      window.agentreadyV2Report = JSON.parse(reportText.slice(start + v2Marker.length, end));
      const robotsPanel = document.getElementById("robots-simulation-panel");
      if (robotsPanel) robotsPanel.hidden = false;
      const sitemapPanel = document.getElementById("sitemap-reconciliation-panel");
      if (sitemapPanel) sitemapPanel.hidden = false;
      const graphPanel = document.getElementById("link-graph-panel");
      if (graphPanel) graphPanel.hidden = false;
      const duplicatePanel = document.getElementById("duplicate-clusters-panel");
      if (duplicatePanel) duplicatePanel.hidden = false;
      console.info("[FIX:ai-audit-context] Embedded audit report captured", {{bytes:reportText.length, findings:(window.agentreadyV2Report.findings || []).length}});
      loadSessionRobots(window.agentreadyV2Report.run && window.agentreadyV2Report.run.id);
      return window.agentreadyV2Report;
    }}
  }} catch (error) {{
    console.warn("[FIX:ai-audit-context] Unable to capture embedded audit report", {{error:String(error)}});
  }}
  if (required) {{
    window.agentreadyV2Report = null;
    console.warn("[FIX:ai-audit-context] Audit report context missing from HTML");
    return null;
  }}
  return window.agentreadyV2Report;
}}
async function loadSessionRobots(runId) {{
  const live = document.getElementById("robots-live");
  if (!live || !runId || live.dataset.userEdited === "true") return;
  try {{
    const response = await fetch("/v2/runs/" + encodeURIComponent(runId) + "/robots/source");
    const payload = await response.json();
    const found = response.ok && payload.found === true && typeof payload.robots === "string" && payload.robots.length > 0;
    if (live.dataset.userEdited === "true") return;
    live.value = found ? payload.robots : "";
    live.readOnly = found;
    live.setAttribute("aria-readonly", String(found));
    live.title = found ? translations[language.value].robots_live_discovered_hint : "";
    const status = document.getElementById("robots-simulation-status");
    if (found && status) status.textContent = translations[language.value].robots_live_loaded;
    console.info("[FIX:robots-session] Current robots policy loaded", {{run_id:runId, found, bytes:found ? payload.robots.length : 0}});
  }} catch (error) {{
    live.readOnly = false;
    live.removeAttribute("aria-readonly");
    console.warn("[FIX:robots-session] Unable to load current robots policy", {{run_id:runId, error:String(error)}});
  }}
}}
function resetSessionRobots() {{
  const live = document.getElementById("robots-live");
  if (!live) return;
  live.value = "";
  live.readOnly = false;
  live.removeAttribute("aria-readonly");
  live.title = "";
  live.dataset.userEdited = "false";
}}
async function runV2BackgroundPollOnly() {{
  while (activeV2JobId) {{ const jobId = activeV2JobId; await new Promise(resolve => setTimeout(resolve, 700)); if (!jobId) break; const status = await (await fetch("/v2/jobs/" + encodeURIComponent(jobId))).json(); setCrawlProgress(status.progress); if (status.status === "completed") {{ captureV2Report(status.html); renderReport(status.html); activeV2JobId = null; localStorage.removeItem("agentready.dashboard.job.v2"); }} else if (["failed","cancelled"].includes(status.status)) {{ activeV2JobId = null; localStorage.removeItem("agentready.dashboard.job.v2"); }} }}
}}
async function request(path, method="GET", body=null, html=false, showOutput=true, statusMessage="") {{
  if (showOutput) setProgress(8, translations[language.value].progress_start);
  const options = {{method, headers:{{"Content-Type":"application/json"}}}}; if (body) options.body = JSON.stringify(body);
  if (showOutput) setProgress(35, translations[language.value].progress_fetch);
  const catalogPath = ["/checks", "/seo/checks", "/mobile/checks"].includes(path);
  const response = await fetch(path + (catalogPath ? "?language=" + language.value : ""), options);
  if (!response.ok) throw new Error("HTTP " + response.status);
  if (html) {{
    if (showOutput) setProgress(78, translations[language.value].progress_render);
    const reportText = await response.text();
    captureV2Report(reportText, path === "/v2/audit/dashboard");
    return renderReport(reportText);
  }}
  const data = await response.json();
  if (showOutput) {{
    result.textContent = debugMode() ? JSON.stringify(data, null, 2) : (statusMessage || translations[language.value].progress_done);
    finishProgress(true);
  }}
  return data;
}}
async function runScan() {{
  if (!document.getElementById("url").value) {{ showResult(); result.textContent = translations[language.value].no_url; return; }}
  await cancelActiveV2Job();
  logDashboardAction("audit.start", {{target:safeDashboardTarget(document.getElementById("url").value), preset:document.getElementById("preset").value, profile:document.getElementById("v2-profile").value, max_pages:selectedV2MaxPages()}});
  if (aiConversationHistory.length && !(await startNewChat())) {{
    showResult(); finishProgress(false); result.textContent = translations[language.value].failed;
    console.warn("[FIX:dashboard-context] New audit stopped because the previous chat could not be archived");
    return;
  }}
  if (!aiConversationHistory.length) {{ logDashboardAction("ai.context.reset", {{reason:"new-audit"}}); }}
  window.agentreadyV2Report = null;
  resetSessionRobots();
  const preset = document.getElementById("preset").value;
  if (preset === "all") {{ await runAll(); return; }}
  if (preset === "seo") {{ await runSeo(); return; }}
  if (preset === "mobile") {{ await runMobile(); return; }}
  if (preset === "v2") {{ await runV2(); return; }}
  try {{ await request("/v2/audit/dashboard","POST",scanPayload(),true); setAiAvailability(true); }} catch (error) {{ setAiAvailability(false); finishProgress(false); result.textContent = translations[language.value].failed + ": " + error.message; }}
}}
async function runV2() {{
  if (!document.getElementById("url").value) {{ showResult(); result.textContent = translations[language.value].no_url; return; }}
  window.agentreadyV2Report = null;
  try {{
    const reportHtml = await runV2Background();
    renderReport(reportHtml);
    await loadV2Inventory();
    setAiAvailability(true);
  }} catch (error) {{
    setAiAvailability(false); finishProgress(false); result.textContent = translations[language.value].failed + ": " + error.message;
  }}
}}
async function runV2Background() {{
  const payload = {{url:document.getElementById("url").value,preset:"all",profile:document.getElementById("v2-profile").value,discovery_kind:selectedV2Discovery(),max_pages:selectedV2MaxPages(),limits:selectedV2Limits(),render:document.getElementById("v2-render").checked,timeout:Number(document.getElementById("timeout").value),language:language.value}};
  const response = await fetch("/v2/jobs", {{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(payload)}});
  if (!response.ok) {{ let detail = ""; try {{ const errorPayload = await response.json(); detail = errorPayload.detail || ""; }} catch (_) {{}} throw new Error("HTTP " + response.status + (detail ? ": " + detail : "")); }}
  const job = await response.json(); activeV2JobId = job.job_id; localStorage.setItem("agentready.dashboard.job.v2", activeV2JobId); setCrawlProgress({{phase:"queued",fetched:0,discovered:0}});
  while (activeV2JobId) {{
    const jobId = activeV2JobId;
    await new Promise(resolve => setTimeout(resolve, 700));
    if (!jobId) break;
    const status = await (await fetch("/v2/jobs/" + encodeURIComponent(jobId))).json(); setCrawlProgress(status.progress);
    if (status.status === "completed") {{ const html = status.html; captureV2Report(html); activeV2JobId = null; localStorage.removeItem("agentready.dashboard.job.v2"); return html; }}
    if (["failed","cancelled"].includes(status.status)) throw new Error(status.error || status.status);
  }}
  throw new Error("job lost");
}}
let v2InventoryKind = "pages";
let v2InventoryCursor = null;
let v2InventoryItems = [];
let v2InventoryCounts = {{}};
let v2InventoryOverviewRunId = null;
function dashboardRunId() {{
  const report = window.agentreadyV2Report;
  return report && report.run ? report.run.id : null;
}}
async function simulateRobots() {{
  const report = window.agentreadyV2Report;
  const status = document.getElementById("robots-simulation-status");
  const output = document.getElementById("robots-simulation-result");
  const runId = report && report.run ? report.run.id : null;
  if (!runId) {{ status.textContent = translations[language.value].robots_empty; return; }}
  const userAgents = document.getElementById("robots-user-agents").value.split(",").map(value => value.trim()).filter(Boolean);
  try {{
    status.textContent = translations[language.value].progress_fetch;
    const response = await fetch("/v2/runs/" + encodeURIComponent(runId) + "/robots/simulate", {{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{live_robots:document.getElementById("robots-live").value,proposed_robots:document.getElementById("robots-proposed").value,user_agents:userAgents.length ? userAgents : ["*"]}})}});
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    const t = translations[language.value];
    const rows = data.newly_blocked.map(url => "<tr><td>" + escapeHtml(t.robots_newly_blocked) + "</td><td>" + escapeHtml(url) + "</td></tr>").join("") + data.newly_allowed.map(url => "<tr><td>" + escapeHtml(t.robots_newly_allowed) + "</td><td>" + escapeHtml(url) + "</td></tr>").join("");
    output.innerHTML = "<p>" + escapeHtml(t.robots_result) + "</p><table><thead><tr><th>" + escapeHtml(t.robots_change) + "</th><th>" + escapeHtml(t.robots_url) + "</th></tr></thead><tbody>" + (rows || "<tr><td colspan='2'>" + escapeHtml(t.robots_no_changes) + "</td></tr>") + "</tbody></table>";
    status.textContent = translations[language.value].robots_result;
  }} catch (error) {{ status.textContent = translations[language.value].robots_result + ": " + error.message; }}
}}

async function reconcileSitemap() {{
  const status = document.getElementById("sitemap-reconciliation-status");
  const output = document.getElementById("sitemap-reconciliation-result");
  const runId = dashboardRunId();
  if (!runId) {{ status.textContent = translations[language.value].run_audit_first; return; }}
  const documents = document.getElementById("sitemap-reconciliation-xml").value.split(/\n\s*\n/).map(value => value.trim()).filter(Boolean);
  const origin = document.getElementById("sitemap-reconciliation-origin").value.trim();
  try {{
    const response = await fetch("/v2/runs/" + encodeURIComponent(runId) + "/sitemap/reconcile", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{documents, origin, category:"sitemap_only", limit:100}})}});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "request failed");
    document.getElementById("sitemap-reconciliation-panel").hidden = false;
    const categoryLabels = {{sitemap_only: language.value === "ru" ? "Только sitemap" : "Sitemap only", crawl_only: language.value === "ru" ? "Только обход" : "Crawl only", broken: language.value === "ru" ? "Битые" : "Broken", redirects: language.value === "ru" ? "Перенаправления" : "Redirects", blocked: language.value === "ru" ? "Заблокированные" : "Blocked", noindex: language.value === "ru" ? "Noindex" : "Noindex", noncanonical: language.value === "ru" ? "Неканонические" : "Non-canonical", out_of_scope: language.value === "ru" ? "Вне области" : "Out of scope", orphan_candidate: language.value === "ru" ? "Кандидаты в сироты" : "Orphan candidates"}};
    output.innerHTML = Object.entries(payload.classifications || {{}}).map(([category, count]) => `<button type="button" class="secondary" data-sitemap-category="${{escapeHtml(category)}}" onclick="loadSitemapCategory(this.dataset.sitemapCategory)">${{escapeHtml(categoryLabels[category] || category)}}: ${{count}}</button>`).join(" ") + `<pre>${{escapeHtml(JSON.stringify(payload.items || [], null, 2))}}</pre>`;
    window.sitemapReconciliation = payload;
    status.textContent = translations[language.value].sitemap_reconcile_complete;
    logDashboardAction("sitemap.reconcile", {{run_id:runId, sitemap_id:payload.sitemap_id, classifications:payload.classifications}});
  }} catch (error) {{ status.textContent = translations[language.value].sitemap_reconcile_failed + ": " + error.message; }}
}}

async function validateCustomRules() {{
  const status = document.getElementById("custom-rules-status");
  try {{
    const response = await fetch("/v2/custom-rules/validate", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{rules:document.getElementById("custom-rules-document").value}})}});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "validation failed");
    document.getElementById("custom-rules-result").textContent = JSON.stringify(payload, null, 2);
    status.textContent = translations[language.value].custom_rules_valid;
  }} catch (error) {{ status.textContent = translations[language.value].custom_rules_validation_failed + ": " + error.message; }}
}}
async function debugCustomRules() {{
  const status = document.getElementById("custom-rules-status");
  try {{
    const runId = dashboardRunId();
    const target = document.getElementById("url").value;
    const response = await fetch("/v2/custom-rules/debug", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{rules:document.getElementById("custom-rules-document").value, url:target, url_key:target, run_id:runId}})}});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "debug failed");
    document.getElementById("custom-rules-result").textContent = JSON.stringify(payload, null, 2);
    status.textContent = translations[language.value].custom_rules_preview_complete;
  }} catch (error) {{ status.textContent = translations[language.value].custom_rules_preview_failed + ": " + error.message; }}
}}

function renderLinkGraphVisual(payload) {{
  const host = document.getElementById("link-graph-visual");
  const t = translations[language.value];
  const items = (payload.items || []).slice(0, 100);
  if (!items.length) {{ host.innerHTML = `<p>${{escapeHtml(t.graph_no_edges)}}</p>`; return; }}
  const width = 760, height = 300, pad = 24;
  const maxAuthority = Math.max(...items.map(item => Number(item.authority) || 0), 0.0001);
  const points = items.map((item, index) => {{
    const columns = Math.max(1, Math.ceil(Math.sqrt(items.length)));
    const row = Math.floor(index / columns), column = index % columns;
    const x = pad + (width - 2 * pad) * ((column + 0.5) / columns);
    const rows = Math.ceil(items.length / columns);
    const y = pad + (height - 2 * pad) * ((row + 0.5) / rows);
    const radius = 5 + 12 * Math.sqrt((Number(item.authority) || 0) / maxAuthority);
    const color = item.disconnected ? "#64748b" : (item.dead_end ? "#d97706" : "#0f766e");
    return {{...item, x, y, radius, color}};
  }});
  const byUrl = new Map(points.map(point => [point.url, point]));
  const edges = (payload.edges || []).filter(edge => byUrl.has(edge.source) && byUrl.has(edge.target)).slice(0, 500);
  const lines = edges.map(edge => {{ const source = byUrl.get(edge.source), target = byUrl.get(edge.target); return `<line x1="${{source.x.toFixed(1)}}" y1="${{source.y.toFixed(1)}}" x2="${{target.x.toFixed(1)}}" y2="${{target.y.toFixed(1)}}" class="link-graph-edge" />`; }}).join("");
  const nodes = points.map(point => `<g class="link-graph-node" tabindex="0" role="button" aria-label="${{escapeHtml(point.url)}}" data-url="${{escapeHtml(point.url)}}" onclick="loadLinkGraphNode(this.dataset.url)" onkeydown="if(event.key==='Enter'||event.key===' '){{event.preventDefault();loadLinkGraphNode(this.dataset.url)}}"><circle cx="${{point.x.toFixed(1)}}" cy="${{point.y.toFixed(1)}}" r="${{point.radius.toFixed(1)}}" fill="${{point.color}}"><title>${{escapeHtml(point.url)}} — ${{Number(point.authority || 0).toFixed(4)}}</title></circle></g>`).join("");
  host.innerHTML = `<svg viewBox="0 0 ${{width}} ${{height}}" width="100%" height="300" role="img" aria-label="${{escapeHtml(t.graph_visual)}}">${{lines}}${{nodes}}</svg>`;
}}

async function loadLinkGraph() {{
  const status = document.getElementById("link-graph-status");
  const output = document.getElementById("link-graph-result");
  const runId = dashboardRunId();
  if (!runId) {{ status.textContent = translations[language.value].run_audit_first; return; }}
  const deadEnd = document.getElementById("link-graph-dead-end").checked;
  const disconnected = document.getElementById("link-graph-disconnected").checked;
  const nodeCapValue = document.getElementById("link-graph-node-cap").value;
  const allNodes = nodeCapValue === "all";
  const nodeCap = allNodes ? 1000 : Math.min(100, Math.max(25, Number(nodeCapValue) || 100));
  const minAuthority = Math.min(1, Math.max(0, Number(document.getElementById("link-graph-min-authority").value) || 0));
  const depth = document.getElementById("link-graph-depth").value;
  const query = new URLSearchParams({{limit:String(nodeCap), dead_end:String(deadEnd), disconnected:String(disconnected)}});
  try {{ query.set("origin", new URL(safeDashboardTarget(document.getElementById("url").value)).origin); }} catch (_) {{ /* server returns a localized validation error */ }}
  console.info("[FIX:link-graph-filters] Loading graph projection", {{run_id:runId, dead_end:deadEnd, disconnected}});
  try {{
    const response = await fetch("/v2/runs/" + encodeURIComponent(runId) + "/graph?" + query.toString());
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "graph request failed");
    if (allNodes) {{
      let cursor = payload.next_cursor;
      while (cursor) {{
        const pageResponse = await fetch("/v2/runs/" + encodeURIComponent(runId) + "/graph?" + new URLSearchParams({{...Object.fromEntries(query), cursor}}).toString());
        const page = await pageResponse.json();
        if (!pageResponse.ok) throw new Error(page.detail || "graph page request failed");
        payload.items = (payload.items || []).concat(page.items || []);
        cursor = page.next_cursor;
      }}
      payload.next_cursor = null;
    }}
    document.getElementById("link-graph-panel").hidden = false;
    payload.items = (payload.items || []).filter(item => (Number(item.authority) || 0) >= minAuthority && (depth === "all" || (depth === "3+" ? Number(item.depth) >= 3 : Number(item.depth) === Number(depth))));
    const t = translations[language.value];
    output.innerHTML = `<p>${{escapeHtml(t.graph_algorithm)}}: ${{escapeHtml(payload.algorithm_version || "")}}</p><table><thead><tr><th>${{escapeHtml(t.graph_url)}}</th><th>${{escapeHtml(t.graph_in)}}</th><th>${{escapeHtml(t.graph_out)}}</th><th>${{escapeHtml(t.graph_authority)}}</th></tr></thead><tbody>${{(payload.items || []).map(item => `<tr><td><button type="button" class="text-link" onclick="loadLinkGraphNode(this.dataset.url)" data-url="${{escapeHtml(item.url)}}">${{escapeHtml(item.url)}}</button></td><td>${{item.inlinks}}</td><td>${{item.outlinks}}</td><td>${{item.authority}}</td></tr>`).join("")}}</tbody></table>`;
    renderLinkGraphVisual(payload);
    status.textContent = t.graph_loaded.replace("{{loaded}}", String((payload.items || []).length)).replace("{{total}}", String(payload.total || 0));
    logDashboardAction("graph.load", {{run_id:runId, nodes:(payload.items || []).length, fingerprint:payload.fingerprint}});
  }} catch (error) {{ status.textContent = translations[language.value].graph_failed + ": " + error.message; }}
}}
async function loadLinkGraphNode(url) {{
  const runId = dashboardRunId();
  if (!runId) return;
  const response = await fetch("/v2/runs/" + encodeURIComponent(runId) + "/graph/node?url=" + encodeURIComponent(url));
  const payload = await response.json();
  if (response.ok) {{ const t = translations[language.value]; document.getElementById("link-graph-status").textContent = `${{payload.node.url}}: ${{payload.inbound.length}} ${{t.graph_node_inbound}}, ${{payload.outbound.length}} ${{t.graph_node_outbound}}`; }}
}}

async function loadDuplicateClusters() {{
  const status = document.getElementById("duplicate-clusters-status");
  const output = document.getElementById("duplicate-clusters-result");
  const runId = dashboardRunId();
  if (!runId) {{ status.textContent = translations[language.value].run_audit_first; return; }}
  const kind = document.getElementById("duplicate-clusters-kind").value;
  try {{
    const response = await fetch("/v2/runs/" + encodeURIComponent(runId) + "/duplicates?kind=" + encodeURIComponent(kind) + "&limit=100");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "duplicate query failed");
    document.getElementById("duplicate-clusters-panel").hidden = false;
    const duplicateKindLabel = item => item.near_duplicate ? translations[language.value].duplicate_near.toLowerCase() : translations[language.value].duplicate_exact.toLowerCase();
    output.innerHTML = (payload.items || []).map(item => `<article class="panel"><h3>${{escapeHtml(item.cluster_id)}} (${{escapeHtml(duplicateKindLabel(item))}})</h3><ul>${{item.members.map(member => `<li>${{escapeHtml(member.url)}} — ${{member.similarity}}</li>`).join("")}}</ul></article>`).join("");
    status.textContent = translations[language.value].duplicates_loaded.replace("{{loaded}}", String((payload.items || []).length)).replace("{{total}}", String(payload.total || 0));
    logDashboardAction("duplicates.load", {{run_id:runId, clusters:(payload.items || []).length, fingerprint:payload.fingerprint}});
  }} catch (error) {{ status.textContent = translations[language.value].duplicate_failed + ": " + error.message; }}
}}

async function createDashboardProject() {{
  const status = document.getElementById("projects-status");
  try {{
    const response = await fetch("/v2/projects", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{project_id:document.getElementById("project-id").value.trim(), name:document.getElementById("project-name").value.trim(), target:safeDashboardTarget(document.getElementById("url").value), default_profile:document.getElementById("v2-profile").value}})}});
    const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || "project request failed");
    status.textContent = translations[language.value].project_saved; loadDashboardProjects();
  }} catch (error) {{ status.textContent = translations[language.value].project_failed + ": " + error.message; }}
}}
async function loadDashboardProjects() {{
  const status = document.getElementById("projects-status");
  const output = document.getElementById("projects-result");
  try {{
    const projectsResponse = await fetch("/v2/projects");
    const projectsPayload = await projectsResponse.json().catch(() => null);
    if (!projectsResponse.ok) throw new Error((projectsPayload && projectsPayload.detail) || "projects request failed (HTTP " + projectsResponse.status + ")");
    if (!Array.isArray(projectsPayload)) throw new Error("projects response is not a list");
    const projects = projectsPayload;
    const project = projects.find(item => item.project_id === document.getElementById("project-id").value.trim());
    if (!project) {{ output.textContent = JSON.stringify(projects, null, 2); status.textContent = translations[language.value].projects_count.replace("{{count}}", String(projects.length)); return; }}
    const response = await fetch("/v2/projects/" + encodeURIComponent(project.project_id) + "/runs?limit=50");
    const history = await response.json(); if (!response.ok) throw new Error(history.detail || translations[language.value].history_failed);
    output.innerHTML = `<p>${{escapeHtml(project.name)}} — ${{escapeHtml(project.target)}}</p><p class="section-hint">${{escapeHtml(translations[language.value].history_explanation)}}</p><table><thead><tr><th>${{escapeHtml(translations[language.value].history_run)}}</th><th>${{escapeHtml(translations[language.value].history_trigger)}}</th><th>${{escapeHtml(translations[language.value].history_baseline)}}</th></tr></thead><tbody>${{(history.items || []).map(item => `<tr><td>${{escapeHtml(item.run_id)}}</td><td>${{escapeHtml(item.trigger || "—")}}</td><td>${{item.baseline_run_id ? escapeHtml(translations[language.value].history_baseline_yes) : escapeHtml(translations[language.value].history_baseline_no)}}</td></tr>`).join("")}}</tbody></table>`;
    status.textContent = translations[language.value].runs_count.replace("{{count}}", String(history.total || 0));
  }} catch (error) {{ status.textContent = translations[language.value].history_failed + ": " + error.message; }}
}}
async function loadSitemapCategory(category) {{
  const state = window.sitemapReconciliation;
  const runId = dashboardRunId();
  if (!state || !runId) return;
  const response = await fetch("/v2/runs/" + encodeURIComponent(runId) + "/sitemap/reconcile", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{documents:[document.getElementById("sitemap-reconciliation-xml").value], origin:document.getElementById("sitemap-reconciliation-origin").value, category, limit:100}})}});
  const payload = await response.json();
  document.getElementById("sitemap-reconciliation-result").insertAdjacentHTML("beforeend", `<pre data-sitemap-items="${{escapeHtml(category)}}">${{escapeHtml(JSON.stringify(payload.items || [], null, 2))}}</pre>`);
}}
async function loadV2Inventory(kind=null, cursor=null) {{
  const report = window.agentreadyV2Report;
  const runId = report && report.run ? report.run.id : null;
  const panel = document.getElementById("v2-inventory-panel");
  const container = document.getElementById("v2-inventory");
  if (!runId) {{ panel.hidden = false; container.textContent = translations[language.value].v2_inventory_empty; return; }}
  panel.hidden = false;
  try {{
    const status = document.getElementById("v2-inventory-status");
    status.textContent = translations[language.value].v2_inventory_loading;
    if (v2InventoryOverviewRunId !== runId) {{
      const overview = await (await fetch("/v2/runs/" + encodeURIComponent(runId) + "/overview")).json();
      v2InventoryCounts = overview.inventory || {{}};
      v2InventoryOverviewRunId = runId;
    }}
    if (cursor === null) resetV2InventoryCursor();
    if (kind) {{ v2InventoryKind = kind; document.getElementById("v2-inventory-kind").value = kind; }}
    if (cursor !== null) v2InventoryCursor = cursor;
    const limit = Number(document.getElementById("v2-inventory-limit").value) || 100;
    const query = new URLSearchParams({{limit:String(limit),sort_by:document.getElementById("v2-inventory-sort").value,descending:String(document.getElementById("v2-inventory-desc").checked)}});
    const search = document.getElementById("v2-inventory-filter").value.trim();
    if (search) query.set("search", search);
    if (v2InventoryCursor) query.set("cursor", v2InventoryCursor);
    const response = await fetch("/v2/runs/" + encodeURIComponent(runId) + "/inventory/" + encodeURIComponent(v2InventoryKind) + "?" + query);
    if (!response.ok) throw new Error("HTTP " + response.status);
    const page = await response.json();
    v2InventoryItems = page.items || [];
    logDashboardAction("inventory.load", {{run_id:runId, kind:v2InventoryKind, rows:v2InventoryItems.length, has_next:Boolean(page.next_cursor)}});
    const counts = Object.entries(v2InventoryCounts).map(([name, count]) => `<button type="button" class="secondary" onclick="loadV2Inventory('${{name.replace('_','-')}}')">${{name}} (${{count}})</button>`).join(" ");
    const selectedColumns = [...document.getElementById("v2-inventory-columns").selectedOptions].map(option => option.value);
    const availableColumns = [...new Set(v2InventoryItems.flatMap(item => Object.keys(item)))];
    const columns = (selectedColumns.length ? selectedColumns : availableColumns).filter(column => availableColumns.includes(column)).slice(0, 12);
    container.innerHTML = `<p>${{counts}}</p><table><thead><tr>${{columns.map(column => `<th scope="col">${{escapeHtml(inventoryColumnLabel(column))}}</th>`).join("")}}</tr></thead><tbody>${{v2InventoryItems.map((item, index) => `<tr data-v2-inventory-row="${{index}}">${{columns.map(column => `<td>${{escapeHtml(typeof item[column] === "object" ? JSON.stringify(item[column]) : (item[column] ?? ""))}}</td>`).join("")}}</tr>`).join("")}}</tbody></table>`;
    const next = document.getElementById("v2-inventory-next");
    next.hidden = !page.next_cursor;
    next.dataset.cursor = page.next_cursor || "";
    status.textContent = translations[language.value].v2_inventory_page.replace("{{count}}", String(v2InventoryItems.length));
  }} catch (error) {{
    container.textContent = translations[language.value].v2_inventory_error + ": " + error.message;
    document.getElementById("v2-inventory-status").textContent = translations[language.value].v2_inventory_error;
  }}
}}
function loadNextV2Inventory() {{
  const cursor = document.getElementById("v2-inventory-next").dataset.cursor;
  if (cursor) {{ logDashboardAction("inventory.next_page", {{kind:v2InventoryKind}}); loadV2Inventory(null, cursor); }}
}}
function filterV2Inventory() {{
  const query = document.getElementById("v2-inventory-filter").value.trim().toLowerCase();
  document.querySelectorAll("[data-v2-inventory-row]").forEach(row => {{
    row.hidden = query && !row.textContent.toLowerCase().includes(query);
  }});
}}
async function saveV2InventoryView() {{
  const report = window.agentreadyV2Report;
  const runId = report && report.run ? report.run.id : null;
  const status = document.getElementById("v2-inventory-status");
  if (!runId) {{ status.textContent = translations[language.value].v2_inventory_empty; return; }}
  const viewId = "dashboard-" + v2InventoryKind + "-" + runId.slice(0, 12);
  try {{
    const response = await fetch("/v2/saved-views", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{id:viewId,name:"Dashboard " + v2InventoryKind,run_id:runId,kind:v2InventoryKind,limit:Number(document.getElementById("v2-inventory-limit").value)||100,search:document.getElementById("v2-inventory-filter").value.trim(),sort_by:document.getElementById("v2-inventory-sort").value,descending:document.getElementById("v2-inventory-desc").checked}})}});
    if (!response.ok) throw new Error("HTTP " + response.status);
    status.textContent = "Saved view: " + viewId;
    await loadSavedV2Views();
  }} catch (error) {{
    status.textContent = translations[language.value].v2_inventory_error + ": " + error.message;
  }}
}}
function escapeHtml(value) {{
  return String(value).replace(/[&<>"']/g, character => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[character]));
}}
function combinedReportDocument(geoText, seoText) {{
  const geo = new DOMParser().parseFromString(geoText, "text/html");
  const seo = new DOMParser().parseFromString(seoText, "text/html");
  function namespaceReport(root, prefix) {{
    const ids = new Map();
    root.querySelectorAll("[id]").forEach(element => {{
      const nextId = prefix + "-" + element.id;
      ids.set(element.id, nextId);
      element.id = nextId;
    }});
    ["for", "aria-controls", "aria-labelledby", "aria-describedby"].forEach(attribute => {{
      root.querySelectorAll("[" + attribute + "]").forEach(element => {{
        const value = element.getAttribute(attribute);
        element.setAttribute(attribute, value.split(/\s+/).map(item => ids.get(item) || item).join(" "));
      }});
    }});
    root.querySelectorAll("a[href^='#']").forEach(link => {{
      const target = link.getAttribute("href").slice(1);
      if (ids.has(target)) link.setAttribute("href", "#" + ids.get(target));
    }});
  }}
  if (geo.body) namespaceReport(geo.body, "geo");
  if (seo.body) namespaceReport(seo.body, "seo");
  [geo.body, seo.body].forEach(body => body && body.querySelectorAll("script").forEach(script => script.remove()));
  const styles = Array.from(document.querySelectorAll("style")).concat(
    Array.from(geo.querySelectorAll("style")),
    Array.from(seo.querySelectorAll("style"))
  ).map(style => style.outerHTML).join("");
  const controller = `<script>(function(){{const reports=[...document.querySelectorAll('[data-report-instance]')];reports.forEach(report=>{{const selector=report.querySelector("select[id$='-lang']"),mains=[...report.querySelectorAll('main[data-lang]')],skip=report.querySelector('.skip-link');if(!selector||!mains.length)return;function setLang(value){{document.documentElement.lang=value;mains.forEach(main=>main.hidden=main.dataset.lang!==value);const active=mains.find(main=>main.dataset.lang===value);if(active&&skip)skip.href='#'+active.id;}}selector.addEventListener('change',()=>setLang(selector.value));setLang(selector.value);}});window.addEventListener('beforeprint',()=>document.querySelectorAll('details').forEach(detail=>detail.open=true));}})();</` + "script>";
  return "<!doctype html><html lang='" + language.value + "'><head><meta charset='utf-8'>" + styles + "</head><body>" +
    "<main><h1>AgentReady combined audit</h1>" +
    "<section data-report-instance='geo'><h2>" + translations[language.value].preset_ai_search + "</h2>" + (geo.body ? geo.body.innerHTML : "") + "</section>" +
    "<section data-report-instance='seo'><h2>" + translations[language.value].preset_seo + "</h2>" + (seo.body ? seo.body.innerHTML : "") + "</section>" +
    "</main>" + controller + "</body></html>";
}}
async function runAll() {{
  if (!document.getElementById("url").value) {{ showResult(); result.textContent = translations[language.value].no_url; return; }}
  window.agentreadyV2Report = null;
  try {{
    const geoText = await runV2Background();
    const seoFrame = await request("/v2/seo/audit/dashboard","POST",{{url:document.getElementById("url").value,profile:document.getElementById("v2-profile").value,crawl:true,max_pages:selectedV2MaxPages(),language:language.value,checks:null,timeout:Number(document.getElementById("timeout").value),recommendation_limit:Number(document.getElementById("recommendations").value),limits:selectedV2Limits()}},true);
    const combined = combinedReportDocument(geoText, seoFrame.srcdoc);
    renderReport(combined); setAiAvailability(true);
  }} catch (error) {{ setAiAvailability(false); finishProgress(false); result.textContent = translations[language.value].failed + ": " + error.message; }}
}}
async function runSeo() {{
  if (!document.getElementById("url").value) {{ showResult(); result.textContent = translations[language.value].no_url; return; }}
  window.agentreadyV2Report = null;
  try {{ await request("/v2/seo/audit/dashboard","POST",{{url:document.getElementById("url").value,profile:document.getElementById("v2-profile").value,crawl:true,max_pages:selectedV2MaxPages(),language:language.value,checks:selectedChecks(),timeout:Number(document.getElementById("timeout").value),recommendation_limit:Number(document.getElementById("recommendations").value),limits:selectedV2Limits()}},true); setAiAvailability(true); }} catch (error) {{ setAiAvailability(false); finishProgress(false); result.textContent = translations[language.value].failed + ": " + error.message; }}
}}
async function runMobile() {{
  if (!document.getElementById("url").value) {{ showResult(); result.textContent = translations[language.value].no_url; return; }}
  window.agentreadyV2Report = null;
  console.info("Running mobile audit from dashboard", {{url:document.getElementById("url").value}});
  try {{ await request("/v2/mobile/audit/dashboard","POST",{{urls:[document.getElementById("url").value],language:language.value,timeout:Number(document.getElementById("timeout").value),recommendation_limit:Number(document.getElementById("recommendations").value)}},true); setAiAvailability(true); }} catch (error) {{ setAiAvailability(false); finishProgress(false); result.textContent = translations[language.value].failed + ": " + error.message; }}
}}
async function runHealth() {{ try {{ const response = await fetch("/healthz"); if (!response.ok) throw new Error("HTTP " + response.status); console.info("[FIX:dashboard-progress] Service health checked without resetting audit progress"); }} catch (error) {{ console.warn("[FIX:dashboard-progress] Health check failed", {{error:String(error)}}); }} }}
async function openAiCredentials() {{
  const dialog = document.getElementById("ai-credentials-dialog");
  const result = document.getElementById("ai-credentials-result");
  ensureAiPricingFields();
  result.textContent = "";
  try {{
    const response = await fetch("/ai/status");
    const data = await response.json();
    renderAiProviders(data);
  }} catch (error) {{ result.textContent = translations[language.value].failed + ": " + error.message; }}
  dialog.showModal();
}}
function ensureAiPricingFields() {{
  if (document.getElementById("ai-provider-input-price")) return;
  const anchor = document.getElementById("ai-provider-chat-only");
  if (!anchor || !anchor.parentElement) return;
  const grid = document.createElement("div");
  grid.className = "form-grid four";
  grid.style.marginTop = "14px";
  [["ai-provider-input-price", translations[language.value].ai_input_price], ["ai-provider-output-price", translations[language.value].ai_output_price]].forEach(([id, labelText]) => {{
    const wrapper = document.createElement("div");
    const label = document.createElement("label");
    label.htmlFor = id;
    label.textContent = labelText;
    const input = document.createElement("input");
    input.id = id;
    input.type = "text";
    input.inputMode = "decimal";
    input.dataset.decimal = "true";
    input.min = "0";
    input.step = "0.000001";
    input.value = "0";
    wrapper.append(label, input);
    grid.append(wrapper);
  }});
  grid.querySelectorAll("[data-decimal]").forEach(element => element.addEventListener("blur", normalizeDecimalInput));
  anchor.parentElement.before(grid);
}}
function renderAiProviders(data) {{
  ensureAiPricingFields();
  window.aiProviders = data.providers || [];
  if (data.model) renderModelCatalog([{{id:data.model,capabilities:["other"]}}], data.model);
  const select = document.getElementById("ai-provider");
  const chatSelect = document.getElementById("ai-chat-provider");
  select.replaceChildren();
  chatSelect.replaceChildren();
  const newOption = document.createElement("option"); newOption.value = ""; newOption.textContent = translations[language.value].ai_new; select.append(newOption);
  (data.providers || []).forEach(provider => {{
    const option = document.createElement("option"); option.value = provider.id; option.textContent = provider.name + " (" + provider.base_url + ")";
    select.append(option);
    const chatOption = option.cloneNode(true); chatSelect.append(chatOption);
  }});
  select.dataset.active = data.active_provider || "";
  const savedProvider = restoredDashboardState["ai-provider"];
  const savedChatProvider = restoredDashboardState["ai-chat-provider"];
  select.value = (savedProvider && [...select.options].some(option => option.value === savedProvider)) ? savedProvider : (data.active_provider || "");
  chatSelect.value = (savedChatProvider && [...chatSelect.options].some(option => option.value === savedChatProvider)) ? savedChatProvider : (data.active_provider || "");
  document.getElementById("ai-enable").checked = Boolean(data.enabled && data.transport_enabled);
  selectAiProvider();
}}
function setProviderBusy(busy, message="") {{
  const dialog = document.getElementById("ai-credentials-dialog");
  dialog.classList.toggle("provider-busy", busy);
  ["ai-provider-model-refresh","ai-provider","ai-chat-provider"].forEach(id => {{
    const element = document.getElementById(id);
    if (element) element.disabled = busy || (id === "ai-provider-model-refresh" && !selectedAiProvider());
  }});
  if (message) document.getElementById("ai-credentials-result").textContent = message;
}}
function newAiProvider() {{
  const select = document.getElementById("ai-provider"); select.value = "";
  document.getElementById("ai-provider-name").value = "";
  document.getElementById("ai-provider-url").value = "";
  document.getElementById("ai-key").value = "";
  document.getElementById("ai-provider-input-price").value = "0";
  document.getElementById("ai-provider-output-price").value = "0";
  document.getElementById("ai-provider-chat-only").checked = false;
  document.getElementById("ai-chat-provider").value = "";
  document.getElementById("ai-enable").checked = false;
  document.getElementById("ai-provider-model-refresh").disabled = true;
  renderModelCatalog([], null);
}}
function selectedAiProvider() {{
  return (window.aiProviders || []).find(provider => provider.id === document.getElementById("ai-provider").value);
}}
function selectAiProvider() {{
  const provider = selectedAiProvider();
  if (!provider) {{ newAiProvider(); return; }}
  document.getElementById("ai-provider-name").value = provider.name;
  document.getElementById("ai-provider-url").value = provider.base_url;
  document.getElementById("ai-key").value = "";
  document.getElementById("ai-provider-input-price").value = normalizeDecimalString(provider.input_price_per_million ?? 0);
  document.getElementById("ai-provider-output-price").value = normalizeDecimalString(provider.output_price_per_million ?? 0);
  document.getElementById("ai-provider-chat-only").checked = Boolean(provider.chat_only);
  document.getElementById("ai-provider-model-refresh").disabled = false;
  renderModelCatalog([], null);
  loadAiModels(provider.id, restoredDashboardState["ai-model"] || provider.model);
  saveDashboardState();
}}
function selectChatProvider() {{
  const provider = (window.aiProviders || []).find(item => item.id === document.getElementById("ai-chat-provider").value);
  if (!provider) {{ renderModelCatalog([], null); saveDashboardState(); return; }}
  loadAiModels(provider.id, document.getElementById("ai-model").value || provider.model);
  saveDashboardState();
}}
async function loadAiTools() {{
  try {{
    const response = await fetch("/ai/tools?language=" + encodeURIComponent(language.value));
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    ["ai-skill","ai-mcp-tool"].forEach(id => {{
      const selected = id === "ai-skill" ? data.skills : data.mcp_tools;
      [...document.getElementById(id).options].forEach(option => option.selected = selected.includes(option.value));
    }});
    updateAiContextChips();
  }} catch (error) {{
    console.warn("Unable to load AI tools settings", {{error:String(error)}});
  }}
}}
async function saveAiTools() {{
  try {{
    const response = await fetch("/ai/tools", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{skills:selectedValues("ai-skill"),mcp_tools:selectedValues("ai-mcp-tool")}})}});
    if (!response.ok) throw new Error("HTTP " + response.status);
  }} catch (error) {{
    console.warn("Unable to save AI tools settings", {{error:String(error)}});
  }}
}}
let aiPromptLibrary = [];
let aiPromptEditingId = null;
let aiPromptEditingMode = null;
async function loadPromptLibrary() {{
  try {{
    const response = await fetch("/ai/prompts?language=" + encodeURIComponent(language.value));
    if (!response.ok) throw new Error("HTTP " + response.status);
    aiPromptLibrary = (await response.json()).prompts || [];
    const select = document.getElementById("ai-prompt-library");
    select.replaceChildren();
    aiPromptLibrary.forEach(item => {{
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.title + " (" + item.mode + ")";
      select.append(option);
    }});
  }} catch (error) {{
    console.warn("Unable to load prompt library", {{error:String(error)}});
  }}
}}
function applyPrompt() {{
  const prompt = aiPromptLibrary.find(item => item.id === document.getElementById("ai-prompt-library").value);
  if (!prompt) return;
  aiPromptEditingId = prompt.id;
  aiPromptEditingMode = prompt.mode;
  document.getElementById("ai-prompt-title").value = prompt.title;
  document.getElementById("ai-mode").value = prompt.mode;
  document.getElementById("ai-message").value = prompt.prompt;
  updateAiModeHint();
  saveDashboardState();
}}
async function loadSavedV2Views() {{
  const select = document.getElementById("v2-saved-view");
  if (!select) return;
  try {{
    const response = await fetch("/v2/saved-views");
    if (!response.ok) throw new Error("HTTP " + response.status);
    const views = await response.json();
    select.innerHTML = '<option value="">—</option>' + views.map(view => `<option value="${{escapeHtml(view.id)}}">${{escapeHtml(view.name)}}</option>`).join("");
  }} catch (error) {{ console.warn("Unable to load saved views", {{error:String(error)}}); }}
}}
async function loadSavedV2View(viewId) {{
  if (!viewId) return;
  const response = await fetch("/v2/saved-views/" + encodeURIComponent(viewId));
  if (!response.ok) throw new Error("HTTP " + response.status);
  const payload = await response.json();
  const query = payload.query || {{}};
  const kind = {{PageQuery:"pages",LinkQuery:"links",ResourceQuery:"resources",RedirectQuery:"redirects",FindingQuery:"findings",MetricQuery:"metrics"}}[query.query] || v2InventoryKind;
  const filters = query.filters || {{}};
  document.getElementById("v2-inventory-kind").value = kind;
  document.getElementById("v2-inventory-filter").value = filters.search || "";
  document.getElementById("v2-inventory-sort").value = filters.sort_by || "url";
  document.getElementById("v2-inventory-desc").checked = Boolean(filters.descending);
  loadV2Inventory(document.getElementById("v2-inventory-kind").value);
}}
async function deleteSavedV2View() {{
  const viewId = document.getElementById("v2-saved-view").value;
  if (!viewId) return;
  const response = await fetch("/v2/saved-views/" + encodeURIComponent(viewId), {{method:"DELETE"}});
  if (!response.ok) throw new Error("HTTP " + response.status);
  await loadSavedV2Views();
}}
async function exportSavedV2View() {{
  const viewId = document.getElementById("v2-saved-view").value;
  if (!viewId) return;
  const response = await fetch("/v2/saved-views/" + encodeURIComponent(viewId) + "/export?format=json");
  if (!response.ok) throw new Error("HTTP " + response.status);
  const payload = await response.json();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([payload.content], {{type:"application/json"}}));
  link.download = viewId + ".json";
  link.click();
  URL.revokeObjectURL(link.href);
}}
function selectedV2Urls() {{
  return v2InventoryItems.map(item => item.url_key || item.url || item.source_key).filter(Boolean).slice(0, 100);
}}
async function compareV2Inventory() {{
  const report = window.agentreadyV2Report;
  const status = document.getElementById("v2-inventory-status");
  if (!report) {{ status.textContent = translations[language.value].v2_inventory_empty; return; }}
  const baseline = localStorage.getItem("agentready.dashboard.compare.v2");
  if (!baseline) {{ localStorage.setItem("agentready.dashboard.compare.v2", JSON.stringify(report)); status.textContent = "Baseline saved"; return; }}
  try {{
    const response = await fetch("/v2/diff", {{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{request:{{url:document.getElementById("url").value,preset:"all",profile:document.getElementById("v2-profile").value,max_pages:selectedV2MaxPages()}},baseline:JSON.parse(baseline)}})}});
    if (!response.ok) throw new Error("HTTP " + response.status);
    const payload = await response.json();
    const findings = payload.findings || {{}};
    const count = name => Array.isArray(findings[name]) ? findings[name].length : 0;
    status.textContent = `Comparison complete: ${{count("regressed")}} regressions, ${{count("resolved")}} fixed, ${{count("added")}} new, ${{count("removed")}} removed`;
  }} catch (error) {{ status.textContent = translations[language.value].v2_inventory_error + ": " + error.message; }}
}}
async function rescanV2Selection() {{
  const urls = selectedV2Urls();
  const status = document.getElementById("v2-inventory-status");
  if (!urls.length) {{ status.textContent = translations[language.value].v2_inventory_empty; return; }}
  try {{
    const report = window.agentreadyV2Report;
    const response = await fetch("/v2/rescan", {{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{url:document.getElementById("url").value,preset:"all",profile:document.getElementById("v2-profile").value,max_pages:urls.length,selected_urls:urls,rescan_of:report && report.run ? report.run.id : null,confirm:true}})}});
    if (!response.ok) throw new Error("HTTP " + response.status);
    status.textContent = "Rescan complete";
  }} catch (error) {{ status.textContent = translations[language.value].v2_inventory_error + ": " + error.message; }}
}}
async function runV2InventoryJob() {{
  const status = document.getElementById("v2-inventory-status");
  try {{
    const response = await fetch("/v2/jobs", {{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{url:document.getElementById("url").value,preset:"all",profile:document.getElementById("v2-profile").value,max_pages:selectedV2MaxPages()}})}});
    if (!response.ok) throw new Error("HTTP " + response.status);
    const job = await response.json(); window.v2InventoryJobId = job.job_id; status.textContent = "Job " + job.job_id + " started";
  }} catch (error) {{ status.textContent = translations[language.value].v2_inventory_error + ": " + error.message; }}
}}
async function cancelV2InventoryJob() {{
  const status = document.getElementById("v2-inventory-status");
  if (!window.v2InventoryJobId) {{ status.textContent = "No active job"; return; }}
  try {{
    const response = await fetch("/v2/jobs/" + encodeURIComponent(window.v2InventoryJobId) + "/cancel", {{method:"POST"}});
    if (!response.ok) throw new Error("HTTP " + response.status);
    const job = await response.json(); status.textContent = "Job " + job.job_id + ": " + job.status;
  }} catch (error) {{ status.textContent = translations[language.value].v2_inventory_error + ": " + error.message; }}
}}
function openPromptEditor() {{
  let dialog = document.getElementById("ai-prompt-edit-dialog");
  if (!dialog) {{
    dialog = document.createElement("dialog");
    dialog.id = "ai-prompt-edit-dialog";
    dialog.className = "ai-prompt-edit-dialog";
    dialog.setAttribute("aria-labelledby", "ai-prompt-edit-title-heading");
    dialog.innerHTML = `<form method="dialog"><h2 id="ai-prompt-edit-title-heading">${{translations[language.value].ai_prompt_edit_dialog}}</h2><p>${{translations[language.value].ai_prompt_edit_dialog_hint}}</p><label for="ai-prompt-edit-name">${{translations[language.value].ai_prompt_title}}</label><input id="ai-prompt-edit-name" type="text" maxlength="120"><label for="ai-prompt-edit-text">${{translations[language.value].ai_message}}</label><textarea id="ai-prompt-edit-text"></textarea><div class="actions"><button type="button" class="secondary" id="ai-prompt-edit-cancel">${{translations[language.value].ai_prompt_cancel}}</button><button type="button" id="ai-prompt-edit-save">${{translations[language.value].ai_prompt_save}}</button></div></form>`;
    document.body.append(dialog);
    dialog.querySelector("#ai-prompt-edit-cancel").addEventListener("click", () => dialog.close());
    dialog.querySelector("#ai-prompt-edit-save").addEventListener("click", async () => {{
      document.getElementById("ai-prompt-title").value = dialog.querySelector("#ai-prompt-edit-name").value.trim();
      document.getElementById("ai-message").value = dialog.querySelector("#ai-prompt-edit-text").value;
      await savePrompt();
      dialog.close();
    }});
  }}
  const selected = aiPromptLibrary.find(item => item.id === document.getElementById("ai-prompt-library").value);
  if (selected) {{ aiPromptEditingId = selected.id; aiPromptEditingMode = selected.mode; }}
  dialog.querySelector("#ai-prompt-edit-name").value = selected?.title || document.getElementById("ai-prompt-title").value || "";
  dialog.querySelector("#ai-prompt-edit-text").value = selected?.prompt || document.getElementById("ai-message").value || "";
  dialog.showModal();
  dialog.querySelector("#ai-prompt-edit-name").focus();
}}
function setupPromptComposer() {{
  let select = document.getElementById("ai-prompt-library");
  let title = document.getElementById("ai-prompt-title");
  if (!select) {{ select = document.createElement("select"); select.id = "ai-prompt-library"; select.className = "ai-hidden-compatible"; document.body.append(select); }}
  if (!title) {{ title = document.createElement("input"); title.id = "ai-prompt-title"; title.className = "ai-hidden-compatible"; document.body.append(title); }}
  const toolbar = document.querySelector(".ai-composer-toolbar");
  const libraryPanel = document.querySelector(".ai-prompt-library-panel");
  if (!select || !title || !toolbar || document.querySelector(".ai-prompt-composer")) return;
  const composer = document.createElement("div");
  composer.className = "ai-prompt-composer";
  const row = document.createElement("div");
  row.className = "ai-prompt-composer-row";
  select.size = 1;
  select.classList.remove("ai-hidden-compatible");
  select.title = translations[language.value].ai_prompt_library;
  select.setAttribute("aria-label", translations[language.value].ai_prompt_library);
  row.append(select);
  const apply = document.createElement("button");
  apply.type = "button";
  apply.className = "secondary";
  apply.textContent = translations[language.value].ai_prompt_apply;
  apply.title = translations[language.value].ai_prompt_apply;
  apply.addEventListener("click", applyPrompt);
  row.append(apply);
  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "secondary";
  edit.textContent = translations[language.value].ai_prompt_edit || "Edit prompt";
  edit.title = translations[language.value].ai_prompt_edit_hint || translations[language.value].ai_prompt_save;
  edit.addEventListener("click", openPromptEditor);
  row.append(edit);
  const management = document.createElement("div");
  management.className = "ai-prompt-management";
  title.classList.remove("ai-hidden-compatible");
  title.classList.add("ai-prompt-edit-field");
  title.type = "text";
  title.placeholder = translations[language.value].ai_prompt_title;
  title.title = translations[language.value].ai_prompt_title;
  title.setAttribute("aria-label", translations[language.value].ai_prompt_title);
  management.append(title);
  const save = document.createElement("button");
  save.type = "button";
  save.className = "secondary";
  save.textContent = translations[language.value].ai_prompt_save_as;
  save.title = translations[language.value].ai_prompt_save;
  save.addEventListener("click", savePrompt);
  management.append(save);
  composer.append(row, management);
  const message = document.getElementById("ai-message");
  const messageRow = document.createElement("div");
  messageRow.className = "ai-message-row";
  message.parentNode.insertBefore(messageRow, message);
  messageRow.append(message);
  const tools = toolbar.querySelector(".ai-composer-tools");
  const attachment = tools.querySelector("label[for='ai-attachments']");
  const send = document.getElementById("ai-chat-button");
  const sideActions = document.createElement("div");
  sideActions.className = "ai-side-actions";
  sideActions.append(attachment, save, send);
  messageRow.append(sideActions);
  messageRow.parentNode.insertBefore(composer, toolbar);
  const links = document.createElement("div");
  links.className = "ai-composer-links";
  const link = (id, label, hint, action) => {{
    const item = document.createElement("a"); item.id = id; item.href = "#"; item.className = "text-link"; item.textContent = label; item.title = hint; item.setAttribute("aria-label", hint); item.addEventListener("click", event => {{ event.preventDefault(); action(); }}); return item;
  }};
  const runButton = document.getElementById("ai-run-button");
  const retryButton = document.getElementById("ai-retry-button");
  const exportButton = tools.querySelector("button[onclick='exportChat()']");
  runButton.remove(); retryButton.remove(); exportButton.remove();
  links.append(link("ai-run-button", translations[language.value].ai_simple_ask, translations[language.value].ai_run_hint, () => runAi("/ai/recommend")));
  links.append(link("ai-retry-button", translations[language.value].ai_retry_link, translations[language.value].ai_retry, () => runAi("/ai/chat", true)));
  links.append(link("ai-save-chat-link", translations[language.value].ai_chat_save, translations[language.value].ai_chat_save, () => saveChat()));
  links.append(link("ai-export-chat-link", translations[language.value].ai_export_link, translations[language.value].ai_chat_export, () => exportChat()));
  composer.parentNode.insertBefore(links, toolbar);
  toolbar.hidden = true;
  if (libraryPanel) libraryPanel.hidden = true;
}}
async function savePrompt() {{
  const prompt = document.getElementById("ai-message").value.trim();
  const title = document.getElementById("ai-prompt-title").value.trim() || prompt.slice(0, 80);
  if (!prompt || !title) return;
  try {{
    const response = await fetch("/ai/prompts", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{id:aiPromptEditingId,title,mode:aiPromptEditingMode || document.getElementById("ai-mode").value,prompt,language:language.value}})}});
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    aiPromptEditingId = data.prompt && data.prompt.id ? data.prompt.id : aiPromptEditingId;
    aiPromptEditingMode = data.prompt && data.prompt.mode ? data.prompt.mode : aiPromptEditingMode;
    await loadPromptLibrary();
  }} catch (error) {{
    document.getElementById("ai-result").hidden = false;
    renderAiReport({{error:{{message:translations[language.value].failed + ": " + error.message}}}});
  }}
}}
async function loadSavedChats() {{
  try {{
    const response = await fetch("/ai/chats");
    if (!response.ok) throw new Error("HTTP " + response.status);
    const select = document.getElementById("ai-saved-chats");
    select.replaceChildren();
    (await response.json()).chats.forEach(item => {{
      const option = document.createElement("option");
      option.value = item.file;
      option.textContent = item.name + (item.created_at ? " · " + item.created_at : "");
      select.append(option);
    }});
  }} catch (error) {{
    console.warn("Unable to load saved chats", {{error:String(error)}});
  }}
}}
async function saveChat(nameOverride=null) {{
  if (!aiConversationHistory.length) return false;
  const name = nameOverride || document.getElementById("ai-prompt-title").value.trim() || ("AI chat " + new Date().toISOString().slice(0, 19));
  try {{
    const response = await fetch("/ai/chats", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{
      name, target:safeDashboardTarget(document.getElementById("url").value) || null, language:language.value, mode:document.getElementById("ai-mode").value,
      provider:document.getElementById("ai-chat-provider").value || null, model:document.getElementById("ai-model").value || null,
      messages:aiConversationHistory, usage:aiSessionUsage
    }})}});
    if (!response.ok) throw new Error("HTTP " + response.status);
    await loadSavedChats();
    return true;
  }} catch (error) {{
    console.warn("[FIX:dashboard-context] Unable to save AI chat", {{error:String(error)}});
    return false;
  }}
}}
async function startNewChat() {{
  if (aiConversationHistory.length) {{
    const saved = await saveChat("AI chat " + new Date().toISOString().slice(0, 19));
    if (!saved) return false;
  }}
  aiConversationHistory = [];
  aiSessionUsage = {{prompt_tokens:0, completion_tokens:0, total_tokens:0, input_cost:0, output_cost:0, total_cost:0}};
  aiLastUserMessage = "";
  localStorage.removeItem(aiChatStateKey);
  renderChatHistory();
  document.getElementById("ai-result").replaceChildren();
  document.getElementById("ai-result").hidden = true;
  document.getElementById("ai-message").value = "";
  aiPromptEditingId = null;
  document.getElementById("ai-prompt-library").value = "";
  document.getElementById("ai-prompt-title").value = "";
  aiPromptEditingMode = null;
  return true;
}}
function exportChat() {{
  if (!aiConversationHistory.length) return;
  const payload = {{
    messages: aiConversationHistory.map(item => ({{role:item.role, content:item.content}})),
    model: document.getElementById("ai-model").value || null,
    provider: document.getElementById("ai-chat-provider").value || null,
    metadata: {{target:safeDashboardTarget(document.getElementById("url").value) || null, language:language.value, mode:document.getElementById("ai-mode").value}},
    usage: aiSessionUsage
  }};
  const blob = new Blob([JSON.stringify(payload, null, 2)], {{type:"application/json"}});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "agentready-chat-openai-deepseek.json";
  link.click();
  URL.revokeObjectURL(link.href);
}}
function aiReportDocument() {{
  const report = document.getElementById("ai-result").cloneNode(true);
  report.querySelectorAll("button").forEach(button => button.remove());
  report.querySelectorAll(".ai-full-report-link").forEach(link => link.remove());
  const fullReport = report.querySelector("#ai-full-report");
  if (fullReport) fullReport.hidden = false;
  return "<!doctype html><html lang='" + language.value + "'><head><meta charset='utf-8'><title>" +
    translations[language.value].ai_report_title + "</title><style>body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}}.report-generated{{margin:.25rem 0 1rem;color:#6b7280;font-size:.85rem}}.ai-report-card{{border:1px solid #ddd;border-radius:8px;padding:10px;margin:8px 0}}pre{{white-space:pre-wrap}}button{{display:none}}</style></head><body>" +
    report.outerHTML + "</body></html>";
}}
function downloadAiReport() {{
  const blob = new Blob([aiReportDocument()], {{type:"text/html;charset=utf-8"}});
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "agentready-ai-report.html";
  link.click();
  URL.revokeObjectURL(link.href);
}}
function printAiReport() {{
  const popup = window.open("", "_blank", "noopener,noreferrer");
  if (!popup) return;
  popup.document.write(aiReportDocument());
  popup.document.close();
  popup.focus();
  popup.print();
}}
function openAiFullReport() {{
  const popup = window.open("", "_blank", "noopener,noreferrer");
  if (!popup) return;
  popup.document.write(aiReportDocument());
  popup.document.close();
  popup.focus();
}}
function modelCapabilityLabel(capability) {{
  const icons = {{chat:"💬",embedding:"🔢",rerank:"↕",moderation:"🛡",audio:"🔊",other:"◈"}};
  const key = "model_" + capability;
  return (icons[capability] || icons.other) + " " + (translations[language.value][key] || capability);
}}
function modelOptionLabel(model) {{
  return (model.capabilities || ["other"]).map(modelCapabilityLabel).join(" · ") + " · " + model.id;
}}
function renderModelCatalog(models, selected) {{
  const providerSelect = document.getElementById("ai-provider-model");
  const chatSelect = document.getElementById("ai-model");
  window.aiModels = Array.isArray(models) ? models : [];
  const visibleModels = document.getElementById("ai-provider-chat-only").checked
    ? window.aiModels.filter(model => (model.capabilities || []).includes("chat"))
    : window.aiModels;
  [providerSelect, chatSelect].forEach(select => {{
    select.replaceChildren();
    visibleModels.forEach(model => {{
      const option = document.createElement("option"); option.value = model.id; option.textContent = modelOptionLabel(model); select.append(option);
    }});
    const preferred = selected && [...select.options].some(option => option.value === selected)
      ? selected
      : (visibleModels.find(model => (model.capabilities || []).includes("chat")) || visibleModels[0])?.id;
    if (preferred) select.value = preferred;
  }});
  const chip = document.getElementById("ai-model-chip");
  if (chip) {{
    const activeModel = chatSelect.value || selected || "—";
    chip.textContent = translations[language.value].ai_model_chip + ": " + activeModel;
    chip.title = activeModel === "—" ? translations[language.value].ai_model_hint : activeModel;
  }}
  saveDashboardState();
}}
function toggleChatOnly() {{
  renderModelCatalog(window.aiModels, document.getElementById("ai-provider-model").value || null);
}}
async function loadAiModels(providerId, selected) {{
  const result = document.getElementById("ai-credentials-result");
  setProviderBusy(true, translations[language.value].model_loading);
  try {{
    const response = await fetch("/ai/providers/" + encodeURIComponent(providerId) + "/models");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || ("HTTP " + response.status));
    renderModelCatalog(data.models, selected || data.selected_model);
    result.textContent = "";
  }} catch (error) {{
    renderModelCatalog([{{id:selected || "gpt-4o-mini",capabilities:["other"]}}], selected || "gpt-4o-mini");
    result.textContent = translations[language.value].model_error;
  }} finally {{
    setProviderBusy(false);
  }}
}}
function refreshAiModels() {{
  const provider = selectedAiProvider();
  if (provider) loadAiModels(provider.id, document.getElementById("ai-provider-model").value || provider.model);
}}
async function saveAiProvider() {{
  const result = document.getElementById("ai-credentials-result");
  const provider = selectedAiProvider();
  const body = {{provider_id:provider ? provider.id : null,name:document.getElementById("ai-provider-name").value,base_url:document.getElementById("ai-provider-url").value,model:document.getElementById("ai-provider-model").value || null,input_price_per_million:decimalValue("ai-provider-input-price"),output_price_per_million:decimalValue("ai-provider-output-price"),chat_only:document.getElementById("ai-provider-chat-only").checked,api_key:document.getElementById("ai-key").value || null,active:true,enable_ai:document.getElementById("ai-enable").checked}};
  setProviderBusy(true, translations[language.value].ai_saved);
  try {{
    const response = await fetch("/ai/providers", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify(body)}});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || ("HTTP " + response.status));
    result.textContent = translations[language.value].ai_saved;
    await refreshAiProviders();
  }} catch (error) {{ result.textContent = translations[language.value].failed + ": " + error.message; }}
  finally {{ setProviderBusy(false); }}
}}
async function activateAiProvider() {{
  const result = document.getElementById("ai-credentials-result");
  const providerId = document.getElementById("ai-provider").value;
  setProviderBusy(true);
  try {{
    const response = await fetch("/ai/providers/active", {{method:"POST", headers:{{"Content-Type":"application/json"}}, body:JSON.stringify({{provider_id:providerId}})}});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || ("HTTP " + response.status));
    result.textContent = translations[language.value].ai_active;
    await refreshAiProviders();
  }} catch (error) {{ result.textContent = translations[language.value].failed + ": " + error.message; }}
  finally {{ setProviderBusy(false); }}
}}
async function clearAiProvider() {{
  const result = document.getElementById("ai-credentials-result");
  const providerId = document.getElementById("ai-provider").value;
  if (!providerId) return;
  setProviderBusy(true);
  try {{
    const response = await fetch("/ai/providers/" + encodeURIComponent(providerId), {{method:"DELETE"}});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || ("HTTP " + response.status));
    result.textContent = translations[language.value].ai_cleared;
    await refreshAiProviders();
  }} catch (error) {{ result.textContent = translations[language.value].failed + ": " + error.message; }}
  finally {{ setProviderBusy(false); }}
}}
async function refreshAiProviders() {{
  const response = await fetch("/ai/status");
  const data = await response.json();
  const timeoutSeconds = Number(data.timeout_seconds);
  const maxRetries = Number(data.max_retries);
  const timeoutControl = document.getElementById("ai-provider-timeout");
  const retriesControl = document.getElementById("ai-provider-retries");
  if (timeoutControl && !Object.prototype.hasOwnProperty.call(restoredDashboardState, "ai-provider-timeout") && Number.isFinite(timeoutSeconds)) timeoutControl.value = String(timeoutSeconds);
  if (retriesControl && !Object.prototype.hasOwnProperty.call(restoredDashboardState, "ai-provider-retries") && Number.isFinite(maxRetries)) retriesControl.value = String(maxRetries);
  if (Number.isFinite(timeoutSeconds) && Number.isFinite(maxRetries)) {{
    // Per-attempt timeout + exponential retry backoff + response margin.
    const backoffSeconds = Math.min(31, Math.max(0, 2 ** maxRetries - 1));
    window.aiRequestTimeoutMs = Math.max(45000, (timeoutSeconds * (maxRetries + 1) + backoffSeconds + 15) * 1000);
  }}
  window.aiProviders = data.providers || [];
  renderAiProviders(data);
}}
function aiReportHeading(text, hintText) {{
  const heading = document.createElement("h3");
  heading.append(document.createTextNode(text));
  const hint = document.createElement("span");
  hint.className = "hint";
  hint.tabIndex = 0;
  hint.setAttribute("role", "img");
  hint.setAttribute("aria-label", hintText || text);
  hint.dataset.tooltip = hintText || text;
  hint.textContent = "?";
  heading.append(hint);
  return heading;
}}
function aiReportPriority(priority) {{
  const key = "ai_priority_" + String(priority || "medium").toLowerCase();
  return translations[language.value][key] || translations[language.value].ai_priority_medium;
}}
function aiReportStatus(status) {{
  const key = "ai_status_" + String(status || "warn").toLowerCase();
  return translations[language.value][key] || status || "";
}}
function aiReportMode(mode) {{
  return translations[language.value]["ai_mode_" + String(mode || "both").toLowerCase()] || mode || "";
}}
function aiReportText(text, className="") {{
  const element = document.createElement("p");
  element.className = className;
  element.textContent = text || "";
  return element;
}}
let aiSessionUsage = {{prompt_tokens:0, completion_tokens:0, total_tokens:0, input_cost:0, output_cost:0, total_cost:0}};
let aiConversationHistory = [];
let aiAttachments = [];
let aiLastUserMessage = "";
const aiChatStateKey = "agentready.ai.chat.v2";
function saveAiChatState() {{
  try {{
    localStorage.setItem(aiChatStateKey, JSON.stringify({{history:aiConversationHistory.slice(-40), usage:aiSessionUsage}}));
  }} catch (error) {{
    console.warn("Unable to persist AI chat", {{error:String(error)}});
  }}
}}
function restoreAiChatState() {{
  try {{
    const raw = localStorage.getItem(aiChatStateKey);
    if (!raw) return;
    const state = JSON.parse(raw);
    aiConversationHistory = Array.isArray(state.history) ? state.history.filter(item => item && (item.role === "user" || item.role === "assistant") && typeof item.content === "string").slice(-40) : [];
    aiLastUserMessage = [...aiConversationHistory].reverse().find(item => item.role === "user")?.content || "";
    if (state.usage && typeof state.usage === "object") aiSessionUsage = {{...aiSessionUsage, ...state.usage}};
    renderChatHistory();
    if (aiConversationHistory.length) prependChatResponseInfo({{}});
  }} catch (error) {{
    console.warn("Unable to restore AI chat", {{error:String(error)}});
  }}
}}
function renderChatHistory() {{
  const history = document.getElementById("ai-chat-history");
  const welcome = document.getElementById("ai-welcome");
  if (welcome) welcome.hidden = aiConversationHistory.length > 0;
  history.replaceChildren();
  aiConversationHistory.forEach(item => {{
    const message = document.createElement("div");
    message.className = "ai-chat-message " + item.role;
    message.textContent = item.content;
    history.append(message);
  }});
}}
async function restoreSavedChat() {{
  const filename = document.getElementById("ai-saved-chats").value;
  if (!filename) return;
  try {{
    const response = await fetch("/ai/chats/" + encodeURIComponent(filename));
    if (!response.ok) throw new Error("HTTP " + response.status);
    const data = await response.json();
    aiConversationHistory = Array.isArray(data.messages) ? data.messages.filter(item => item && (item.role === "user" || item.role === "assistant") && typeof item.content === "string").slice(-40) : [];
    aiLastUserMessage = [...aiConversationHistory].reverse().find(item => item.role === "user")?.content || "";
    if (data.usage && typeof data.usage === "object") aiSessionUsage = {{...aiSessionUsage, ...data.usage}};
    renderChatHistory();
    if (aiConversationHistory.length) prependChatResponseInfo({{}});
    saveAiChatState();
  }} catch (error) {{
    console.warn("Unable to restore saved AI chat", {{error:String(error)}});
  }}
}}
function selectedValues(id) {{
  return [...document.getElementById(id).selectedOptions].map(option => option.value);
}}
function aiToolPickerConfig(kind) {{
  return kind === "skills"
    ? {{selectId:"ai-skill", pickerId:"ai-skills-picker", optionsId:"ai-skills-options", triggerId:"ai-skills-trigger", labelKey:"ai_skills_selected", emptyKey:"ai_skills_selected"}}
    : {{selectId:"ai-mcp-tool", pickerId:"ai-context-picker", optionsId:"ai-context-options", triggerId:"ai-context-trigger", labelKey:"ai_context_selected", emptyKey:"ai_context_selected"}};
}}
function renderAiToolPicker(kind) {{
  const config = aiToolPickerConfig(kind);
  const select = document.getElementById(config.selectId);
  const container = document.getElementById(config.optionsId);
  if (!select || !container || container.dataset.ready === "true") return;
  container.replaceChildren(...[...select.options].map(option => {{
    const label = document.createElement("label");
    label.className = "ai-tool-option";
    label.title = option.title || option.textContent;
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = option.value;
    checkbox.checked = option.selected;
    checkbox.setAttribute("aria-label", option.dataset.label || option.textContent);
    checkbox.addEventListener("change", () => {{
      option.selected = checkbox.checked;
      select.dispatchEvent(new Event("change", {{bubbles:true}}));
    }});
    const text = document.createElement("span");
    text.textContent = option.dataset.label || option.textContent.split(" — ")[0];
    label.append(checkbox, text);
    return label;
  }}));
  container.dataset.ready = "true";
}}
function syncAiToolPicker(kind) {{
  const config = aiToolPickerConfig(kind);
  renderAiToolPicker(kind);
  const selected = new Set(selectedValues(config.selectId));
  document.querySelectorAll("#" + config.optionsId + " input").forEach(input => input.checked = selected.has(input.value));
}}
function toggleAiToolPicker(kind) {{
  const config = aiToolPickerConfig(kind);
  renderAiToolPicker(kind);
  document.querySelectorAll(".ai-tool-picker").forEach(picker => {{
    if (picker.id !== config.pickerId) picker.classList.remove("open");
  }});
  document.getElementById(config.pickerId).classList.toggle("open");
  console.info("[AI-UX] Tool picker toggled", {{kind, open:document.getElementById(config.pickerId).classList.contains("open")}});
}}
function updateAiContextChips() {{
  const container = document.getElementById("ai-context-chips");
  if (!container) return;
  syncAiToolPicker("skills");
  syncAiToolPicker("context");
  const skillSelect = document.getElementById("ai-skill");
  const contextSelect = document.getElementById("ai-mcp-tool");
  const skillNames = [...skillSelect.selectedOptions].map(option => option.dataset.label || option.textContent.split(" — ")[0]);
  const contextNames = [...contextSelect.selectedOptions].map(option => option.dataset.label || option.textContent.split(" — ")[0]);
  const skillTrigger = document.getElementById("ai-skills-trigger");
  const contextTrigger = document.getElementById("ai-context-trigger");
  skillTrigger.textContent = translations[language.value].ai_skills + ": " + skillNames.length;
  skillTrigger.title = skillNames.length ? skillNames.join(", ") + ". " + translations[language.value].ai_skills_hint : translations[language.value].ai_skills_hint;
  contextTrigger.textContent = translations[language.value].ai_mcp + ": " + contextNames.length;
  contextTrigger.title = contextNames.length ? contextNames.join(", ") + ". " + translations[language.value].ai_mcp_hint : translations[language.value].ai_mcp_hint;
  const values = [
    ["MCP", selectedValues("ai-mcp-tool").length],
    ["Skills", selectedValues("ai-skill").length],
    ["Files", aiAttachments.length]
  ].filter(item => item[1] > 0);
  const filesChip = document.getElementById("ai-files-chip");
  if (filesChip) filesChip.remove();
  const fileCount = aiAttachments.length;
  if (fileCount) {{
    const chip = document.createElement("span");
    chip.id = "ai-files-chip";
    chip.className = "ai-context-chip ai-files-chip";
    chip.textContent = "Files: " + fileCount;
    chip.title = aiAttachments.map(item => item.name).join(", ");
    container.append(chip);
  }}
  console.info("[AI-UX] Context summary updated", {{mcp:values[0]?.[1] || 0, skills:values[1]?.[1] || 0, files:values[2]?.[1] || 0}});
}}
function appendChatMessage(role, content) {{
  if (!content) return;
  aiConversationHistory.push({{role, content}});
  const history = document.getElementById("ai-chat-history");
  const message = document.createElement("div");
  message.className = "ai-chat-message " + role;
  message.textContent = content;
  history.append(message);
  history.scrollTop = history.scrollHeight;
  saveAiChatState();
}}
function prependChatResponseInfo(data) {{
  const history = document.getElementById("ai-chat-history");
  const existing = history.querySelector(".ai-chat-response-info");
  if (existing) existing.remove();
  const info = document.createElement("div");
  info.className = "ai-chat-response-info";
  info.textContent = translations[language.value].ai_response_language;
  history.prepend(info);
  saveAiChatState();
}}
function base64FromBytes(bytes) {{
  let binary = "";
  const chunk = 0x8000;
  for (let index = 0; index < bytes.length; index += chunk) binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
  return btoa(binary);
}}
async function readAiAttachment(file) {{
  const type = file.type || "application/octet-stream";
  const textual = type.startsWith("text/") || /\.(txt|md|markdown|json|csv|ya?ml)$/i.test(file.name);
  const content = textual
    ? (await file.text()).slice(0, 12000)
    : "data:" + type + ";base64," + base64FromBytes(new Uint8Array(await file.arrayBuffer())).slice(0, 16000);
  return {{name:file.name, type, content}};
}}
async function readAiAttachments(files) {{
  aiAttachments = await Promise.all([...files].slice(0, 5).map(readAiAttachment));
  console.info("AI attachments loaded", {{count:aiAttachments.length, names:aiAttachments.map(item => item.name)}});
  updateAiContextChips();
}}
function accumulateAiUsage(data) {{
  const usage = data && data.usage;
  if (!usage || data._sessionUsageCounted) return;
  ["prompt_tokens","completion_tokens","total_tokens","input_cost","output_cost","total_cost"].forEach(key => {{
    aiSessionUsage[key] += Number(usage[key] || 0);
  }});
  data.session_usage = {{...aiSessionUsage}};
  data._sessionUsageCounted = true;
  saveAiChatState();
}}
function renderAiUsage(data) {{
  if (!data.usage) return null;
  const card = document.createElement("div");
  card.className = "ai-report-card";
  const current = data.usage;
  const session = data.session_usage || aiSessionUsage;
  const tokens = [
    [translations[language.value].ai_input_tokens, current.prompt_tokens],
    [translations[language.value].ai_output_tokens, current.completion_tokens],
    [translations[language.value].ai_total_tokens, current.total_tokens]
  ];
  const costsConfigured = Number(current.input_price_per_million) > 0 && Number(current.output_price_per_million) > 0;
  if (costsConfigured) tokens.push(
    [translations[language.value].ai_input_cost, Number(current.input_cost || 0).toFixed(6)],
    [translations[language.value].ai_output_cost, Number(current.output_cost || 0).toFixed(6)],
    [translations[language.value].ai_total_cost, Number(current.total_cost || 0).toFixed(6)]
  );
  const sessionTokens = [
    [translations[language.value].ai_input_tokens, session.prompt_tokens],
    [translations[language.value].ai_output_tokens, session.completion_tokens],
    [translations[language.value].ai_total_tokens, session.total_tokens]
  ];
  if (costsConfigured) sessionTokens.push([translations[language.value].ai_total_cost, Number(session.total_cost || 0).toFixed(6)]);
  const heading = document.createElement("strong");
  heading.textContent = translations[language.value].ai_usage;
  card.append(heading, aiReportText(tokens.map(item => item[0] + ": " + item[1]).join(" · ")));
  const sessionHeading = document.createElement("strong");
  sessionHeading.textContent = translations[language.value].ai_session_usage;
  card.append(sessionHeading, aiReportText(sessionTokens.map(item => item[0] + ": " + item[1]).join(" · ")));
  return card;
}}
function renderAiReport(data) {{
  const output = document.getElementById("ai-result");
  accumulateAiUsage(data);
  output.className = "ai-report";
  output.replaceChildren();
  const title = document.createElement("h1");
  title.textContent = translations[language.value].ai_report_title;
  output.append(title);
  const generated = document.createElement("p");
  generated.className = "report-generated";
  const generatedModel = data.model || translations[language.value].ai_model_unknown;
  generated.textContent = translations[language.value].ai_generated + " " + translations[language.value].ai_generated_with_model + " " + generatedModel + " " + new Date().toLocaleString();
  output.append(generated);
  const reportActions = document.createElement("div");
  reportActions.className = "actions";
  const download = document.createElement("button");
  download.type = "button";
  download.className = "secondary";
  download.textContent = translations[language.value].ai_download;
  download.onclick = downloadAiReport;
  const print = document.createElement("button");
  print.type = "button";
  print.className = "secondary";
  print.textContent = translations[language.value].ai_print;
  print.onclick = printAiReport;
  reportActions.append(download, print);
  output.append(reportActions);
  const meta = document.createElement("div");
  meta.className = "ai-report-meta";
  const metaParts = [];
  if (data.target) metaParts.push(translations[language.value].ai_target + ": " + data.target);
  if (data.mode) metaParts.push(aiReportMode(data.mode));
  if (data.model) metaParts.push(data.model);
  if (metaParts.length) meta.textContent = metaParts.join(" · ");
  output.append(meta);
  if (data.error) {{
    const errorCard = document.createElement("div");
    errorCard.className = "ai-report-card";
    errorCard.dataset.priority = "high";
    errorCard.append(aiReportText(data.error.message || translations[language.value].failed));
    if (data.error.code) errorCard.append(aiReportText(translations[language.value].ai_error_code + ": " + data.error.code));
    output.append(errorCard);
    return output;
  }}
  if (data.summary) {{
    output.append(aiReportHeading(translations[language.value].ai_summary, translations[language.value].ai_summary_hint));
    output.append(aiReportText(data.summary, "ai-report-summary"));
  }}
  const actions = Array.isArray(data.actions) ? data.actions : [];
  output.append(aiReportHeading(translations[language.value].ai_actions, translations[language.value].ai_actions_hint));
  if (!actions.length) output.append(aiReportText(translations[language.value].ai_no_actions));
  else {{
    const list = document.createElement("ul");
    list.className = "ai-report-list";
    actions.forEach(action => {{
      const card = document.createElement("li");
      card.className = "ai-report-card";
      card.dataset.priority = action.priority || "medium";
      const heading = document.createElement("strong");
      heading.textContent = aiReportPriority(action.priority) + " · " + (action.title || "");
      card.append(heading, aiReportText(action.action || ""));
      if (Array.isArray(action.check_ids) && action.check_ids.length) {{
        card.append(aiReportText(translations[language.value].ai_checks + ": " + action.check_ids.join(", ")));
      }}
      if (Array.isArray(action.verification) && action.verification.length) {{
        card.append(aiReportText(translations[language.value].ai_verification + ": " + action.verification.join(" · ")));
      }}
      list.append(card);
    }});
    output.append(list);
  }}
  const evidence = Array.isArray(data.evidence) ? data.evidence : [];
  output.append(aiReportHeading(translations[language.value].ai_evidence, translations[language.value].ai_evidence_hint));
  if (!evidence.length) output.append(aiReportText(translations[language.value].ai_no_evidence));
  else {{
    const list = document.createElement("ul");
    list.className = "ai-report-evidence";
    evidence.forEach(item => {{
      const row = document.createElement("li");
      const parts = [item.check_id, aiReportStatus(item.status), item.details, item.source_url].filter(Boolean);
      if (Array.isArray(item.evidence) && item.evidence.length) parts.push(item.evidence.join(" · "));
      if (item.metrics && typeof item.metrics === "object" && Object.keys(item.metrics).length) {{
        parts.push(JSON.stringify(item.metrics));
      }}
      row.textContent = parts.join(" · ");
      list.append(row);
    }});
    output.append(list);
  }}
  if (Array.isArray(data.cautions) && data.cautions.length) {{
    output.append(aiReportHeading(translations[language.value].ai_cautions, translations[language.value].ai_cautions_hint));
    const list = document.createElement("ul");
    list.className = "ai-report-cautions";
    data.cautions.forEach(item => {{
      const row = document.createElement("li");
      row.textContent = item;
      list.append(row);
    }});
    output.append(list);
  }}
  const usage = renderAiUsage(data);
  if (usage) output.append(aiReportHeading(translations[language.value].ai_usage), usage);
  if (data.disclaimer) {{
    output.append(aiReportHeading(translations[language.value].ai_disclaimer, translations[language.value].ai_disclaimer_hint));
    output.append(aiReportText(data.disclaimer));
  }}
  if (debugMode()) {{
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = translations[language.value].ai_json;
    const raw = document.createElement("pre");
    raw.textContent = JSON.stringify(data, null, 2);
    details.append(summary, raw);
    output.append(details);
  }}
  const visibleNodes = new Set([title, generated, reportActions, meta]);
  const fullReport = document.createElement("div");
  fullReport.id = "ai-full-report";
  fullReport.hidden = true;
  [...output.children].filter(node => !visibleNodes.has(node)).forEach(node => fullReport.append(node));
  const fullReportLink = document.createElement("a");
  fullReportLink.href = "#ai-full-report";
  fullReportLink.target = "_blank";
  fullReportLink.rel = "noopener noreferrer";
  fullReportLink.className = "ai-full-report-link";
  fullReportLink.title = translations[language.value].ai_open_full_report_hint;
  fullReportLink.textContent = translations[language.value].ai_open_full_report;
  fullReportLink.setAttribute("aria-label", translations[language.value].ai_open_full_report_hint);
  fullReportLink.onclick = event => {{
    event.preventDefault();
    const reportHtml = aiReportDocument();
    const popup = window.open("", "_blank", "noopener,noreferrer");
    if (popup) {{
      popup.document.write(reportHtml);
      popup.document.close();
      popup.focus();
      logDashboardAction("ai.full_report.open", {{mode:"window"}});
      return;
    }}
    fullReport.hidden = false;
    fullReportLink.href = "#ai-full-report";
    fullReportLink.target = "_self";
    fullReportLink.textContent = translations[language.value].ai_open_full_report_inline;
    logDashboardAction("ai.full_report.open", {{mode:"inline-fallback"}});
  }};
  output.append(fullReportLink, fullReport);
  return output;
}}
async function runAi(path="/ai/recommend", retry=false) {{
  const target = document.getElementById("url").value;
  const output = document.getElementById("ai-result");
  if (!auditCompleted || !target.trim()) return;
  output.hidden = false;
  if (!target) {{ renderAiReport({{error:{{message:translations[language.value].no_url}}}}); return; }}
  let timeoutId = null;
  try {{
    const message = retry ? aiLastUserMessage : (document.getElementById("ai-message").value || null);
    if (path === "/ai/chat" && !message) {{ renderAiReport({{error:{{message:translations[language.value].ai_message}}}}); return; }}
    if (path === "/ai/chat" && !retry) {{
      aiLastUserMessage = message;
      appendChatMessage("user", message);
    }}
    logDashboardAction("ai.request", {{operation:path === "/ai/chat" ? "chat" : "recommend", retry, has_report:Boolean(window.agentreadyV2Report), message_length:message ? message.length : 0}});
    setAiBusy(true);
    const controller = new AbortController();
    // Allow the configured provider retry budget to complete for large reports.
    const configuredTimeout = Number(document.getElementById("ai-provider-timeout")?.value);
    const configuredRetries = Number(document.getElementById("ai-provider-retries")?.value);
    const providerTimeoutSeconds = Number.isFinite(configuredTimeout) ? Math.min(120, Math.max(1, configuredTimeout)) : 120;
    const retryCount = Number.isFinite(configuredRetries) ? Math.min(5, Math.max(0, configuredRetries)) : 2;
    const backoffSeconds = Math.min(31, Math.max(0, 2 ** retryCount - 1));
    const providerTimeout = (providerTimeoutSeconds * (retryCount + 1) + backoffSeconds + 15) * 1000;
    timeoutId = window.setTimeout(() => controller.abort(), providerTimeout);
    const history = path === "/ai/chat" ? aiConversationHistory.slice(0, retry ? aiConversationHistory.length : -1).slice(-12) : aiConversationHistory.slice(-12);
    const response = await fetch(path, {{method:"POST", headers:{{"Content-Type":"application/json"}}, signal:controller.signal, body:JSON.stringify({{target,report:window.agentreadyV2Report || null,mode:document.getElementById("ai-mode").value,model:document.getElementById("ai-model").value || null,language:language.value,message,history,skills:selectedValues("ai-skill"),mcp_tools:selectedValues("ai-mcp-tool"),attachments:aiAttachments,provider_timeout:providerTimeoutSeconds,provider_max_retries:retryCount}})}});
    const data = await response.json();
    if (!response.ok) {{
      const detail = data && data.detail;
      const detailMessage = detail && typeof detail === "object" ? (detail.message || JSON.stringify(detail)) : detail;
      throw new Error(detailMessage || ("HTTP " + response.status));
    }}
    if (path === "/ai/chat") {{
      prependChatResponseInfo(data);
      appendChatMessage("assistant", data.summary || translations[language.value].ai_report_title);
    }}
    renderAiReport(data);
  }} catch (error) {{
    const message = error.name === "AbortError" ? translations[language.value].ai_timeout : translations[language.value].failed + ": " + error.message;
    console.warn("AI request finished with error", {{path, name:error.name, message}});
    renderAiReport({{error:{{message}}}});
  }} finally {{
    if (timeoutId !== null) window.clearTimeout(timeoutId);
    setAiBusy(false);
  }}
}}
function renderChecks() {{
  const container = document.getElementById("checks"); container.replaceChildren();
  const preset = document.getElementById("preset").value;
  catalog.forEach(item => {{
    const label = document.createElement("label"); label.className = "check";
    const input = document.createElement("input"); input.type = "checkbox"; input.value = item.id; input.checked = preset === "seo" || preset === "mobile" || (item.presets || []).includes(preset);
    const content = document.createElement("span"); const title = document.createElement("strong"); title.textContent = item.title;
    const hint = hintIcon(item.hint || item.description);
    const supported = item.presets ? item.presets.map(preset => presetLabels[preset] || preset).join(", ") : (preset === "mobile" ? presetLabels.mobile : presetLabels.seo);
    const description = document.createElement("small"); description.textContent = item.description + " [" + item.category + "; " + supported + "]";
    content.append(title, hint, description); label.append(input, content); container.append(label);
  }});
}}
async function loadChecks(showOutput=true) {{ try {{ const preset = document.getElementById("preset").value; const path = preset === "seo" ? "/seo/checks" : (preset === "mobile" ? "/mobile/checks" : "/checks"); catalog = await request(path, "GET", null, false, showOutput, translations[language.value].catalog_updated); renderChecks(); }} catch (error) {{ showResult(); result.textContent = translations[language.value].catalog_error + ": " + error.message; }} }}
document.getElementById("url").addEventListener("input", () => setAiAvailability(false));
document.getElementById("ai-attachments").addEventListener("change", event => readAiAttachments(event.target.files));
document.getElementById("ai-message").addEventListener("keydown", event => {{
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {{
    event.preventDefault();
    runAi("/ai/chat");
  }}
}});
const toolsPanel = document.getElementById("tools-panel");
if (toolsPanel) toolsPanel.addEventListener("toggle", saveDashboardState);
document.getElementById("ai-chat-button").addEventListener("click", () => runAi("/ai/chat"));
document.getElementById("ai-message").addEventListener("paste", event => {{
  const files = event.clipboardData && event.clipboardData.files;
  if (files && files.length) {{
    event.preventDefault();
    readAiAttachments(files);
  }}
}});
document.getElementById("ai-skill").addEventListener("change", saveAiTools);
document.getElementById("ai-mcp-tool").addEventListener("change", saveAiTools);
document.getElementById("ai-skill").addEventListener("change", updateAiContextChips);
document.getElementById("ai-mcp-tool").addEventListener("change", updateAiContextChips);
document.addEventListener("click", event => {{
  if (!event.target.closest(".ai-tool-picker")) document.querySelectorAll(".ai-tool-picker").forEach(picker => picker.classList.remove("open"));
}});
document.getElementById("ai-chat-search").addEventListener("input", event => {{
  const needle = event.target.value.trim().toLowerCase();
  [...document.getElementById("ai-saved-chats").options].forEach(option => {{ option.hidden = Boolean(needle && !option.textContent.toLowerCase().includes(needle)); }});
  console.info("[AI-UX] Saved chat search", {{hasQuery:Boolean(needle)}});
}});
document.getElementById("preset").onchange = () => {{ setAiAvailability(false); updatePresetHint(); loadChecks(); }};
document.getElementById("v2-profile").addEventListener("change", syncV2ProfileBudget);
updatePresetHint(); updateAiModeHint(); setAiAvailability(false); loadChecks(false);
const robotsLiveField = document.getElementById("robots-live");
if (robotsLiveField) robotsLiveField.addEventListener("input", () => {{
  robotsLiveField.dataset.userEdited = "true";
  robotsLiveField.readOnly = false;
  robotsLiveField.removeAttribute("aria-readonly");
}});
restoreReportState();
restoreActiveV2Job();
loadSavedV2Views();
refreshAiProviders().catch(error => console.warn("Unable to initialize AI providers", {{error:String(error)}}));
loadAiTools();
updateAiContextChips();
setupPromptComposer();
addSettingsHints();
loadPromptLibrary();
loadSavedChats();
restoreAiChatState();
document.getElementById("ai-saved-chats").addEventListener("change", restoreSavedChat);
</script>
</body></html>"""
