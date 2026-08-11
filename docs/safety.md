[← Previous Page](integrations.md) · [Back to README](../README.md) · [Next Page →](development.md)

# Safety

## Network Safety Defaults

The HTTP client:

- follows at most 5 redirects
- caps responses at 5 MiB
- defaults to 5-second timeout
- validates redirects in public-only mode
- can block loopback/RFC1918/link-local/ULA/reserved targets
- redacts cookies and authorization-sensitive headers from evidence

For untrusted targets:

```bash
agentready scan https://example.com --block-private
```

The v2 crawler uses one bounded Fetcher/EgressPolicy boundary for HTTP and
one BrowserPool boundary for rendered requests. Trusted-local credentials are
CLI-only, require loopback targets and an explicit header allowlist, and are
blocked on cross-origin redirects unless an explicit policy opt-in is used.
Remote API/MCP requests remain passive and cannot supply credential contexts.

FastAPI and MCP facades always operate in public-target mode.

## Commerce Safety

Commerce checks (`x402`, `MPP`, `UCP`, `ACP`) inspect unauthenticated challenge metadata only. The scanner does not submit payment credentials or perform paid transaction retries.

Example:

```bash
agentready scan https://shop.example.com \
  --commerce-url https://api.example.com/paid-resource
```

## GEO/Crawler Diagnostic Boundaries

- Crawler user-agent probing is diagnostic and cannot prove official crawler-IP acceptance.
- Date and citation heuristics are guidance, not ranking guarantees.

## SEO Crawl Boundaries

- `seo audit --crawl` is bounded: same-origin only, deduplicated URLs, default cap of 25 pages (`--max-pages`, max 100 in API).
- The crawl follows links but never submits forms, credentials, or mutations.
- `--render` runs headless Chromium locally; rendered content is only read, never modified.

## Analytics Credentials

- GA4/Search Console checks use a Google service account with read-only scopes (`analytics.readonly`, `webmasters.readonly`).
- The JSON key is stored in the OS credential vault via `keyring`; it is never written to reports, logs, or API responses.
- API/MCP analytics requests use the locally stored credential; there is no endpoint to upload or read credentials remotely.

## See Also

- [GEO & IndexNow](geo-and-indexnow.md) — GEO-specific limitations
- [Integrations](integrations.md) — running API/MCP safely
- [Checks & Methodology](checks-and-methodology.md) — category rationale
