# Operations guide

This guide describes the bounded v2 runtime. Examples use public targets and
contain no credentials.

## Collection sources and limits

The canonical `AuditService` supports single URL, URL list, local sitemap,
robots-sitemap, and bounded same-origin crawl discovery. Select a source with
the CLI or the matching v2 request fields:

```bash
agentready audit https://example.com --discovery single --profile quick --max-pages 10
agentready audit https://example.com --discovery crawl --profile standard --max-pages 25
agentready audit https://example.com --discovery sitemap --discovery-sitemap-xml sitemap.xml
```

`max-pages`, depth, duration, concurrency, response bytes, redirects, and
timeouts are hard bounded by the selected profile and `HARD_CAPS`. Partial
coverage is reported as partial; it is never presented as a complete crawl.
Remote API/MCP targets remain public-only. Rendered collection is optional and
requires the Playwright package plus a separately installed Chromium binary.

## Inventory, reports, and exports

Completed runs expose typed pages, run URLs, links, resources, redirects,
findings, and metrics through `/v2/runs/{run_id}/inventory/{kind}`. Use cursors
for pagination and keep only the current page in a UI. The dashboard, CLI,
MCP `run_inventory_v2`, and exports all consume these same projections:

```bash
agentready inventory RUN_ID pages --limit 100 --format csv -o pages.csv
agentready inventory RUN_ID findings --format json
agentready priority RUN_ID
```

HTML/JSON/JSONL/CSV/Markdown are the supported bounded formats. Coverage,
provenance, limits, and run IDs remain part of the canonical v2 report. PDF
and XLSX are intentionally deferred; do not install unapproved writers.

## Projects, history, and schedules

Projects keep non-secret target/profile/ruleset metadata and run memberships:

```bash
agentready projects create demo "Demo site" https://example.com --profile quick
agentready projects start demo --max-pages 10
agentready projects runs demo
agentready projects baseline demo RUN_ID
```

Scheduled audits are local and opt-in through the v2 schedule API/service.
Workers must be explicitly started; the product does not install an operating-
system scheduler. Leases, one catch-up policy, bounded backoff, cancellation,
and run lineage are persisted in the same local store.

## Optional providers and credentials

PageSpeed, GA4, GSC, and URL Inspection are explicit enrichment jobs. They are
budgeted, timestamped, cached/provenance-rich, and do not change readiness
scoring. Provider names in a core audit do not trigger remote calls. Configure
provider credentials through the CLI/OS vault; never put keys, cookies, or
authorization headers in YAML, HTTP/MCP JSON, reports, or issue text.

Trusted authenticated audits are a separate CLI-only loopback feature. They
require an explicit origin and an OS-vault reference; credentials are injected
only at the Fetcher collection boundary. Redirects outside the exact origin and
rendered browser mode are blocked. See [Safety](safety.md) for the vault
workflow and negative-boundary rules.

## Dependency profiles

```bash
pip install -e .                         # core CLI and public audits
pip install -e ".[server]"               # FastAPI/serve
pip install -e ".[mcp]"                  # MCP surface
pip install -e ".[analytics]"             # GA4/GSC provider clients
pip install -e ".[portable]"              # EXE build/runtime extras
pip install -r requirements-dev.txt       # complete test/build environment
```

Playwright browsers are installed separately with
`python -m playwright install chromium`. Optional dependency absence must be
reported as an explicit capability skip, not silently collected as a product
failure.

## Migrations and backup/restore

The SQLite store uses forward-only schema migrations and rejects newer schemas;
there are no down-migrations. Stop the serve process before copying
`audit.sqlite3`, or use a consistent SQLite backup procedure. Keep the adjacent
`saved-views.jsonl` when saved views are required, and restore into a copy
first. Retain only the required audit window and remove expired local data
according to the deployment policy.

## Troubleshooting

- `404 run not found`: the bounded in-process run cache evicted the run; use
  SQLite-backed serve mode for durable local history and re-run the audit if
  the inventory is no longer retained.
- `partial_limit` or `deadline`: lower concurrency or raise the bounded
  profile/page/time limit explicitly; do not interpret the score as complete
  coverage.
- Missing MCP: install the `mcp` extra in the same environment as the CLI and
  verify with `python -c "import mcp; print(mcp.__file__)"`.
- Missing rendered checks: install the Playwright extra and Chromium binary in
  the same environment.
- Provider unavailable/quota: inspect the typed provider status and provenance;
  missing enrichment is not a zero and does not fail the core audit.
- Secret appearing in output: stop publication, remove the artifact, rotate
  the credential, and inspect redacted logs before retrying. DEBUG output is
  intended to contain only hosts, counts, versions, hashes, and status codes.
