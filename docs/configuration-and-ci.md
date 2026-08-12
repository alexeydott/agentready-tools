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

- `.agentready.yml` / `.agentready.yaml` is used by configuration-aware
  library, AI, and serve integrations. The canonical `audit` CLI takes its
  bounded execution options explicitly so its request is reproducible from
  the command line.
- `agentready init` creates the documented configuration template.

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

The canonical v2 audit surface uses the same bounded controls from CLI, API,
and MCP projections. `profile`, `max_pages`, `limits`, `include`, `exclude`,
`render`, `provider`, and `language` are included in the deterministic
execution plan; provider names describe optional enrichment capabilities and
do not cause remote provider calls during the core crawl.

External provider jobs are separately bounded and opt-in. They can persist
cached PageSpeed/GA4/GSC/URL Inspection observations with timestamps, but they
cannot alter the deterministic audit score. Credentials remain CLI/OS-vault
state and are not accepted by default HTTP/MCP audit requests.

Canonical command-line gates:

```bash
agentready audit https://example.com --mode readiness
```

Additional options:

```bash
agentready audit https://example.com --mode readiness --fail-on-checks
agentready audit https://example.com --mode readiness --preset ai-search
```

## Localization Controls

```bash
agentready audit https://example.com --mode readiness --lang ru
agentready audit https://example.com --mode readiness --language en
```

Language applies to human-facing fields while stable machine identifiers remain unchanged.

## See Also

- [Reporting](reporting.md) — output files and dashboard behavior
- [Checks & Methodology](checks-and-methodology.md) — scoring and maturity details
- [GEO & IndexNow](geo-and-indexnow.md) — publisher commands and safety limits
## Optional durable v2 serve history

The HTTP server keeps bounded in-process history by default. Set
`AGENTREADY_SERVE_SQLITE=1` and configure the serve data directory to enable
the existing `SQLiteSiteStore` at `audit.sqlite3`; WAL transactions, schema
migrations, interrupted-run recovery, and newer-schema rejection are then
handled by the store. Back up the SQLite file while the server is stopped (or
use a consistent SQLite backup), retain only the required audit window, and
remove expired database files according to the deployment retention policy.
Saved-view snapshots are stored as `saved-views.jsonl` beside the database;
unknown snapshot schemas are rejected and logged without dropping valid
records. Test a restore on a copy before replacing a production file.
