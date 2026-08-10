[← Previous Page](checks-and-methodology.md) · [Back to README](../README.md) · [Next Page →](configuration-and-ci.md)

# GEO & Indexing Notifications

## AI Search / GEO Profile

Run dedicated GEO checks:

```bash
agentready scan https://example.com/article/ --preset ai-search --lang ru
```

Or blend GEO checks into another preset:

```bash
agentready scan https://example.com/article/ --preset all --with-ai-search --lang ru
```

Reports can expose:

- `score` — protocol/core readiness
- `ai_search_score` — separate GEO score (`geo_scored` checks only)

`citation-readiness` is experimental and intentionally excluded from numeric `ai_search_score`.

## Crawler Roles and Google-Extended

Do not treat every robots.txt token as a live crawler User-Agent:

- Search/indexing crawlers (`OAI-SearchBot`, `Claude-SearchBot`, `PerplexityBot`, and `Googlebot`) affect discovery and should normally reach public content.
- User-directed fetchers (`ChatGPT-User`, `Claude-User`, and `Perplexity-User`) retrieve pages in response to user actions; robots behavior differs by provider.
- Training crawlers (`GPTBot` and `ClaudeBot`) represent a publisher policy choice and do not reduce the GEO score when blocked.
- `Google-Extended` is a standalone robots.txt product token. Google states that it has no separate HTTP request User-Agent, does not affect Google Search inclusion, and is not a Google Search ranking signal. AgentReady inspects its robots policy but does not issue a fabricated live request or search for it in access logs.

## IndexNow Workflow

Generate key:

```bash
agentready indexnow key --dir public
```

Verify deployment:

```bash
agentready indexnow verify https://example.com YOUR_KEY
```

Preview Git-derived changed URLs:

```bash
agentready indexnow git \
  --repo . \
  --base-url https://example.com \
  --content-root site \
  --from-ref HEAD~1 \
  --to-ref HEAD
```

Submit explicitly after verification:

```bash
agentready indexnow git \
  --repo . \
  --base-url https://example.com \
  --content-root site \
  --key YOUR_KEY \
  --send
```

### Global and Yandex endpoints

The default endpoint is the global IndexNow endpoint, which distributes notifications to participating engines. Select Yandex explicitly when provider-specific delivery is required:

```bash
# Validate the payload without sending
agentready indexnow submit https://example.com/new-page \
  --key YOUR_KEY \
  --provider yandex \
  --dry-run

# Send to Yandex
agentready indexnow submit https://example.com/new-page \
  --key YOUR_KEY \
  --provider yandex
```

Use either `--provider` or an explicit `--endpoint`; `--provider yandex` and `--endpoint` together are rejected as ambiguous.

IndexNow rules enforced by AgentReady:

- one host per request
- at most 10,000 URLs per POST
- key format of 8–128 ASCII letters, digits, or hyphens
- a custom non-root `keyLocation` authorizes only URLs beneath that directory
- HTTP `200` and `202` mean accepted/received, not indexed

## Google Indexing API

Google's Indexing API is **not** a general URL-submission API. Officially supported pages are:

- `JobPosting`
- `BroadcastEvent` embedded in `VideoObject`

Install optional authentication support:

```bash
pip install -e ".[google]"
```

Create a Google Cloud service account without assigning a project IAM role, enable the Web Search Indexing API, and add the service-account email as a delegated owner of the matching Google Search Console property. Do not grant the Google Cloud project `Owner` role.

Keep the downloaded JSON private and select it at runtime:

```bash
# PowerShell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\secure\service-account.json"

# Linux/macOS
export GOOGLE_APPLICATION_CREDENTIALS=/secure/service-account.json
```

Preview an update. This performs a read-only live-page preflight and refuses pages without supported JSON-LD:

```bash
agentready google-indexing publish https://example.com/jobs/42
```

Publish only after reviewing the preview:

```bash
agentready google-indexing publish https://example.com/jobs/42 --send
```

For a deleted URL, the page may no longer be fetchable. Declare the formerly supported type explicitly:

```bash
agentready google-indexing publish https://example.com/jobs/42 \
  --type deleted \
  --eligible-type job-posting \
  --send
```

Other inputs and status lookup:

```bash
agentready google-indexing publish --from-file changed-urls.txt
agentready google-indexing publish \
  --git-repo . --base-url https://example.com --content-root site
agentready google-indexing status https://example.com/jobs/42
```

The default run guard is 200 publish notifications, matching Google's documented default daily project quota. `--max-notifications` makes a different known project limit explicit. Metadata reports the latest notification known to the API; it does not report indexing state.

### Corrections to the referenced Habr article

| Article guidance | Safe implementation |
|------------------|---------------------|
| Submit arbitrary pages to Google | Submit only supported `JobPosting` or `BroadcastEvent` pages |
| Grant the service account the Google Cloud `Owner` role | Assign no project IAM role; add delegated Search Console ownership |
| Use `oauth2client` | Use the maintained `google-auth` library |
| Expect `{"success": true}` from IndexNow | Use official HTTP `200`/`202` receipt semantics |
| Send a separate `charset` header | Use `Content-Type: application/json; charset=utf-8` |

Official references:

- [Google Indexing API prerequisites](https://developers.google.com/search/apis/indexing-api/v3/prereqs)
- [Google Indexing API usage](https://developers.google.com/search/apis/indexing-api/v3/using-api)
- [Google Indexing API quotas](https://developers.google.com/search/apis/indexing-api/v3/quota)
- [IndexNow protocol documentation](https://www.indexnow.org/documentation)

## GEO Utilities

```bash
agentready geo git-dates site/guides/page.md --repo .
agentready logs ai-bots /var/log/nginx/access.log
agentready geo init-rules AI_SEARCH_RULES.md --lang ru
```

## Measuring Outcomes

Combine the audit with:

- real AI-bot access and WAF logs
- Google Search Console and Yandex Webmaster indexing, crawl, and impression signals
- periodic manual checks of whether relevant AI-search answers cite the site as a source
- change annotations so observations can be compared before and after meaningful content or protocol updates

These signals are observational. They do not prove that one change caused a ranking or citation change, and no GEO audit can promise immediate inclusion.

## Limits You Should Keep Explicit

- User-Agent spoofing is diagnostic, not crawler-IP verification.
- Git history comparisons are heuristic evidence, not editorial truth.
- IndexNow acceptance (`200`/`202`) does not guarantee indexing/ranking.
- Google Indexing API HTTP `200` confirms a notification, not crawl or indexing.
- Google notification metadata is submission history, not index status.
- Citation heuristics are not ranking-factor guarantees.

## See Also

- [Checks & Methodology](checks-and-methodology.md) — scoring scope and categories
- [Configuration & CI](configuration-and-ci.md) — credentials and logging environment variables
- [Safety](safety.md) — network, credentials, and commerce boundaries
