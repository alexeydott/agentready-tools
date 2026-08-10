[← Previous Page](safety.md) · [Back to README](../README.md) · [Next Page →](dashbord_faq_ru.md)

# Development

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
  report.py           console/JSON/Markdown/HTML
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
test runner, and all portable-build dependencies through `pip`.

## Portable Windows Build

Build the standalone executable with:

```powershell
.\scripts\build-portable.ps1 -Clean
```

The output is `dist\portable\agentready.exe`. The PyInstaller spec embeds
version information and `packaging\agentready.ico` as the application icon.

## Source archive

Create a distributable source archive without AI Factory files, agent
artifacts, caches, reports, or previous build outputs:

```powershell
.\scripts\package-source.ps1
```

The archive is written to
`dist\source\agentready-tools-<version>-source.zip` and includes only the
package source, documentation, tests, examples when present, and build
metadata.

## Localization Notes

- Built-in locales: `en`, `ru`
- Machine-stable check IDs remain unchanged across locales
- Human-facing text (titles/reasons/guidance) is localized

## Release Context

- 0.4.0 introduced separate GEO scoring and IndexNow/GEO utilities
- Core and GEO scoring remain intentionally separated

## See Also

- [Getting Started](getting-started.md) — install and first scan
- [Reporting](reporting.md) — outputs and baselines
- [Configuration & CI](configuration-and-ci.md) — test gates and thresholds
