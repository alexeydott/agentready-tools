[← Previous Page](configuration-and-ci.md) · [Back to README](../README.md) · [Next Page →](integrations.md)

# Reporting

## Output Formats

Generate JSON:

```bash
agentready scan https://example.com --format json -o report.json
```

Generate Markdown:

```bash
agentready scan https://example.com --format markdown -o report.md
```

Generate HTML dashboard:

```bash
agentready scan https://example.com --format html -o report.html
```

## Localized Reports

```bash
agentready scan https://example.com --format markdown --lang ru -o report-ru.md
agentready scan https://example.com --format json --lang ru -o report-ru.json
agentready scan https://example.com --format html --lang ru -o dashboard.html
```

The HTML dashboard embeds English and Russian views with an in-browser language switcher.

SEO output uses the independent `agentready.seo.v1` schema:

```bash
agentready seo audit https://example.com --format json -o seo.json
agentready seo audit https://example.com --baseline seo.json --min-score 80
# Cross-page checks via a bounded same-origin crawl
agentready seo audit https://example.com --crawl --max-pages 25 --format html -o seo.html
```

The SEO audit runs 23 single-page checks (metadata, indexability, canonical, images, HTTPS/mixed content, URL format, content quality, performance, hreflang, structured data); `--crawl` adds 5 cross-page checks (broken links, redirect chains, duplicate metadata, internal nofollow, link counts). `--render` extracts links from JS-driven pages through headless Chromium.

## Structured evidence

Evidence is preserved across JSON, HTML, Markdown, console, MCP, and AI report surfaces when a check produces it. In addition to the check finding, consumers may receive:

- `url`: the fetched or affected source URL;
- `page`: the containing page URL;
- `resource`: the affected resource URL;
- `metrics`: bounded check-specific values such as image attributes or title length.

When presenting findings, keep page and resource locations distinct and do not infer a location that is absent from the evidence.

SEO baselines reject Agent Readiness JSON and only compare SEO score/check regressions.

Mobile-friendliness output uses the independent `agentready.mobile.v1` schema with per-page and aggregate scores:

```bash
agentready mobile audit https://example.com --format json -o mobile.json
agentready mobile audit https://example.com https://example.com/about --render --format html -o mobile.html
```

## Baselines and Regressions

Create baseline:

```bash
agentready scan https://example.com --format json -o baseline.json
```

Compare against baseline:

```bash
agentready scan https://example.com --baseline baseline.json
```

Regression types include:

- scored check `pass -> fail`
- newly introduced scored failure
- maturity-level decrease

## Remediation Prompts

Reports include ready-to-paste coding-agent prompts for failed/warning checks to speed implementation follow-ups.

## See Also

- [Configuration & CI](configuration-and-ci.md) — threshold and gate policies
- [Checks & Methodology](checks-and-methodology.md) — check taxonomy and score model
- [Integrations](integrations.md) — API/MCP report automation
