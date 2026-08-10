[Back to README](../README.md) · [Next Page →](checks-and-methodology.md)

# Getting Started

## Prerequisites

- Python 3.11+
- pip
- Internet access to reach scan targets

## Installation

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e .
```

For a complete clean developer environment, including tests and the portable
build dependencies, use the repository requirements file:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Optional extras:

```bash
pip install -e '.[server]'
pip install -e '.[mcp]'
pip install -e '.[ai]'
```

For a standalone Windows build, run `scripts\build-portable.ps1 -Clean`. The
result is `dist\portable\agentready.exe`; it includes version metadata and the
command-line application icon.

## First Scan

```bash
agentready scan https://example.com
```

Useful presets:

```bash
agentready scan https://docs.example.com --preset content
agentready scan https://api.example.com --preset api
agentready scan https://example.com/article/ --preset ai-search --lang ru
agentready scan https://example.com --preset all --lang en
```

The `all` preset runs the complete readiness set, including GEO-scored checks.
The browser dashboard's **All checks** profile also runs the independent SEO
audit and combines both report sections in one HTML result.

Independent SEO audit:

```bash
agentready seo audit https://example.com/article/ --format html -o seo.html
# Cross-page checks (broken links, duplicate metadata, redirect chains)
agentready seo audit https://example.com --crawl --max-pages 25
# Headless-browser rendering for JS-driven sites
agentready seo audit https://example.com --crawl --render
```

The audit runs 23 single-page checks; `--crawl` adds 5 cross-page checks from a bounded same-origin crawl (default: 25 pages).

Analytics checks (GA4 traffic/bounce, Search Console clicks/impressions) run when Google credentials are configured:

```bash
pip install -e '.[analytics]'
agentready seo credentials set service-account.json
agentready seo credentials status
agentready seo audit https://example.com/page --ga-property 123456789 --gsc-site https://example.com/
```

The service-account JSON is stored in the OS credential vault (Windows Credential Manager via `keyring`); `GOOGLE_APPLICATION_CREDENTIALS` is a supported fallback. API payloads are read-only (`analytics.readonly`, `webmasters.readonly` scopes).

Mobile-friendliness audit:

```bash
agentready mobile audit https://example.com
agentready mobile audit https://example.com https://example.com/about --render --format html -o mobile.html
```

This checks one or more pages for Google Mobile-Friendly signals (viewport, responsive CSS, fixed widths, touch targets, font readability, indexability). `--render` adds Playwright-rendered viewport metrics and requires the `playwright` extra.

## Optional SEO/GEO AI Assistant

The assistant is disabled by default and never runs during ordinary audits. Install
the optional dependencies, enable it in `.agentready.yml`, then store the key in
the Windows Credential Manager (or another OS keyring):

```yaml
ai:
  enabled: true
  transport_enabled: true
  model: gpt-4o-mini
  base_url: https://api.openai.com/v1
  language: en
```

```bash
agentready ai credentials set
agentready ai credentials status
agentready ai recommend https://example.com --mode both
agentready ai chat https://example.com --mode seo --message "Prioritize technical fixes"
```

`OPENAI_API_KEY` is supported as a process-environment fallback. Keys are never
accepted as ordinary CLI arguments, written to reports, or logged. AI HTTP/MCP
operations require both enablement flags and loopback binding; use an
authenticated external gateway for any future remote deployment. Advice is
non-executing and cannot guarantee rankings or indexing.

## Common Scan Options

```bash
agentready scan https://example.com --only markdown-negotiation
agentready scan https://example.com --exclude oauth-discovery --exclude oauth-protected-resource
agentready scan https://example.com --with-llms --with-markdown-fallback --with-markdown-efficiency
```

## Validate Installation

```bash
agentready checks
agentready checks --json
```

## See Also

- [Checks & Methodology](checks-and-methodology.md) — scoring, tiers, and check categories
- [Configuration & CI](configuration-and-ci.md) — config and quality gates
- [Reporting](reporting.md) — output formats and baselines
