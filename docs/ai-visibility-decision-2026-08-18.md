# AI Visibility Monitor decision — 2026-08-18

## Decision

**Deferred.** Task 32 does not add an AI-visibility adapter, endpoint, schema,
dependency, provider credential, or readiness-score input.

## Gate review

| Gate | Finding | Decision impact |
| --- | --- | --- |
| Approved engines/providers | No engine-neutral provider list or customer demand evidence is approved for this release. | Fail — no implementation scope. |
| Terms-compliant access | Direct SERP scraping is not an acceptable access method. Google Custom Search JSON API is restricted to existing customers and is scheduled for discontinuation on 2027-01-01; Bing Web Search requires a separately approved subscription and contract. | Fail — no stable common transport. |
| OpenAI Web Search | Official hosted web search is provider-specific, paid per tool call, and model/provider dependent; it cannot establish cross-engine visibility or a reproducible neutral baseline. | Not a substitute for the monitor. |
| Query cap and locale | No approved query budget, locale matrix, or per-run cap has been supplied. | Fail — bounded execution cannot be specified. |
| Retention and reproducibility | No approved snapshot retention, provenance format, replay fixture, or redaction policy exists for external AI answers. | Fail — evidence would not be replayable. |
| Cost and demand | No authorized spend or expected demand is recorded. | Fail — no justification for an external provider. |

The facts above are based on the official provider documentation reviewed for
this gate: [Google Custom Search JSON API](https://developers.google.com/custom-search/v1/overview),
[Bing Web Search overview](https://github.com/MicrosoftDocs/bing-docs/blob/main/bing-docs/bing-web-search/overview.md),
and [OpenAI Web Search](https://developers.openai.com/api/docs/guides/tools-web-search/).

## Re-open criteria

Reconsider only after a written approval names the engines/providers and
official access method, sets a per-run query cap and locale list, defines
snapshot provenance and retention, specifies a no-secret logging/redaction
contract, records a cost ceiling and expected demand, and supplies official or
synthetic fixtures plus an explicitly opt-in live L4 smoke test. Any future
implementation must remain external enrichment, must not alter readiness
scoring, and must reuse the existing provider budget/provenance boundaries.
