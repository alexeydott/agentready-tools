# Research notes — AgentReady Tools 0.2.0

Date: 2026-08-07

## 0.8.2 implementation review (2026-08-11)

The dashboard integration review and headed browser acceptance confirmed the
following implementation decisions:

- Dashboard browser tests use `/dashboard` explicitly, while legacy `/` and
  v1 scan endpoints remain compatibility surfaces.
- Browser-local state restores bounded dashboard fields and AI chat history.
  Credential restoration is intentionally redacted: raw API keys are not
  placed in `localStorage` or password inputs.
- Prompt editing carries a stable server-side ID and updates only the selected
  language map, preserving the other localized variant.
- Optional AI chat/provider absence is reported as an explicit acceptance skip,
  not a false product failure.
- Inline combined-report controllers must split the closing `</script>` token
  when embedded in a script string, otherwise the browser terminates the outer
  script early.

Validation evidence for this pass: 352 tests passed, compile and diff checks
passed, headed Playwright/DevTools runs covered `gossnab.ru` and `mappl.ru`,
and the Win64 portable executable was rebuilt after source and version changes.

## Sources reviewed

### Cloudflare

Primary source:
https://blog.cloudflare.com/agent-readiness/

Verified points used in the implementation:

1. The scanner actively makes requests to a site and evaluates four scored dimensions: Discoverability, Content, Bot Access Control, and Capabilities/Protocol Discovery.
2. Commerce checks are evaluated separately and were explicitly described as not counting toward the launch score.
3. `llms.txt` is discussed as a useful content surface but is not enabled by default in the public scan; Cloudflare says a customized scan may include it.
4. Markdown content negotiation uses `Accept: text/markdown`.
5. Cloudflare's own documentation additionally exposes `/index.md` fallbacks because not all agents send the Markdown Accept header.
6. For very large documentation sites, Cloudflare uses hierarchical per-directory `llms.txt` files rather than one very large flat file.
7. Cloudflare emphasizes context efficiency and reports that agent-friendly documentation reduced retrieval cost/latency in its own benchmark. AgentReady does **not** copy those benchmark numbers into a pass/fail threshold.
8. Cloudflare provides a coding-agent prompt for failed checks.
9. Web Bot Auth is described as conditional: content-only sites that do not operate outbound agents do not necessarily need it.
10. The scanner itself exposes MCP/Agent Skills surfaces as an example of agent-native discoverability.

### Kodus

Repository:
https://github.com/kodustech/agent-readiness

The repository is MIT-licensed and targets **source-code repositories**, not public websites. Its domain-specific checks were therefore not copied into AgentReady.

Transferable engineering ideas reviewed:

- fine-grained YAML configuration;
- criteria/pillar enable/disable behavior;
- skipped criteria excluded from score calculations;
- sequential maturity tiers with an 80% pass threshold;
- CI minimum-level gating;
- recommendations ranked by impact and effort;
- machine-readable JSON output;
- dashboard-style summary visualization;
- optional deeper analysis rather than turning every heuristic into a hard failure.

Relevant source files:

- `src/engine/config.ts`
- `src/engine/scorer.ts`
- `src/engine/recommender.ts`
- project `README.md`

## Changes selected for AgentReady

### 1. Supplemental `llms.txt` audit

Rationale: directly supported by the Cloudflare article, but intentionally not part of the core score.

Validation:

- HTTP 200;
- text MIME type;
- non-HTML body;
- H1 heading;
- at least one Markdown link;
- body-size/link-count metrics;
- large flat index warning;
- detection of hierarchical `llms.txt` links.

The size and link-count values are **AgentReady heuristics**, not Cloudflare thresholds.

### 2. `/index.md` fallback

Rationale: Cloudflare documents this as a practical compatibility path for agents that do not send `Accept: text/markdown`.

It is supplemental and non-scoring because it is an implementation pattern, not a universal protocol requirement.

### 3. Markdown efficiency

Rationale: Cloudflare emphasizes the token/context benefits of Markdown.

AgentReady compares raw response byte sizes and explicitly labels the result a **proxy**, because byte count is not token count and depends on the model/tokenizer.

### 4. Web Bot Auth applicability correction

Previous behavior treated Web Bot Auth as a scored default criterion. The Cloudflare article explicitly states it is not needed for a simple site that does not make outbound agent requests.

0.2.0 therefore keeps the probe but marks it informational until applicability can be established reliably.

### 5. YAML configuration

New files:

- `.agentready.yml`
- `.agentready.yaml`

Supported areas:

- preset;
- include/exclude checks;
- network limits;
- content/commerce targets;
- digest verification;
- scoring threshold;
- CI gates;
- recommendation count.

This adapts the configuration concept from Kodus without copying its codebase-specific schema.

### 6. CI gates

New CLI:

- `--min-score`
- `--min-level`
- `--fail-on-checks`
- `--ci`

CLI thresholds work directly. `--ci` additionally activates gate values from `.agentready.yml`.

### 7. Tiered maturity progress

The old hard-coded milestone gates were replaced with `transparent-tiered-v2`.

Properties:

- sequential tiers;
- default 80% threshold;
- threshold configurable;
- only selected, scored, applicable results participate;
- next-level progress contains current/needed/remaining.

The **80% mechanism** is inspired by Kodus. The website criteria assigned to tiers are AgentReady-specific. The result is not represented as Cloudflare's proprietary/unpublished formula.

### 8. Prioritized recommendations

Every actionable failure/warning receives:

- impact;
- effort;
- priority;
- action;
- reason.

Sorting favors higher impact and lower effort, following the useful UX pattern in Kodus.

### 9. Coding-agent prompt

Each remediation now contains an `agent_prompt` suitable for handing to a coding agent. It tells the agent to preserve existing human-facing behavior/security controls and gives the exact re-run command.

This directly reflects Cloudflare's stated remediation workflow.

### 10. HTML report improvement

The HTML output now includes:

- category score bars;
- check type (`core`, `experimental`, `supplemental`);
- prioritized recommendations;
- remediation prompts.

This is a lightweight static equivalent of the dashboard-style presentation used by readiness tools; it adds no runtime JavaScript dependency.

## Explicitly not integrated

### Kodus codebase checks

Linting, tests, containers, CODEOWNERS, dependency freshness, repository security, etc. are useful for **coding-agent autonomy**, but they answer a different question from `isitagentready.com`: whether the deployed **website** exposes agent-readable protocols.

They were intentionally left out to avoid conflating two readiness domains.

A future separate command could implement `agentready repo /path/to/repository`, but it should remain a distinct report/profile.

### Mandatory LLM-based scoring

Kodus has optional AI-powered analysis of qualitative repository criteria. AgentReady 0.2.0 does not make an external LLM call part of website scoring because this would:

- reduce reproducibility;
- require credentials/vendor configuration;
- make CI results model-dependent;
- turn protocol conformance into subjective evaluation.

Qualitative content analysis could be added later as a supplemental provider interface, never as an opaque core score.

### Hidden LLM directives

Cloudflare documents hidden instructions that tell agents to use Markdown resources. AgentReady does not score or recommend hidden prompt-like directives because they are not a web interoperability standard and may interact poorly with prompt-injection/security policies.

## Verification performed

- unit tests: 11 passed;
- full local end-to-end fixture: 23 checks executed (20 core + 3 supplemental);
- fixture result: core score 100/100, Level 5;
- supplemental results: `llms-txt`, `markdown-index-fallback`, `markdown-efficiency` all pass;
- Agent Skills digest verification exercised against actual bytes;
- x402 + MPP challenge detection exercised on the same read-only HTTP 402 fixture;
- private-target protection remains enabled by default in FastAPI/MCP surfaces.

## 0.4.0 — Integration of the Tochki AI-search/GEO guide

Source reviewed: https://tochkicamp.ru/guides/kak-optimizirovat-sayt-pod-ai-poisk/

The useful recommendations were separated into three classes.

### Remote, reproducible checks

- page indexability and canonical consistency;
- declared `robots.txt` policy plus diagnostic live HTTP probes for search/user crawler identities;
- parseable, connected Article/TechArticle JSON-LD;
- Person author linkage and optional `sameAs`;
- BreadcrumbList presence;
- conditional FAQPage validation;
- publication/modification date syntax, ordering and visible exposure.

### Explicit heuristics

Citation readiness is measured as evidence, not as a ranking prediction: concrete numeric facts, complete code blocks, tables/lists, sufficiently substantive and self-contained paragraphs, answer-first structure, and heading structure. It is marked experimental and excluded from the separate GEO score. Human review remains necessary for intent coverage and editorial quality.

### Publication/operations utilities

- IndexNow key generation and public verification;
- validated batch payloads (single host, de-duplication, protocol maximum);
- Git diff → URL preview using canonical/front-matter first and deterministic path fallback;
- explicit `--send` for network submission;
- Git-history date audit;
- access-log summaries for known AI/search bot tokens;
- a project rules template enforcing plan-before-mass-edit, post-change validation and non-goals such as keyword stuffing/thin-page generation.

The implementation deliberately does not treat `llms.txt` or Schema.org markup as proven ranking multipliers. It also does not treat spoofed crawler User-Agent success/failure as proof of provider crawler reachability, because providers can verify source networks and WAFs can apply IP-based controls.
### 0.4.0 verification

- unit/regression tests: 21 passed;
- Python bytecode compilation: passed;
- local HTTP end-to-end `ai-search` fixture: core score 100/100; separate GEO score 100/100 across 8 applicable GEO-scored checks;
- the same fixture passed robots/sitemap, Markdown negotiation, AI bot policy, Content Signals, live crawler diagnostics, canonical/indexability, connected JSON-LD, FAQ, dates, and citation heuristic;
- generated Russian JSON and bilingual HTML GEO reports were inspected by assertions;
- IndexNow/Git utilities are covered by isolated tests and do not contact IndexNow unless explicit submission is requested.
