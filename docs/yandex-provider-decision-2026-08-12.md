# Yandex provider decision — 2026-08-12

## Decision

Defer a first-party Yandex Webmaster/Metrica adapter for WP9. AgentReady keeps
the existing IndexNow publisher, but does not add a third-party index-check
broker or infer ranking/indexing state from public search results.

The v2 provider workflow accepts only bounded, explicitly supplied cached
observations. Live credentials remain in the local OS-vault/CLI context and
are never accepted by the default HTTP or MCP audit surfaces.

## Evidence from official documentation

- **Webmaster API:** version 4.1 is a REST API at `api.webmaster.yandex.net`.
  Requests require an OAuth token and a user ID; applications require a
  registered client ID and acceptance of the API terms. The documented
  resources include host information, summaries, important URLs, verification,
  and re-crawl quota.
- **Webmaster permissions:** the current OAuth guide documents
  `webmaster:hostinfo` and `webmaster:verify` for the supported host workflows.
- **Webmaster quotas:** HTTP 429 responses include `QUOTA_EXCEEDED` and a
  daily quota/recovery timestamp. The API documentation does not provide a
  stable public quota suitable for silently scheduling per-page checks.
- **Metrica API:** OAuth access requires `metrika:read` for statistics. The
  Reports API uses `/stat/v1/data`, supports bounded dimensions/metrics and
  returns sampled/statistical data rather than an indexing verdict.
- **Metrica limits:** current documentation lists 30 requests/sec per IP,
  three parallel requests per user, 5,000 requests/day per user, and 200
  Reports API requests per five minutes. Reports may be incomplete for the
  current day and can contain limited-disclosure data.

## Reconsideration criteria

Implement a Yandex adapter only after a user supplies a supported OAuth client,
explicit scopes, a host/counter identifier, and a product requirement for a
specific documented endpoint. It must use the existing `ExternalMetricProvider`
contract, cache by request and freshness window, expose quota/unavailable
states, and remain an enrichment that cannot change the core audit score.

Official references:

- https://yandex.com/dev/webmaster/doc/en/
- https://yandex.com/dev/webmaster/doc/en/tasks/how-to-get-oauth
- https://yandex.com/dev/webmaster/doc/en/reference/errors
- https://yandex.com/dev/metrika/en/intro/authorization
- https://yandex.com/dev/metrika/en/intro/quotas
- https://yandex.com/dev/metrika/en/stat/openapi/data
