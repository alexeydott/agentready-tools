[← Previous Page](getting-started.md) · [Back to README](../README.md) · [Next Page →](geo-and-indexnow.md)

# Checks & Methodology

## Core Check Categories

The default `all` preset includes 20 core scored surfaces:

| Category | Checks |
|---|---|
| Discoverability | `robots-txt`, `sitemap`, `link-headers`, `dns-aid` |
| Content Accessibility | `markdown-negotiation` |
| Bot Access Control | `ai-bot-rules`, `content-signals`, `web-bot-auth` |
| Protocol Discovery | `api-catalog`, `oauth-discovery`, `oauth-protected-resource`, `auth-md`, `mcp-server-card`, `a2a-agent-card`, `agent-skills`, `webmcp` |
| Commerce | `x402`, `mpp`, `ucp`, `acp` |

List checks with references:

```bash
agentready checks --json
```

## Supplemental Content Checks (Opt-in)

- `llms-txt`
- `markdown-index-fallback`
- `markdown-efficiency`

Enable explicitly:

```bash
agentready scan https://docs.example.com \
  --include llms-txt \
  --include markdown-index-fallback \
  --include markdown-efficiency
```

## Scoring Model

Only deterministic core scored checks contribute to the main score:

```text
score = round(100 * passed_scored_checks / applicable_scored_checks)
```

Supplemental, experimental, skipped, and error-only checks do not silently inflate the score.

## Maturity Levels

- Level 0 — Not Agent-Ready
- Level 1 — Basic Web Presence
- Level 2 — Bot-Aware
- Level 3 — Agent-Readable
- Level 4 — Agent-Integrated
- Level 5 — Agent-Native

Tiers are sequential and use a configurable pass ratio (default `0.8`).

## Recommendations

Each failed/warn/error result can produce:

- action
- reason
- impact (`high|medium|low`)
- effort (`low|medium|high`)
- numeric priority

The output is sorted to surface higher-impact, lower-effort actions first.

## See Also

- [GEO & IndexNow](geo-and-indexnow.md) — separate GEO profile and publishing workflows
- [Configuration & CI](configuration-and-ci.md) — thresholds and gate behavior
- [Reporting](reporting.md) — how model outputs are rendered
