# AGENTS.md

> Keep this file aligned with real repository structure and update it when project layout changes.

## Project Overview
AgentReady Tools is a Python package and CLI for auditing website AI-agent readiness, including protocol checks, optional GEO checks, explicit indexing publishers, and integration surfaces (CLI, API, MCP, and a localized dashboard).

## Tech Stack
- **Programming language:** Python 3.11+
- **Framework:** `argparse` CLI with optional `FastAPI`
- **Database:** None
- **ORM:** Not applicable

## Project Structure
```text
src/
  agentready/                 # Core package modules
    protocols/                # Versioned passive protocol auditors and adapters
    crawler.py                # v2 bounded async crawler and frontier
    audit_core/run_context.py # Immutable run identity and lifecycle coordinator
    audit_service.py           # Shared v2 application service and projections
    query_service.py            # Typed bounded QuerySpec projections
    plan_compiler.py            # Network-free deterministic execution planning
    discovery.py               # Bounded URL/list/sitemap/crawl discovery sources
    saved_views.py             # Bounded in-process saved QuerySpec views
    audit_core/contracts.py     # Canonical fact/evidence/finding identities
    page_parser.py            # Shared parsed-page representation
    browser_pool.py           # Optional async Playwright browser pool
    crawl_profiles.py         # Bounded quick/standard/deep/custom profiles
    robots.py                 # RFC 9309 and provider-specific robots policies
    sitemap.py                # Bounded secure sitemap/index parsing and scope
    seo/                      # Shared SEO evidence and atomic-rule engine
    report_v2.py              # Additive v2 evidence/coverage report contract
    jobs_v2.py                # Bounded asynchronous audit jobs
    compatibility.py          # v1/v2 compatibility manifest
    fetcher.py                # Shared bounded fetch/storage boundary
    egress.py                 # Public-target egress policy
    interaction.py            # Offline semantic interaction findings
    crawler_identity.py       # Crawler identity confidence evidence
    metrics.py                # Opt-in external enrichment adapters
tests/                        # Pytest suite
.ai-factory/                  # AI Factory context and generated setup artifacts
  DESCRIPTION.md              # Project specification for AI workflows
  rules/
    base.md                   # Detected coding conventions
.github/skills/               # Built-in AI Factory skills and helpers
.vscode/
  mcp.json                    # Project-level MCP server configuration
examples/                     # Sample artifacts/scripts
dist/                         # Build distribution artifacts
README.md                     # Main product and usage documentation
pyproject.toml                # Package metadata and dependencies
requirements.txt              # Runtime dependency pins
```

## Key Entry Points
| File | Purpose |
|------|---------|
| `src/agentready/cli.py` | Main CLI entrypoint and command routing. |
| `src/agentready/scanner.py` | Scan orchestration, scoring inputs, and baseline comparison. |
| `src/agentready/checks.py` | Protocol and supplemental audit implementations. |
| `src/agentready/structured_data.py` | Shared JSON-LD parsing and Google eligibility detection. |
| `src/agentready/indexnow.py` | Global and Yandex IndexNow key and submission flows. |
| `src/agentready/google_indexing.py` | Eligible-content Google Indexing API publish/status client. |
| `src/agentready/server.py` | Optional FastAPI HTTP API wrapper around scanner logic and dashboard/AI endpoints. |
| `src/agentready/report_v2.py` | Typed v2 reports, evidence, coverage, fingerprints, diffs and exports. |
| `src/agentready/jobs_v2.py` | Bounded asynchronous job lifecycle used by v2 endpoints. |
| `src/agentready/dashboard.py` | Localized browser dashboard and client-side audit/AI interactions. |
| `src/agentready/i18n.py` | Shared language normalization and EN/RU translation catalog. |
| `src/agentready/mcp_server.py` | Optional MCP surface for scan operations. |
| `scripts/dashboard-interactive.py` | Headed Playwright/DevTools acceptance runner for dashboard, AI, persistence, and live-site checks. |
| `src/agentready/agentfindings.py` | Agent-facing findings and remediation-plan builders for coding agents. |
| `src/agentready/mobile_scanner.py` | Multi-page mobile-friendliness audit orchestration (`agentready mobile`). |
| `src/agentready/seo_crawler.py` | Bounded same-origin crawler with cross-page SEO checks (`seo audit --crawl`). |
| `src/agentready/crawler.py` | v2 deterministic frontier, scope, coverage, and bounded async crawl engine. |
| `src/agentready/audit_core/run_context.py` | Immutable run context and explicit lifecycle transitions. |
| `src/agentready/audit_service.py` | Shared v2 AuditRequest/AuditService execution boundary. |
| `src/agentready/query_service.py` | Typed bounded page/run-url/link/resource queries with cursor pagination. |
| `src/agentready/plan_compiler.py` | Network-free capability and execution-plan compiler. |
| `src/agentready/discovery.py` | Bounded deterministic single-URL, list, sitemap, and crawler discovery. |
| `src/agentready/saved_views.py` | Bounded in-process registry for typed saved QuerySpec views. |
| `src/agentready/audit_core/contracts.py` | Canonical fact, evidence, finding, and localized-stable state contracts. |
| `src/agentready/browser_pool.py` | Optional one-process-per-run Playwright pool with shared egress interception. |
| `src/agentready/robots.py` | RFC 9309 baseline, provider interpretation, and virtual robots simulation. |
| `src/agentready/sitemap.py` | Bounded XML sitemap/index parser and ownership-aware scope classification. |
| `src/agentready/seo/` | Shared page evidence, atomic SEO rules, fingerprints, and v1 aggregation adapter. |
| `src/agentready/protocols/` | Versioned protocol profiles, passive document auditing, evidence locators, and agent/MCP adapters. |
| `src/agentready/crawler_identity.py` | Crawler intent, observed/verified identity confidence, and provider evidence model. |
| `src/agentready/interaction.py` | Offline accessibility-tree and semantic interaction findings. |
| `src/agentready/metrics.py` | Opt-in external provider adapters and CWV enrichment metrics kept outside core scoring. |
| `src/agentready/mobile_render.py` | Optional Playwright-rendered mobile viewport checks. |
| `.vscode/mcp.json` | MCP servers used in this workspace. |

## Documentation
| Document | Path | Description |
|----------|------|-------------|
| README | `README.md` | Project landing page and docs index. |
| Getting Started | `docs/getting-started.md` | Installation, setup, first scans. |
| Checks & Methodology | `docs/checks-and-methodology.md` | Check coverage, scoring, tiers. |
| GEO & IndexNow | `docs/geo-and-indexnow.md` | GEO and indexing notification workflows. |
| Configuration & CI | `docs/configuration-and-ci.md` | Config, environment, and gate controls. |
| Reporting | `docs/reporting.md` | Output formats and baseline diffs. |
| Integrations | `docs/integrations.md` | HTTP API and MCP usage. |
| Safety | `docs/safety.md` | Network and commerce safety limits. |
| Development | `docs/development.md` | Layout and validation commands. |
| Dashboard FAQ (RU) | `docs/dashbord_faq_ru.md` | Beginner guide to the dashboard in Russian. |
| Dashboard FAQ (EN) | `docs/dashbor_faq_en.md` | Beginner guide to the dashboard in English. |
| Changelog | `CHANGELOG.md` | Versioned change history. |
| Research Notes | `RESEARCH.md` | Supporting research context. |
| Notice | `NOTICE.md` | Attribution and notices. |

## AI Context Files
| File | Purpose |
|------|---------|
| `AGENTS.md` | Project map for AI agents and onboarding. |
| `.ai-factory/DESCRIPTION.md` | Setup-time project specification for AI Factory workflows. |
| `.ai-factory/ARCHITECTURE.md` | Architecture rules and boundaries generated by `/aif-architecture`. |
| `.ai-factory/rules/base.md` | Repository-wide baseline coding conventions. |

The dashboard uses `/dashboard` as its explicit browser test route. Dashboard
configuration and chat history may be restored from browser `localStorage`, but
credential values are restored only as redacted OS-vault status metadata.
Localized prompt edits carry a stable prompt ID and update only the selected
language variant.
The v2 dashboard preset is an `AuditService`-backed projection; completed
v2 runs expose bounded typed inventory through the `/v2/runs/{run_id}/...`
endpoints rather than arbitrary query parameters.

## Agent Rules
- Split shell workflows into explicit sequential commands instead of a single chained command when clarity or recovery matters.
  - Incorrect combined command example: `git checkout main && git pull`
  - Correct decomposed command example: first `git checkout main`, then `git pull origin main`
