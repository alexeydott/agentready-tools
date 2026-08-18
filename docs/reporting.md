[← Previous Page](configuration-and-ci.md) · [Back to README](../README.md) · [Next Page →](integrations.md)

# Reporting

## Output Formats

Generate JSON:

```bash
agentready audit https://example.com --mode readiness --format json -o report.json
```

Generate Markdown:

```bash
agentready audit https://example.com --mode readiness --format markdown -o report.md
```

Generate HTML dashboard:

```bash
agentready audit https://example.com --mode readiness --format html -o report.html
```

## Localized Reports

```bash
agentready audit https://example.com --mode readiness --format markdown --lang ru -o report-ru.md
agentready audit https://example.com --mode readiness --format json --lang ru -o report-ru.json
agentready audit https://example.com --mode readiness --format html --lang ru -o dashboard.html
```

The HTML dashboard embeds English and Russian views with an in-browser language switcher.

The dashboard profile **All checks** runs the readiness/GEO scan and the
independent SEO audit, then composes one HTML report with separate GEO and SEO
sections. The combined report keeps the source report styles, including
keyboard-focus and hover hints, and supports one download and print action.

Every CLI, HTTP/dashboard, and MCP audit also writes a timestamped copy to
`.reports` beside the executable (portable builds) or the project root. Set
`AGENTREADY_REPORT_DIR` to choose another directory when running the dashboard
from source. Explicit `-o/--output` files are still written in addition to
this automatic archive.

SEO output uses the canonical `agentready.seo.v2` schema:

```bash
agentready audit https://example.com --mode seo --format json -o seo.json
agentready audit https://example.com --mode seo --baseline seo.json --min-score 80
# Cross-page checks via a bounded same-origin crawl
agentready audit https://example.com --mode seo --crawl --max-pages 25 --format html -o seo.html
```

The SEO audit runs 23 single-page checks (metadata, indexability, canonical, images, HTTPS/mixed content, URL format, content quality, performance, hreflang, structured data); `--crawl` adds 6 cross-page checks (broken links, redirect chains, duplicate metadata, internal nofollow, link counts, HTTPS-to-HTTP links). `--render` extracts links from JS-driven pages through headless Chromium.

## Structured evidence

Evidence is preserved across JSON, HTML, Markdown, console, MCP, and AI report surfaces when a check produces it. In addition to the check finding, consumers may receive:

- `url`: the fetched or affected source URL;
- `page`: the containing page URL;
- `resource`: the affected resource URL;
- `metrics`: bounded check-specific values such as image attributes or title length.

When presenting findings, keep page and resource locations distinct and do not infer a location that is absent from the evidence.

SEO baselines reject Agent Readiness JSON and only compare SEO score/check regressions.

## v2 Reports, jobs, and inventory operations

The canonical `agentready.audit.v2` report includes:

- normalized audit configuration and version metadata;
- bounded evidence with source/page/resource locations and metrics;
- coverage counters for discovered, attempted, completed, skipped, and failed work;
- stable finding fingerprints for comparison across runs.
- run metadata including the deterministic configuration hash, lifecycle state,
  parent-run lineage, and child-rescan identity.

The v2 API supports synchronous audit, rescan, baseline diff, and bounded
inventory export. Inventory data can be paginated for UI/API consumers and
exported as JSONL or CSV. Long-running operations use bounded in-memory jobs
with explicit queued/running/completed/failed/cancelled states. These features
are the canonical report and execution contract; legacy v1 report schemas are not accepted.

For a marketer workspace, the dashboard and `agentready inventory` command
share the same typed query semantics. Saved views, comparison, selected URL
rescan, provider metric rows, and CSV/JSONL/Markdown/HTML export operate on
bounded projections rather than raw JSON blobs.

Mobile-friendliness output uses the canonical `agentready.mobile.v2` schema with per-page and aggregate scores:

```bash
agentready audit https://example.com --mode mobile --format json -o mobile.json
agentready audit https://example.com https://example.com/about --mode mobile --render --format html -o mobile.html
```

## Baselines and Regressions

Create baseline:

```bash
agentready audit https://example.com --mode readiness --format json -o baseline.json
```

Compare against baseline:

```bash
agentready audit https://example.com --mode readiness --baseline baseline.json
```

Regression types include:

- scored check `pass -> fail`
- newly introduced scored failure
- maturity-level decrease

The v2 diff projection also reports new, fixed, persisting, changed, and
regressed findings; coverage and bounded inventory deltas; rule-version
changes; and explicitly incomparable run pairs. Localized text and input order
do not alter finding identity. Different targets, schemas, or report versions
are rejected as incomparable instead of producing a misleading regression.

## Remediation Prompts

Reports include ready-to-paste coding-agent prompts for failed/warning checks to speed implementation follow-ups.

## See Also

- [Configuration & CI](configuration-and-ci.md) — threshold and gate policies
- [Checks & Methodology](checks-and-methodology.md) — check taxonomy and score model
- [Integrations](integrations.md) — API/MCP report automation
# Spreadsheet export decision

XLSX is explicitly deferred as non-blocking for the 0.12.x SEO marketer
surface. The dependency-free JSON/JSONL/CSV/Markdown/HTML exports preserve
streaming bounds and portable packaging; adding XLSX would require auditing an
optional writer, multi-sheet memory behavior, and formula-injection tests before
it can be enabled. No XLSX writer or formula-bearing workbook is accepted by
the current contract.
# Explainable page priority (v2)

`GET /v2/runs/{run_id}/priority` and `agentready priority RUN_ID` return a stable,
override-free ranking using model `page-priority-v1`. Each item includes the
factor codes, normalized values, weights, availability, and source. The formula
uses severity, URL state, internal link authority, available traffic/search
metrics, recurrence, confidence, and freshness. Optional data is omitted from
the weighted denominator when absent, so a page is never penalized for a
provider that was not configured. Ties are resolved by canonical URL.
