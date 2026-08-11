[← Previous Page](geo-and-indexnow.md) · [Back to README](../README.md) · [Next Page →](reporting.md)

# Configuration & CI

## Generate Config

```bash
agentready init
agentready init --lang ru
```

Default config file: `.agentready.yml` (or `.agentready.yaml`).

## Config Structure

```yaml
preset: all

checks:
  include: []
  exclude: []

network:
  timeout: 5.0
  workers: 8
  verify_tls: true
  block_private: false

scoring:
  level_threshold: 0.8

gates:
  min_score: 80
  min_level: 3
  fail_on_checks: false

report:
  language: en

ai:
  enabled: false
  transport_enabled: false
  model: gpt-4o-mini
  base_url: https://api.openai.com/v1
  credential_id: openai-api-key
  active_provider: openai
  providers:
    - id: openai
      name: OpenAI
      base_url: https://api.openai.com/v1
      credential_id: openai-api-key
  timeout: 30.0
  max_retries: 2
  language: en
```

AI settings are trusted-local configuration. `ai.providers` stores named
provider profiles and `ai.active_provider` selects the profile shared by CLI,
serve, and MCP. Provider URLs must use HTTPS without userinfo, query, or
fragment; HTTP is allowed only for explicitly enabled loopback development
providers. Remote API/MCP callers cannot override the provider URL, credential
ID, or security controls. The serve dashboard can create, edit, activate, and
remove profiles; API keys remain in the OS credential vault.

The local `serve` dashboard stores its selected AI skills and MCP context
providers in `.cache/ai-tools.json` beside the running server by default.
Override the location with `agentready serve --data-dir <path>`; the directory
is created automatically.

## Discovery and Overrides

- CLI auto-searches upward for `.agentready.yml` / `.agentready.yaml`.
- CLI flags override config values.
- Use explicit config: `--config ./ci/agentready.yml`
- Disable discovery: `--no-config`

## Indexing Integration Environment

Indexing publisher credentials are intentionally not stored in `.agentready.yml`.

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_APPLICATION_CREDENTIALS` | unset | Path to a Google service-account JSON file used only by explicit `google-indexing` commands |
| `LOG_LEVEL` | `WARNING` | Publisher diagnostics on stderr: `DEBUG`, `INFO`, `WARNING`, or `ERROR` |

Install Google authentication support separately:

```bash
pip install -e ".[google]"
```

CLI `--credentials` overrides `GOOGLE_APPLICATION_CREDENTIALS` for one command. Never commit service-account JSON, OAuth tokens, or authorization headers. DEBUG logs include hosts, counts, status codes, and retry state but redact credentials and IndexNow keys.

## CI Gates

The additive v2 audit surface uses the same bounded controls from CLI, API,
and MCP projections. `profile`, `max_pages`, `limits`, `include`, `exclude`,
`render`, `provider`, and `language` are included in the deterministic
execution plan; provider names describe optional enrichment capabilities and
do not cause remote provider calls during the core crawl.

Command-line gates without `--ci`:

```bash
agentready scan https://example.com --min-score 80 --min-level 3
```

Use gate values from config:

```bash
agentready scan https://example.com --ci
```

Additional options:

```bash
agentready scan https://example.com --fail-on-checks
agentready scan https://example.com --preset ai-search --ci --min-ai-search-score 80
```

## Localization Controls

```bash
agentready scan https://example.com --lang ru
agentready scan https://example.com --language en
```

Language applies to human-facing fields while stable machine identifiers remain unchanged.

## See Also

- [Reporting](reporting.md) — output files and dashboard behavior
- [Checks & Methodology](checks-and-methodology.md) — scoring and maturity details
- [GEO & IndexNow](geo-and-indexnow.md) — publisher commands and safety limits
