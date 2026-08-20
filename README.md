# AgentReady Tools

> Audit public websites for AI-agent protocol readiness and AI Search/GEO readiness.

AgentReady Tools is a Python toolkit that checks whether a site is easy for autonomous AI agents to discover, read, authenticate to, integrate with, and transact with. It follows Cloudflare-style public methodology for protocol readiness, adds optional GEO checks, and provides reproducible scoring, CI gates, and remediation guidance.

> AgentReady does **not** claim score compatibility with Cloudflare. The formulas here are explicit and reproducible for this project.

## Independent SEO audit

The separate SEO mode audits the selected page (23 single-page checks: metadata, indexability, canonical, robots.txt/sitemap, images, HTTPS/mixed content, URL format, content quality, performance, hreflang, structured data) plus an optional bounded same-origin crawl (broken links, redirect chains, duplicate metadata across pages, internal nofollow, link counts, HTTPS-to-HTTP links). It does not predict rankings, query Search Console/Yandex Webmaster, or modify the target:

```bash
agentready audit https://example.com --mode seo --format html -o seo.html
agentready audit https://example.com --mode seo --lang ru --min-score 80
# Cross-page checks via a bounded same-origin crawl
agentready audit https://example.com --mode seo --crawl --max-pages 25
# Headless-browser link extraction for JS-driven sites (requires Playwright)
agentready audit https://example.com --mode seo --crawl --render
```

Checks requiring Google Analytics / Search Console credentials (traffic, impressions, bounce data) run when configured — see [Getting Started](docs/getting-started.md). External PageSpeed/GA4/GSC/URL Inspection observations are opt-in enrichments with timestamps and do not affect the deterministic core score. The audit never mutates the target.

For marketer workflows, use the reusable v2 inventory workspace in the dashboard
or the transport-neutral CLI/API/MCP surfaces. A run exposes typed pages, links,
resources, redirects, findings, metrics, saved views, comparison, bounded
rescan, and export; partial crawl coverage remains explicitly partial.

## Mobile-friendliness audit

The mobile mode audits one or more pages for Google Mobile-Friendly signals. Static checks (viewport, responsive CSS, fixed-width elements, touch targets, font readability, indexability) run without a browser; `--render` adds Playwright-rendered viewport metrics:

```bash
agentready audit https://example.com --mode mobile
agentready audit https://example.com https://example.com/about --mode mobile --render --format html -o mobile.html
```

Mobile reports use the canonical `agentready.mobile.v2` JSON schema and are available as console, JSON, Markdown, and HTML. The API exposes `POST /v2/mobile/audit` and `POST /v2/mobile/audit/dashboard`; the MCP facade exposes v2 audit projections.

SEO reports use the canonical `agentready.seo.v2` JSON schema and are available as console, JSON, Markdown, and HTML. The API exposes `POST /v2/seo/audit` and `POST /v2/seo/audit/dashboard`; the MCP facade exposes v2 audit projections. Remote transports reject private targets and retain bounded timeout, redirect, response-size, and TLS controls.

## Quick Start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e .
agentready audit https://example.com --mode readiness
```

### Clean developer setup and build

The source archive contains everything needed for development, testing, and
the Windows portable build. Only a supported 64-bit Python installation and
`pip` are prerequisites; Python packages are installed from the project
metadata:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q src
.\.venv\Scripts\Activate.ps1
.\scripts\build-portable.ps1 -Clean
.\dist\portable\agentready.exe --help
```

To create the source distribution ZIP (without AI context, caches, reports,
or previous build output), run:

```powershell
.\scripts\package-source.ps1
```

Python 3.11 or newer is supported by the package; use 64-bit Python 3.12 for
the reproducible Win64 portable build. Browser binaries are not required to
build the executable. Install Playwright browsers separately only when using
rendered mobile or SEO checks:

```powershell
python -m playwright install chromium
```

`requirements-dev.txt` explicitly installs the complete developer/build test
environment through the `dev`, `mcp`, and `portable` extras. The default pytest
collection therefore requires the MCP Python package because the acceptance
matrix imports the MCP v2 contract at collection time; install
`requirements-dev.txt` before running the suite. Installing the Playwright
package does not install browser binaries. If rendered SEO/mobile tests fail
with a missing Chromium executable, run `python -m playwright install chromium`
in the same virtual environment.

If `agentready mcp` reports a missing MCP dependency, activate the same
environment used by `agentready` and run
`python -m pip install -e ".[mcp]"`. Verify the installation with
`python -c "import mcp; print(mcp.__file__)"`.

### Windows portable executable

The standalone Win64 build is distributed as `agentready.exe`. It includes the
CLI, FastAPI `serve`, the MCP facade (`agentready mcp`), and the documented
Google indexing dependencies:

```powershell
.\scripts\build-portable.ps1 -Clean
.\dist\portable\agentready.exe --help
```

The executable contains Windows version information and the AgentReady command
line application icon.

## Key Features

- **Protocol readiness checks** across discoverability, content accessibility, bot controls, protocol discovery, and commerce signals.
- **Separate AI Search/GEO score** (`ai_search_score`) so GEO quality does not overwrite core protocol readiness.
- **CI gating support** via minimum score and optional strict fail-on-checks behavior.
- **Canonical v2 audit contract** with bounded evidence, coverage accounting, deterministic finding fingerprints, baseline diff, rescan, inventory pagination, JSONL/CSV export, and bounded asynchronous jobs.
- **AuditService-backed v2 dashboard profile** with escaped report projection and bounded server-side run inventory APIs for pages, URLs, links, resources, redirects, findings, and metrics.
- **Bounded v2 crawler foundation** with deterministic frontier/scope accounting, shared fetch and egress policy, robots/sitemap reconciliation, protocol profiles, and optional browser rendering.
- **Prioritized recommendations** ranked by impact and effort.
- **Multiple output formats**: console, JSON, Markdown, HTML dashboard (with EN/RU localization).
- **Integration surfaces**: CLI, optional FastAPI API, optional MCP endpoint (including `audit_findings`/`remediation_plan` tools that hand coding agents concrete optimization gaps with step-by-step fix instructions).
- **Independent SEO mode** with Google/Yandex best-practice checks and SEO-only baselines/thresholds.
- **Combined dashboard profile** where “All checks” runs GEO/readiness and SEO and presents both sections in one report.
- **Mobile-friendliness audit** with static HTML/CSS checks plus optional Playwright-rendered viewport metrics, available in CLI, API, and MCP.
- **Explicit indexing publishers**: global/Yandex IndexNow and eligible-content Google Indexing API workflows.
- **Opt-in SEO/GEO AI assistant** using an OpenAI-compatible API, bounded audit context, OS-vault credentials, and EN/RU CLI/API/MCP flows.
- **Serve-mode AI chat** for asking follow-up questions about the completed audit, with bounded conversation history, text-file attachments, selectable skills, and AgentReady MCP findings/remediation context.
- **Large-report-safe AI handoff** with provider-aware dashboard deadlines, deterministic context projection, structured error details, and resumed-session recovery from the embedded v2 report.
- **Restorable dashboard sessions** with browser-local audit/chat state, redacted OS-vault credential status, stable localized prompt editing, and explicit failure rendering.
- **Portable serve state** stored under `.cache` beside the executable by default (or `serve --data-dir <path>`), created automatically at startup.
- **Prompt library and chat archive** for reusable SEO/GEO questions and JSON conversation files in the serve cache.

## Example

```bash
# Full protocol + GEO run with CI gates
agentready audit https://example.com --mode readiness \
  --preset ai-search --min-score 80 --fail-on-checks \
  --format markdown -o report.md
```

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](docs/getting-started.md) | Installation, commands, first scans |
| [Checks & Methodology](docs/checks-and-methodology.md) | Core checks, supplemental checks, scoring model |
| [GEO & IndexNow](docs/geo-and-indexnow.md) | AI Search profile and indexing notification workflows |
| [Configuration & CI](docs/configuration-and-ci.md) | `.agentready.yml`, environment, overrides, gates |
| [Reporting](docs/reporting.md) | JSON/Markdown/HTML outputs, baselines |
| [Integrations](docs/integrations.md) | HTTP API and MCP usage |
| [Yandex provider decision](docs/yandex-provider-decision-2026-08-12.md) | Dated official-API assessment and safe deferral |
| [Safety](docs/safety.md) | Network, crawler, commerce safety boundaries |
| [Architecture](docs/architecture.md) | Runtime layers and the canonical v2 contract |
| [Development](docs/development.md) | Project layout and validation |
| [Operations](docs/operations.md) | v2 collection, inventory, providers, limits, migrations, backup/restore, troubleshooting |
| [Dashboard FAQ (RU)](docs/dashbord_faq_ru.md) | Beginner dashboard guide in Russian |
| [Dashboard FAQ (EN)](docs/dashbor_faq_en.md) | Beginner dashboard guide in English |

## Additional Root Docs

- [CHANGELOG.md](CHANGELOG.md)
- [RESEARCH.md](RESEARCH.md)
- [NOTICE.md](NOTICE.md)

## Sources

- https://blog.cloudflare.com/agent-readiness/
- https://isitagentready.com/
- https://github.com/kodustech/agent-readiness
- https://tochkicamp.ru/guides/kak-optimizirovat-sayt-pod-ai-poisk/
- https://www.indexnow.org/documentation
- https://developers.google.com/search/apis/indexing-api/v3/using-api

## License

MIT
