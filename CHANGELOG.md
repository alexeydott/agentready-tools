# Changelog

## 0.13.2

### Explicit test dependencies and release packaging

- Made `requirements-dev.txt` explicitly install the `dev`, MCP, and portable
  extras required for collection and full-suite validation.
- Corrected README and developer guidance to describe MCP as a collection-time
  test dependency rather than an optional skipped test surface.
- Excluded local `.agentready.yml` configuration from source archives and
  synchronized source-package validation with the published v2 schemas.
- Rebuilt the Win64 portable executable with synchronized `0.13.2` metadata.

## 0.13.1 

### Background crawl progress and AI audit context

- Added background v2 audit jobs with persisted progress, including crawl
  phase, fetched URLs, discovered URLs, and queue state; progress survives a
  dashboard reload and service-health checks no longer reset it.
- Added configurable crawl depth. Deep profile with depth `0` inspects only
  the start page and its same-origin resources; page limit `0` remains the
  full same-origin crawl up to the shared 25,000-page safety cap.
- Fixed dashboard-to-AI handoff: the completed v2 report is now extracted from
  the background HTML response and passed to the AI chat instead of starting a
  new default 25-page audit.
- Added regression coverage for depth-zero resource inventory, background job
  progress, report-context extraction, and rendered report restoration.

## 0.13.0

### Full-site crawl and localized dashboard fixes

- Added full same-origin crawl mode: `max_pages=0` expands to the shared
  25,000-URL safety cap across dashboard, HTTP, SEO, and `AuditService` paths.
- Made crawl-profile budgets visible and predictable: deep profile defaults to
  100 pages while explicit page limits remain respected.
- Fixed dashboard report restoration so stale `Сводка инвентаря` HTML is
  invalidated and regenerated with the localized `Состав и объём данных` label.
- Preserved crawl profile and page-budget selections in dashboard requests and
  added regression coverage for profile, SEO crawl, localization, and full-site
  budget behavior.
- Completed v2 SEO/marketer tooling, reports, inventory, MCP, jobs, saved views,
  and release-gate cleanup accumulated since 0.12.0.

## 0.12.0

### v2 transport parity and final marketer workflow

- Added canonical CLI inventory/view/export/compare/rescan commands.
- Added MCP `run_inventory_v2` and credential-free cached provider fixture
  normalization alongside the existing v2 audit tools.
- Added bounded PageSpeed, GA4, GSC, and URL Inspection enrichment jobs using
  the existing metric/store/query path; enrichment cannot change core scores.
- Added the dated official-source Yandex Webmaster/Metrica deferral record.
- Updated compatibility/version/package metadata, dashboard acceptance storage
  keys, documentation, and release goldens for v0.12.0.

## 0.11.0

### Breaking: v2-only audit contracts

- Replaced the public v1 scan, SEO, and mobile command/route/tool facades with
  the canonical `agentready audit --mode ...`, `/v2/...`, and v2 MCP surfaces.
- Unified readiness, SEO, mobile, findings, remediation, and protocol report
  schemas under explicit v2 contracts; unsupported v1 payloads are rejected.
- Routed readiness rule execution through the v2 `AuditService` projection and
  preserved bounded crawl coverage, run lineage, and baseline diff semantics.
- Updated dashboard links, generated remediation commands, regression tests,
  architecture contracts, and integration documentation.
- Fixed canonical v2 CLI rendering, score gates, SEO check selection, filter
  partitioning, credentials management, and release-manifest completeness.
- Closed the remaining release gates: published v2 schema documents now match
  serialized reports, all versioned HTTP routes are manifest-covered, and
  readiness rule/crawl execution reuses a bounded per-run response cache.

## 0.10.0

- Refined the SEO/GEO AI assistant workspace to match the planned chat-first
  layout, including in-chat Skills and MCP context pickers with explanatory
  tooltips and compact context chips.
- Moved the prompt library into the composer as a dropdown with prompt use,
  save-as, user-prompt editing, and a modal editor with full-width title and
  multiline prompt fields.
- Aligned composer actions with the UX design: attachment, save-as-prompt,
  and send controls sit beside the textarea; secondary chat actions are
  tooltip links; AI settings are available from the model panel.
- Preserved prompt IDs, localized variants, user-prompt modes, existing AI
  API contracts, report persistence, and dashboard chat interactions.
- Documented the current runtime architecture and v1/v2 compatibility
  boundaries, and exposed the source-package command in the main documentation.

## 0.9.0 

- Added the AuditService-backed v2 dashboard profile and bounded typed run
  inventory endpoints, with scheduler protection for page limits and invalid
  non-HTTP links.
- Exposed the vNext crawl profile, page limit, and browser rendering in the
  dashboard's advanced panel instead of hard-coded request values, and added
  the missing localized vNext profile hint.
- Bounded the in-process v2 run registry by retained inventory records in
  addition to run count, so deep crawls cannot pin unbounded memory; evicted
  runs now return `404` from inventory endpoints.
- Recorded URLs drained by the max-pages stop in coverage and run inventory so
  a bounded run leaves no stale `queued` rows.
- Restored the combined-report hover/focus hint check in the headed dashboard
  acceptance runner as a hard assertion with an explicit iframe wait.
- Documented the `/v2/runs/{run_id}/inventory/{kind}` route, the `urls` alias,
  and registry eviction behavior.
- Rebuilt the portable executable and extended the regression gate to 361 tests.

## 0.8.2

- Hardened dashboard AI prompt editing so stable prompt IDs and independent
  English/Russian variants are preserved, with visible save failures.
- Added headed browser regression coverage for `/dashboard`, local session/chat
  restoration, credential redaction, optional-provider skips, and browser
  diagnostics.
- Added the `python -m agentready.cli` entrypoint and synchronized package,
  compatibility, report, and Windows portable version metadata.
- Added a full-extra GitHub Actions gate for MCP and Chromium-backed tests.
- Rebuilt the portable executable and retained the 357-test regression gate.

## 0.8.1

- Fixed the combined “All checks” dashboard report so GEO and SEO sections
  retain their built-in hover/focus hints, with Edge UI coverage.
- Synchronized package, API, report, and Windows portable version metadata.

## 0.8.0

- Added the vNext compatibility surface: bounded v2 reports, evidence and
  coverage contracts, protocol and provider boundaries, storage/crawler
  foundations, and additive API/CLI jobs, diff, rescan, and export workflows.
- Migrated dashboard and AI projections to evidence-backed v2 context while
  preserving v1 commands, localized reports, credential boundaries, and MCP
  compatibility.
- Release candidate validation covers 213 tests, source packaging policy,
  compile checks, compatibility suites, and synchronized Windows/package
  version metadata.

## 0.7.13

- Embedded localized AI chat skills, including the SEO security interpreter
  for explaining insecure links and possible SEO-spam signals.
- Applied the built-in skill instructions consistently across dashboard, CLI,
  and MCP AI assistant surfaces.

## 0.7.12

- Added a visible localized list of affected page URLs to SEO HTML reports
  for crawl-aware insecure-link findings.

## 0.7.11

- Added crawl-aware SEO detection for insecure HTTP links on every crawled
  HTTPS page, with affected page URLs and localized guidance in serve, CLI,
  and MCP reports.

## 0.7.10

- Added the MCP CLI extra to the portable dependency set so clean PyInstaller
  builds install all required transitive dependencies.
- Added reproducible clean-environment setup and source-archive instructions.

## 0.7.9

- Changed Russian standard report status labels to normal lowercase wording,
  matching the SEO report.

## 0.7.8

- Corrected SEO image evidence so `Additional details` lists only images
  missing `alt` text and includes matching total/missing counters.
- Applied the same affected-only evidence pattern to mixed-content resources
  and insecure links.

## 0.7.7

- Normalized dashboard decimal values to display a leading zero, for example
  `0.8` instead of `.8`.

## 0.7.6

- Updated dashboard decimal inputs to accept both `.` and `,` separators.

## 0.7.5

- Limited SEO report `Additional details` evidence to failed, warning, and
  error checks so passed and not-applicable checks stay concise.

## 0.7.4

- Normalized the status column typography in the standard HTML report to match
  the SEO and mobile report styling.

## 0.7.3

- Expanded the dashboard to use the available viewport width instead of a
  centered fixed-width layout.

## 0.7.2

- Moved the dashboard help panel to the right side.
- Moved the localized help toggle beside the language selector and removed the
  language-selector tooltip icon.

## 0.7.1

- Made the dashboard help sidebar horizontally resizable on desktop while
  preserving the stacked mobile layout.

## 0.7.0

- Added a collapsible localized help sidebar to the dashboard.
- Added beginner guidance for audit setup, checks, reports, AI assistant usage, language selection, and troubleshooting.


## 0.6.0

- Added structured SEO evidence locations for affected pages and resources, including image `page`/`resource` fields and title length metrics.
- Preserved bounded evidence metrics through AI context projection, typed AI responses, and the dashboard AI report.
- Added evidence URLs, findings, and metrics to SEO console and Markdown exports for consistent report output.
- Added regression coverage for structured evidence serialization, AI propagation, dashboard display data, and report renderers.

## 0.5.2

- Added simple and advanced usage examples with descriptions to nested CLI help modes.
- Added regression coverage for rendered portable help output.

## 0.5.1

- Fixed report timestamps so they appear immediately below `h1` in every HTML report.
- Unified subdued timestamp styling across standard, SEO, mobile, and AI report exports.
- Fixed HTML report generation to use one timestamp for all localized report views.

## 0.5.0

- Added an OpenAI-compatible SEO/GEO AI assistant across CLI, FastAPI serve, dashboard, and MCP.
- Added provider profiles, shared OS-vault credentials, model catalogs, capability markers, model selection, usage, and cost accounting.
- Added localized structured AI reports, dashboard language support, loading/error states, audit gating, and persistent provider/model state.
- Added localized prompt library, built-in SEO/GEO skills, AgentReady MCP context, bounded conversation history, attachments, clipboard paste, saved chats, and chat restoration.
- Added chat retry, OpenAI/DeepSeek-compatible JSON export, new-chat autosave, resizable input, and AI report HTML download/print.
- Changed portable runtime persistence to use `.cache` beside the executable and documented the runtime data layout.
- Added generation timestamps to standard, SEO, mobile, and AI reports.

## 0.4.0

- Added a separate `ai-search` / GEO audit profile inspired by the Tochki practical guide without changing the protocol-readiness score.
- Added `ai_search_score` and `ai_search_applicable` to reports plus `--min-ai-search-score` / `--min-geo-score` CI gates.
- Added `search-indexability`, `ai-crawler-live-access`, `structured-data-graph`, `faq-structured-data`, `date-transparency`, and experimental `citation-readiness` checks.
- Added live crawler diagnostics for OAI-SearchBot, Claude-SearchBot, PerplexityBot and Googlebot; user-directed/training agents are reported separately.
- Added IndexNow key generation, deployed-key verification, batch submission, dry-run and Git-change URL mapping with explicit `--send`.
- Added Git-backed publication/modification date review with normalized-content comparison.
- Added AI crawler access-log summaries.
- Added Russian/English `AI_SEARCH_RULES.md` generator for safe mass-edit and verification workflows.
- Added GEO-aware recommendations and report/dashboard display.
- Added baseline warning when AI Search/GEO score decreases.
- Expanded regression suite to 21 tests before end-to-end packaging validation.

## 0.3.0

- Added a dedicated localization layer with built-in English (`en`) and Russian (`ru`) catalogs.
- Added `--lang` / `--language` selection for scans and check listings.
- Added `report.language` to YAML configuration and `agentready init --lang`.
- Localized console, JSON, Markdown, and HTML report output.
- Localized check/category/level labels, result descriptions, recommendations, remediation guidance, and coding-agent prompts.
- Preserved stable machine identifiers (`id`, `status`, scores, protocol identifiers) across locales.
- Added a client-side English/Russian selector to the self-contained HTML dashboard without requiring a rescan.
- Added `language` support to FastAPI and MCP interfaces and a `/scan/dashboard` API endpoint.
- Expanded the test suite from 11 to 16 tests with localization regression coverage.

## 0.2.0 — 2026-08-07

- Added YAML configuration and `agentready init`.
- Added supplemental `llms-txt`, `markdown-index-fallback`, and `markdown-efficiency` checks.
- Added generic `--include` / `--exclude` check selection.
- Added `--with-llms`, `--with-markdown-fallback`, and `--with-markdown-efficiency` shortcuts.
- Added `--min-score`, `--min-level`, `--ci`, and config-driven gates.
- Added `transparent-tiered-v2` sequential maturity model with configurable threshold and next-tier progress.
- Reclassified Web Bot Auth as informational by default because applicability is contextual.
- Added impact/effort prioritized recommendations.
- Added ready-to-paste coding-agent remediation prompts.
- Added evidence metrics for content efficiency checks.
- Improved HTML and Markdown reports.
- Baseline comparison now detects maturity-level regressions and reports score decreases.
- Expanded HTTP API and MCP arguments for supplemental checks.
- Expanded test suite from 7 to 11 unit tests and repeated full end-to-end fixture validation.

## 0.1.0
- Initial revision
