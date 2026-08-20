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

```

### Optional dependency FAQ

`pip install -e .` installs only the core runtime. It does not install the
MCP server or Playwright extras. Use `requirements-dev.txt` for the complete
developer and portable-build environment, or install the needed extras
explicitly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# alternatively:
.\.venv\Scripts\python.exe -m pip install -e ".[mcp]"
.\.venv\Scripts\python.exe -m pip install -e ".[server]"
.\.venv\Scripts\python.exe -m pip install -e ".[ai]"
```

The default pytest collection requires the `mcp` module because the acceptance
matrix imports the MCP v2 contract at collection time. Install
`requirements-dev.txt` in the same virtual environment used by pytest before
running the suite; do not rely on optional-test skips.
If `agentready mcp` is started without the extra, it prints the same repair
command and an import verification command.

Playwright's Python package and its Chromium executable are separate
installations. For `--render` audits and browser-backed tests, run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[portable]"
.\.venv\Scripts\python.exe -m playwright install chromium
```

If Chromium is missing, `BrowserPool` reports the exact install command rather
than exposing Playwright's low-level launch error. Browser binaries are not
required to build the portable executable, only to run rendered audits/tests.bash
pip install -e '.[server]'
pip install -e '.[mcp]'
pip install -e '.[ai]'
```

For a standalone Windows build, run `scripts\build-portable.ps1 -Clean`. The
result is `dist\portable\agentready.exe`; it includes version metadata and the
command-line application icon.

## First Scan

```bash
agentready audit https://example.com --mode readiness
```

Useful presets:

```bash
agentready audit https://docs.example.com --mode readiness --preset content
agentready audit https://api.example.com --mode readiness --preset api
agentready audit https://example.com/article/ --mode readiness --preset ai-search --lang ru
agentready audit https://example.com --mode readiness --preset all --lang en
```

The `all` preset runs the complete readiness set, including GEO-scored checks.
The browser dashboard's **All checks** profile also runs the independent SEO
audit and combines both report sections in one HTML result.

Independent SEO audit:

```bash
agentready audit https://example.com/article/ --mode seo --format html -o seo.html
# Cross-page checks (broken links, duplicate metadata, redirect chains)
agentready audit https://example.com --mode seo --crawl --max-pages 25
# Headless-browser rendering for JS-driven sites
agentready audit https://example.com --mode seo --crawl --render
```

The audit runs 23 single-page checks; `--crawl` adds 6 cross-page checks from a bounded same-origin crawl (default: 25 pages). The result includes explicit coverage and affected-URL evidence; a capped or interrupted crawl is not a statement about the entire site.

Marketer inventory workflow:

```bash
agentready inventory RUN_ID pages --search "product" --sort-by title --format csv -o pages.csv
agentready view list --base-url http://127.0.0.1:8765
agentready compare https://example.com --baseline baseline.json
agentready rescan https://example.com --rescan-of RUN_ID --select-url https://example.com/page
```

The dashboard uses the same typed inventory path. Saved views retain the
selected kind, filter, limit, sort field, and direction. `agentready audit`
remains the canonical local execution command; inventory/view/compare/rescan
commands address an already running local v2 service.

Analytics checks (GA4 traffic/bounce, Search Console clicks/impressions) run when Google credentials are configured:

```bash
pip install -e '.[analytics]'
agentready credentials set service-account.json
agentready credentials status
agentready audit https://example.com/page --mode seo --ga-property 123456789 --gsc-site https://example.com/
```

The service-account JSON is stored in the OS credential vault (Windows Credential Manager via `keyring`); `GOOGLE_APPLICATION_CREDENTIALS` is a supported fallback. API payloads are read-only (`analytics.readonly`, `webmasters.readonly` scopes).

Mobile-friendliness audit:

```bash
agentready audit https://example.com --mode mobile
agentready audit https://example.com https://example.com/about --mode mobile --render --format html -o mobile.html
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
# Allow a slower model more time per attempt and one extra retry.
agentready ai chat https://example.com --provider-timeout 120 --provider-max-retries 1 --message "Summarize the highest-impact fixes"
```

`OPENAI_API_KEY` is supported as a process-environment fallback. Keys are never
accepted as ordinary CLI arguments, written to reports, or logged. AI HTTP/MCP
operations require both enablement flags and loopback binding; use an
authenticated external gateway for any future remote deployment. Advice is
non-executing and cannot guarantee rankings or indexing.

## Common Scan Options

```bash
agentready audit https://example.com --mode readiness --include markdown-negotiation
agentready audit https://example.com --mode readiness --exclude oauth-discovery --exclude oauth-protected-resource
agentready audit https://example.com --mode readiness --include llms-txt --include markdown-index-fallback --include markdown-efficiency
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
