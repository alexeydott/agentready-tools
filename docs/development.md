[← Previous Page](safety.md) · [Back to README](../README.md) · [Next Page →](dashbord_faq_ru.md)

# Development

The current release is **0.10.0**. The package version, compatibility manifest,
report defaults, and Win64 file metadata are synchronized from the same release
change.

## Project Layout

```text
src/agentready/
  checks.py           protocol and supplemental checks
  registry.py         check metadata and presets
  scanner.py          orchestration and baselines
  scoring.py          numeric score + transparent maturity model
  recommendations.py  prioritized improvement plan
  remediation.py      implementation guidance + agent prompts
  config.py           YAML config loading/template
  i18n.py             report/dashboard localization catalogs
  http.py             bounded HTTP client and evidence capture
  target.py           URL normalization and SSRF policy
  fetcher.py          bounded fetch and evidence/storage boundary
  egress.py           public-target egress and redirect policy
  security.py         shared redaction and security helpers
  report.py           console/JSON/Markdown/HTML
  report_v2.py        additive v2 report contract and evidence projection
  audit_service.py    shared v2 application boundary and child-run lineage
  audit_core/         run lifecycle, canonical contracts, and Memory/SQLite store
  query_service.py    typed bounded inventory projections and pagination
  saved_views.py      bounded persisted QuerySpec views
  discovery.py        URL/list/sitemap/crawl discovery sources
  sitemap_reconciliation.py  sitemap inventory reconciliation and XML export
  link_graph.py       bounded internal link graph and authority projections
  duplicates.py       boilerplate-aware exact/near duplicate signatures
  custom_rules.py     bounded declarative extraction and debugger
  exports.py          bounded inventory formats and presentation branding
  jobs_v2.py          bounded asynchronous job lifecycle
  compatibility.py    v1/v2 compatibility manifest and migration metadata
  gitutils.py         Git→URL mapping and publication-date audit
  indexnow.py         IndexNow key/verification/submission client
  accesslog.py        AI crawler access-log analysis
  geo_rules.py        project-policy template generator
  agentfindings.py    agent-facing findings/remediation-plan builders
  seo_models.py       SEO report models (agentready.seo.v1)
  seo_checks.py       single-page SEO checks
  seo_crawler.py      bounded same-origin crawler + cross-page SEO checks
  seo_scoring.py      SEO score aggregation
  seo_recommendations.py  SEO recommendation ranking
  seo_report.py       SEO console/JSON/Markdown/HTML rendering
  seo_scanner.py      SEO audit orchestration
  mobile_models.py    mobile report models (agentready.mobile.v1)
  mobile_checks.py    static mobile-friendliness checks
  mobile_render.py    optional Playwright-rendered mobile checks
  mobile_scoring.py   mobile score aggregation
  mobile_report.py    mobile console/JSON/Markdown/HTML rendering
  mobile_scanner.py   mobile audit orchestration
  crawler.py          v2 deterministic bounded frontier crawler
  page_parser.py      shared parsed-page evidence model
  browser_pool.py     optional Playwright browser pool and egress interception
  crawl_profiles.py   quick/standard/deep/custom crawl limits
  robots.py           RFC 9309 and provider robots policies
  sitemap.py          bounded sitemap/index parsing and scope reconciliation
  crawler_identity.py crawler intent and identity confidence evidence
  interaction.py      offline accessibility and semantic interaction findings
  metrics.py           opt-in external enrichment provider adapters
  protocols/          versioned passive protocol auditors and adapters
  seo/                shared SEO evidence and atomic rule engine
  dashboard.py        localized browser dashboard and combined audit presentation
  report_styles.py    shared HTML report styles and tooltip presentation
  cli.py              CLI and CI gates
  server.py           optional FastAPI API
  mcp_server.py       optional MCP facade
```

## Validation Commands

```bash
PYTHONPATH=src pytest -q
python -m compileall -q src
```

For a clean Windows validation, create a new 64-bit Python 3.12 virtual
environment and install `requirements-dev.txt`. This installs the package,
test runner, MCP/Playwright optional dependencies, and all portable-build
dependencies through `pip`. Playwright browser binaries are a separate step:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

Without the `mcp` extra, MCP-specific tests are reported as skipped. Without
the Chromium binary, browser-backed tests and `--render` audits cannot run;
the portable build itself does not require that binary.

The `full-extra` GitHub Actions workflow installs MCP, Playwright, and Chromium
and runs the suite as a no-optional-skips release gate. Local development may
still use the smaller dependency set when browser/MCP work is not in scope.

### L0-L4 acceptance matrix

`tests/test_acceptance_matrix.py` keeps the release boundary explicit:

| Level | Coverage | Execution |
| --- | --- | --- |
| L0 | Typed request and contract unit checks | Every test run |
| L1 | Deterministic local dashboard/fixture behavior | Every test run |
| L2 | CLI, FastAPI, and MCP request-field parity | Every test run |
| L3 | Dashboard accessibility and inventory controls | Full-extra suite and headed acceptance |
| L4 | Opt-in live-site smoke | `workflow_dispatch` only; never a blocking default gate |

L4 must use bounded targets and explicit operator consent. It is not a
replacement for deterministic fixture coverage.

## Portable Windows Build

Build the standalone executable with:

```powershell
.\scripts\build-portable.ps1 -Clean
```

The output is `dist\portable\agentready.exe`. The PyInstaller spec embeds
version information and `packaging\agentready.ico` as the application icon.

## Source archive

Create a distributable source archive without AI Factory files, agent
artifacts, hidden working directories, caches, reports, or previous build outputs.
The script also excludes the planning-only `docs\vNext` and
`docs\presentations` trees; product schemas under `schemas\` remain included:

```powershell
.\scripts\package-source.ps1
```

The archive is written to
`dist\source\agentready-tools-<version>-source.zip` and includes only the
package source, documentation, tests, examples when present, and build
metadata.

The browser regression runner is kept in `scripts\dashboard-interactive.py`.
It can run a headed Edge smoke suite, including the combined `all` profile,
report download/print actions, AI interactions, localization, and browser
diagnostics:

```powershell
python scripts\dashboard-interactive.py `
  --url http://127.0.0.1:8000 `
  --target https://example.com `
  --edge "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" `
  --headed
```

The runner uses `/dashboard` as the product route and verifies dashboard and
chat `localStorage` restoration without restoring raw API keys into browser
storage or password fields. It also treats unavailable optional AI chat
providers as explicit skips rather than product failures. The direct module
entrypoint is available for CLI smoke checks:

```powershell
python -m agentready.cli --help
python -m agentready.cli audit https://example.com --profile quick --max-pages 1
```

## Localization Notes

- Built-in locales: `en`, `ru`
- Machine-stable check IDs remain unchanged across locales
- Human-facing text (titles/reasons/guidance) is localized

## Release Context

- 0.4.0 introduced separate GEO scoring and IndexNow/GEO utilities
- Core and GEO scoring remain intentionally separated
- 0.8.0 introduced the v2 contract, bounded crawler, protocol profiles,
  independent SEO/mobile domains, jobs, diffs, exports, and compatibility
  metadata.
- 0.8.1 preserved that v1-compatible surface and fixed combined dashboard
  report composition, including report-local tooltip styles.
- 0.9.0 hardens dashboard AI prompt localization/editing, browser persistence
  checks, module CLI execution, and synchronized release metadata.

## See Also

- [Getting Started](getting-started.md) — install and first scan
- [Reporting](reporting.md) — outputs and baselines
- [Configuration & CI](configuration-and-ci.md) — test gates and thresholds
