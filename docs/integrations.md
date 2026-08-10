[← Previous Page](reporting.md) · [Back to README](../README.md) · [Next Page →](safety.md)

# Integrations

## HTTP API

Start service:

```bash
agentready serve --host 127.0.0.1 --port 8765 --data-dir .cache
```

Trigger scan:

```bash
curl -X POST http://127.0.0.1:8765/scan \
  -H 'content-type: application/json' \
  -d '{
    "url":"https://example.com",
    "preset":"all",
    "language":"ru",
    "include":["llms-txt","markdown-index-fallback"]
  }'
```

The `/scan` endpoint supports every scanner preset through the `preset` field:
`all`, `content`, `api`, and `ai-search`. The equivalent check catalog is available
without running a network scan:

```bash
curl 'http://127.0.0.1:8765/checks?language=ru'
```

### v2 application/report contract

The additive v2 surface returns `agentready.audit.v2` reports with bounded
evidence, coverage, version metadata, and deterministic finding fingerprints.
Existing v1 endpoints remain supported:

```bash
curl -X POST http://127.0.0.1:8765/v2/audit \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com","preset":"all","max_pages":25}'
curl -X POST http://127.0.0.1:8765/v2/jobs \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com"}'
curl http://127.0.0.1:8765/v2/jobs/<job_id>
curl -X POST http://127.0.0.1:8765/v2/jobs/<job_id>/cancel
```

Use `/v2/rescan`, `/v2/diff`, and `/v2/export` for explicit rescan,
comparable-baseline, and bounded JSONL/CSV inventory operations. Request
limits are enforced server-side; incompatible baselines are rejected rather
than silently compared. The canonical CLI equivalent is
`agentready audit https://example.com --fail-on-checks`.

`POST /v2/jobs` returns a job identifier for bounded asynchronous execution.
Poll `GET /v2/jobs/{job_id}` for a typed snapshot and use
`POST /v2/jobs/{job_id}/cancel` to request cancellation. Job state is
explicit; a cancelled or failed operation is never returned as a successful
audit report.

The v2 crawler is deterministic within its configured limits: same-origin
scope, normalized URL identity, bounded frontier, explicit item states, and
coverage accounting. Protocol profiles audit passive documents and expose
evidence through the same report and agent/MCP projection boundaries.

Release `0.8.1` freezes the compatibility manifest: v1 CLI/API facades stay
supported, while v2 schemas and protocol manifests are additive. Migration
status is intentionally `v1-preserved-v2-additive`; no v1 endpoint is removed
by this release candidate.

Get localized HTML dashboard:

```bash
curl -X POST http://127.0.0.1:8765/scan/dashboard \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com","language":"ru"}' \
  -o dashboard.html
```

The dashboard's `all` profile calls both `/scan/dashboard` (including GEO
checks) and `/seo/audit/dashboard`, then presents their results as one
downloadable HTML report with GEO and SEO sections. The independent endpoints
remain unchanged for API consumers that need one report source.

Independent SEO endpoints (optional `crawl`, `max_pages`, `render` fields enable cross-page checks and headless-browser link extraction):

```bash
curl -X POST http://127.0.0.1:8765/seo/audit \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com","language":"en","crawl":true,"max_pages":25}'
curl -X POST http://127.0.0.1:8765/seo/audit/dashboard \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com"}' -o seo.html
```

The MCP facade additionally exposes `seo_audit`. API and MCP SEO requests reject private targets and do not perform mutations. Optional `ga_property` / `gsc_site` fields enable GA4/Search Console analytics checks using the stored service account (see Getting Started).

Credential management is CLI-only (`agentready seo credentials set|status|clear`) and is intentionally not exposed as an API/MCP endpoint.

Mobile endpoints:

```bash
curl -X POST http://127.0.0.1:8765/mobile/audit \
  -H 'content-type: application/json' \
  -d '{"urls":["https://example.com"],"language":"en"}'
curl -X POST http://127.0.0.1:8765/mobile/audit/dashboard \
  -H 'content-type: application/json' \
  -d '{"urls":["https://example.com"],"render":true}' -o mobile.html
```

The MCP facade additionally exposes `mobile_audit`, `mobile_findings`, and `mobile_remediation_plan` for coding-agent workflows.

The HTTP `serve` surface is intentionally read-only: filesystem-only commands
(`init`, `geo init-rules`, and `logs`) and credentialed/mutating publisher commands
are not exposed as unauthenticated API endpoints.

The dashboard and AI assistant preserve the v1 localized HTML experience while
using the v2 evidence/coverage projection for AI context. AI output is
advisory, bounded, and must not receive credential material; provider keys stay
in the OS credential vault and saved chats remain local runtime data.

The serve process creates its data directory automatically. It defaults to a
`.cache` directory beside the running server (portable EXE) or project source
tree (Python execution); use `--data-dir` to select another directory. AI chat
skill and MCP selections are stored in `<data-dir>/ai-tools.json`.

### AI assistant endpoints

Enable both `ai.enabled` and `ai.transport_enabled` in `.agentready.yml` to
expose the loopback-only assistant routes:

The main `/dashboard` includes **AI authorization**. It opens a local dialog
where the API key is entered into a password field and saved directly to the OS
credential vault; the key is not returned to the browser or written to YAML.
The dialog also supports removing the saved key. Provider URL and model remain
trusted local `.agentready.yml` settings.

```bash
curl http://127.0.0.1:8765/ai/status
curl -X POST http://127.0.0.1:8765/ai/recommend \
  -H 'content-type: application/json' \
  -d '{"target":"https://example.com","mode":"seo","language":"ru"}'
curl -X POST http://127.0.0.1:8765/ai/chat \
  -H 'content-type: application/json' \
  -d '{"target":"https://example.com","mode":"both","message":"Prioritize high-impact fixes"}'
```

The same credential operations are available as loopback-only endpoints:

```bash
curl -X POST http://127.0.0.1:8765/ai/credentials \
  -H 'content-type: application/json' \
  -d '{"api_key":"YOUR_API_KEY"}'
curl -X DELETE http://127.0.0.1:8765/ai/credentials
```

CLI, `serve`, and MCP all resolve the same active profile from
`ai.active_provider`. Each profile contains a name, OpenAI-compatible
`base_url`, selected `model`, and a credential ID; its API key is stored in the
`agentready-tools` OS keyring service. The serve dashboard can switch between
profiles without exposing keys to the browser. There is no separate provider
selection or API key per transport.

The same dashboard dialog has an explicit “Enable AI assistant and local
transport” switch. Saving with the switch enabled persists both
`ai.enabled` and `ai.transport_enabled`, so the selected profile is usable by
CLI, serve, and MCP without editing YAML manually.

The configured provider `model` takes precedence over the shared `ai.model`
fallback. CLI supports a per-call override with `--model`; serve accepts
`model` in the loopback AI request; MCP exposes an optional `model` argument on
`ai_recommend` and `ai_chat`.

The serve dashboard loads an OpenAI-compatible provider's `/models` catalog
from `GET /ai/providers/{provider_id}/models` after provider selection. Models
are shown in both provider settings and the chat selector with capability
markers such as chat, embedding, rerank, moderation, and audio. When a
provider exposes only model IDs, these markers use conservative name
heuristics; explicit provider capability metadata takes precedence.

Provider settings include a persisted **chat-capable models only** filter.
When enabled, embedding, reranking, moderation, and audio-only models remain
available in the provider catalog response but are hidden from the provider
and chat selectors.

Requests accept bounded report context and caller-owned `user`/`assistant`
history. The dashboard chat keeps the selected audit as context, supports up
to five bounded text, JPEG/PNG, Word, Excel, and PDF attachments. Files can be
selected or pasted from the clipboard; text is included directly and binary
files are represented by bounded data URLs for providers that support them.
The chat can also apply built-in skills
(`audit-analyst`, `evidence-explainer`, and `implementation-planner`). The
AgentReady MCP context options invoke the local `seo_findings` and
`remediation_plan` projections before the selected model is called. Selected
skills and MCP tools are persisted through `GET/POST /ai/tools` in the serve
data directory. The response is advisory, evidence-grounded, localized, and
does not modify the target.

The dashboard also provides a prompt library and chat archive. The first
request to `GET /ai/prompts` creates `<data-dir>/prompts.json` with common
SEO/GEO prompts; custom prompts are saved with `POST /ai/prompts`. Completed
conversations can be saved with `POST /ai/chats` and are written as JSON files
under `<data-dir>/chats/`; `GET /ai/chats` lists the saved conversations.
Built-in prompts are returned in the selected dashboard language. The active
conversation and token totals are additionally persisted in browser
`localStorage`, so a reload or dashboard language switch does not clear the
chat. The chat editor is positioned below the transcript, supports vertical
resizing, can retry the latest user request with the currently selected model,
exports an OpenAI/DeepSeek-compatible JSON document with a `messages` array,
and can start a new dialog after automatically saving the current one to the
serve chat history.

## MCP Server

Run MCP:

```bash
agentready mcp --host 127.0.0.1 --port 8766
# or, from a source installation:
python -m agentready.mcp_server
```

The portable `agentready.exe` also bundles the MCP facade, so `agentready mcp`
works in the standalone Win64 build.

When AI is explicitly enabled, MCP also exposes `ai_recommend` and `ai_chat`.
They accept only target/report context, mode, language, and bounded history;
provider and credential overrides are not part of the tool schema. MCP remains
loopback-only.

Endpoint:

```text
http://127.0.0.1:8766/mcp
```

`scan_site` accepts optional `include` checks and `language: "en" | "ru"`.

### Tools for coding agents

Two tools are designed for autonomous coding agents that need to fix a site:

- `audit_findings(url, mode, preset, language, recommendation_limit)` — runs the audit and returns **only the optimization gaps** (failed/warned checks). Each finding contains a localized `title`, `category`, `why` (why it matters), observed `evidence`, and a `remediation` block with fix `instructions`, a ready-to-use `agent_prompt`, a `rerun_command` and reference links. Response schema: `agentready.findings.v1`.
- `remediation_plan(url, mode, preset, language, recommendation_limit)` — returns a **prioritized step-by-step fix plan** ordered by impact/effort. Each step carries instructions, an agent prompt and a verification command. Response schema: `agentready.remediation-plan.v1`.

Both tools support `mode: "readiness"` (default, full protocol audit) and `mode: "seo"` (single-page SEO audit), and `language: "en" | "ru"` for all human-facing text.

Example coding-agent flow:

```text
1. Call remediation_plan("https://example.com", mode="readiness", language="ru")
2. Apply each step in order using its agent_prompt as the task description
3. Re-run the step's verify command to confirm the fix
4. Repeat until steps_count is 0
```

## Typical Automation Flow

1. Trigger scan through API/MCP
2. Persist JSON output
3. Apply CI gate thresholds
4. Generate remediation tickets/prompts

## See Also

- [Safety](safety.md) — production-safe network usage
- [Reporting](reporting.md) — output formats and baseline comparison
- [Configuration & CI](configuration-and-ci.md) — gate management
