[← Dashboard FAQ (RU)](dashbord_faq_ru.md) · [Back to README](../README.md)

# Dashboard: beginner's guide

The dashboard lets you audit a website without using the command line. Enter
a public website address, choose an audit profile, and click **Execute**.
When the audit is finished, you can read, download, or print the report and
ask the AI assistant questions about it.

## Opening the dashboard

Start the local AgentReady Tools server and open the dashboard address shown in
the console. When no language is included in the URL, the dashboard uses the
browser locale: Russian for `ru`, and English for every other locale.

The **Help** button is in the top-right area beside the language selector.
Click it to open the embedded help panel for the full page height. Click
**Hide help** to collapse it again. On desktop, drag the panel's left edge to
resize it.

The **Language** selector in the top-right corner changes the interface
language. The selection is saved in your browser. An explicit
`?language=en` or `?language=ru` URL parameter takes priority over the browser
locale and saved state.

## Main fields

| Element | What to do |
|---|---|
| **Website URL** | Enter a public address such as `https://example.com`. |
| **Audit preset** | Choose all checks, content, API, AI Search/GEO, SEO, or mobile-friendliness. |
| **Execute** | Starts the audit with the selected settings. |
| `?` icon | Hover over it or reach it with Tab to read a short explanation. |

Only audit websites you are allowed to inspect. Private and loopback addresses
are blocked for safety.

## Advanced parameters

Open **Advanced parameters** when you need more control:

- **Content URL** — a specific page for content-oriented checks.
- **Commerce URL** — an endpoint where commerce discovery signals should be
  checked.
- **Timeout** — maximum time to wait for one network request.
- **Workers** — number of checks that can run in parallel.
- **Level threshold** — minimum requirement ratio for advancing to the next
  maturity level.
- **Recommendation limit** — maximum recommendations shown in the report.
- **Verify Agent Skills digests** — validates skill content instead of checking
  only its links.

## Custom rules debugger

Open **Custom rules** to validate a YAML rules document before using it in an
audit workflow. Use `version: 1`, a stable `id` for every rule, a title, and an
assertion. **Validate rules** checks the document structure and reports the
location of invalid fields. **Preview matches** evaluates the rules against
the available saved audit representation; it does not start a crawl or send a
new request to the audited website.

## Projects and run history

In **Projects and run history**, enter a stable project ID and display name,
then click **Create or update project**. **Load run history** lists the
project's recent audit runs. The table uses these columns:

- **Audit run** — the identifier of the saved run.
- **Started by** — what initiated the run, such as the dashboard or an API
  request.
- **Baseline** — whether the run is marked as the comparison baseline
  (`Yes`/`No`).

An empty history is a valid result: it means that no run has been saved for the
selected project yet.

## Virtual Robots simulation

Open **Virtual Robots simulation** to compare the stored and proposed robots
policies for selected user agents. Paste both documents and click
**Simulate policy**. This is an offline comparison: it does not fetch or publish
`robots.txt`.

## Sitemap reconciliation

Paste bounded sitemap XML and choose the origin associated with the stored run,
then click **Reconcile sitemap**. The result compares sitemap entries with the saved
inventory. This control does not fetch or submit a sitemap.

## Link Graph

Click **Load graph** to display a bounded projection of stored link
occurrences. **Dead ends** and **Disconnected** filter only the displayed
projection; they do not start a crawl.

## Links below the settings

- **Refresh check catalog** reloads the checks available for the selected
  profile.
- **Check service health** sends a small request to confirm that the local
  service is responding.
- **AI** opens AI-provider settings.
- **Debug results** displays the raw JSON response from the server. Use it when
  you need technical details for troubleshooting.

## Selecting individual checks

Open **Checks included in this run**. **Select all** enables every check in
the selected profile, while **Clear checks** removes them. You can then select
only the checks you need. A short explanation is shown beside each check.

## Reading the audit result

After you start an audit, the dashboard shows progress for starting, fetching
data, and rendering the report. A completed report can include:

- overall score and maturity level;
- passed, failed, and skipped checks;
- prioritized recommendations;
- confirmed URLs, pages, resources, and metrics when the audit provides them.

Use **Download report** or **Print report** beside the HTML report. A
downloaded HTML file can be opened later without the server.

## Using the AI assistant

The AI panel appears after a compatible audit has finished. It uses the current
report as context and does not change the audited website.

1. Choose **SEO**, **GEO**, or **SEO/GEO** mode.
2. Select a provider and model.
3. Write a question in **Request**, or choose a ready-made request from the
   prompt library.
4. Optionally select **Skills** and **MCP context**. Skills guide the analysis;
   MCP adds confirmed AgentReady findings.
5. Click **Ask AI assistant** for one answer, or **Chat with AI assistant** to
   continue a conversation.

**Conversation** keeps previous questions available for follow-up. **Retry
latest request** sends the last request again. **Start new chat** clears the
current conversation.

## Files, prompts, and saved chats

- **Attach files** adds images or documents to the request.
- **Prompt library** contains reusable SEO/GEO questions.
- **Prompt title** names a custom prompt.
- **Save prompt** adds the current prompt to the library.
- **Save chat to file** stores the conversation history.
- **Export OpenAI/DeepSeek JSON** creates a portable JSON conversation.
- **Saved chats** opens a previously saved conversation.

Do not paste an API key into the request text. Provider keys are stored in the
system credential store rather than in ordinary dashboard text.

## If something does not work

1. Check the website URL and your internet connection.
2. Click **Check service health**.
3. Confirm that the AI provider is enabled and that the selected model exists.
4. Turn on **Debug results** and save the error message.
5. If the AI times out, check the provider URL, model, and network access.

## See Also

- [Getting Started](getting-started.md) — installation and first run
- [Reporting](reporting.md) — report formats and evidence
- [Configuration & CI](configuration-and-ci.md) — project settings
# SEO marketer workspace

The v2 inventory panel reuses the same bounded query contract as the API. Use
Pages, Links, Resources, Redirects, Findings, or Metrics, then filter, sort,
paginate, save, reopen, export, compare, rescan selected URLs, or cancel a
long-running job. Partial crawls are explicitly uncertain outside observed
coverage. Internal authority is a deterministic prioritization signal, not
search-engine PageRank.
