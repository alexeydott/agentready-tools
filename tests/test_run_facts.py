import httpx
from types import SimpleNamespace

from agentready.audit_core import (
    MemorySiteStore,
    RunRecord,
    persist_robots_run_facts,
    persist_sitemap_run_facts,
    robots_policy_from_run_facts,
    sitemap_reconciliation_from_run_facts,
)
from agentready.audit_service import AuditRequest, AuditService


def test_robots_run_facts_preserve_fetch_parse_and_policy_states() -> None:
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-robots", "config", "tool", "rules"))

    persist_robots_run_facts(
        store,
        "run-robots",
        origin="https://example.test",
        robots_text="User-agent: *\nDisallow: /private\nSitemap: /sitemap.xml\n",
        status_code=200,
        user_agents=("*", "GPTBot"),
    )

    facts = {(fact.family, fact.subject): fact for fact in store.iter_run_facts("run-robots")}
    assert facts[("robots.fetch", "https://example.test")].payload["state"] == "available"
    parsed = facts[("robots.parsed", "https://example.test")].payload
    assert parsed["state"] == "present"
    assert parsed["sitemaps"] == ["/sitemap.xml"]
    assert parsed["parser_version"]
    assert facts[("robots.policy", "https://example.test|rfc9309|GPTBot")].payload["interpretation"] == "rfc9309"
    replayed = robots_policy_from_run_facts(store, "run-robots", origin="https://example.test")
    assert replayed.sitemaps == ("/sitemap.xml",)


def test_robots_run_facts_keep_absent_and_unreachable_distinct() -> None:
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-robots-missing", "config", "tool", "rules"))

    persist_robots_run_facts(
        store,
        "run-robots-missing",
        origin="https://example.test",
        robots_text=None,
        status_code=404,
    )
    persist_robots_run_facts(
        store,
        "run-robots-missing",
        origin="https://other.test",
        robots_text=None,
        status_code=503,
    )

    states = {fact.subject: fact.payload["state"] for fact in store.iter_run_facts("run-robots-missing", "robots.fetch")}
    assert states == {
        "https://example.test": "unavailable",
        "https://other.test": "unreachable",
    }


def test_sitemap_run_facts_preserve_discovery_parse_and_urls() -> None:
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-sitemap", "config", "tool", "rules"))

    persist_sitemap_run_facts(
        store,
        "run-sitemap",
        origin="https://example.test",
        documents=(
            "<urlset><url><loc>/relative</loc></url><url><loc>https://example.test/a</loc></url><url><loc>https://other.test/b</loc></url></urlset>",
            "<not-xml",
        ),
        source_urls=("https://example.test/sitemap.xml", "https://example.test/broken.xml"),
    )

    facts = {(fact.family, fact.subject): fact for fact in store.iter_run_facts("run-sitemap")}
    assert facts[("sitemap.discovery", "https://example.test")].payload["source_count"] == 2
    assert facts[("sitemap.fetch", "https://example.test/sitemap.xml")].payload["source_kind"] == "supplied"
    assert facts[("sitemap.fetch", "https://example.test/sitemap.xml")].payload["state"] == "supplied"
    assert facts[("sitemap.parsed", "https://example.test/broken.xml")].payload["state"] == "parse-error"
    urls = facts[("sitemap.urls", "https://example.test")].payload
    assert urls["same_origin"] == ["https://example.test/relative", "https://example.test/a"]
    assert urls["cross_origin_unknown"] == ["https://other.test/b"]
    report = sitemap_reconciliation_from_run_facts(
        store,
        "run-sitemap",
        origin="https://example.test",
        records={"https://example.test/a": {"status_code": 200}},
    )
    assert "https://example.test/a" in report.sitemap_urls
    assert "https://example.test/a" not in report.classifications.sitemap_only


def test_sitemap_run_facts_preserve_fetch_failure_without_fake_document() -> None:
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-sitemap-failure", "config", "tool", "rules"))

    persist_sitemap_run_facts(
        store,
        "run-sitemap-failure",
        origin="https://example.test",
        documents=(
            SimpleNamespace(
                source_url="https://example.test/missing.xml",
                source_kind="robots_declared",
                fetch_state="not_found",
                body=None,
                final_url="https://example.test/missing.xml",
                status_code=404,
                error_kind=None,
            ),
            SimpleNamespace(
                source_url="https://example.test/down.xml",
                source_kind="explicit",
                fetch_state="unreachable",
                body=None,
                final_url=None,
                status_code=None,
                error_kind="timeout",
            ),
        ),
    )

    facts = {(fact.family, fact.subject): fact for fact in store.iter_run_facts("run-sitemap-failure")}
    assert facts[("sitemap.fetch", "https://example.test/missing.xml")].payload["state"] == "not_found"
    assert facts[("sitemap.fetch", "https://example.test/down.xml")].payload["error_kind"] == "timeout"
    assert facts[("sitemap.parsed", "https://example.test/down.xml")].payload["state"] == "unreachable"


def test_audit_service_persists_sitemap_run_fact_schema_identity() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<title>Stored</title>")

    store = MemorySiteStore()
    result = AuditService().run(
        AuditRequest(
            target="https://example.test/sitemap.xml",
            discovery_kind="sitemap",
            discovery_sitemap_xml="<urlset><url><loc>https://example.test/</loc></url></urlset>",
            max_pages=1,
            allow_private=True,
            transport=httpx.MockTransport(handler),
            store=store,
        )
    )

    assert calls == ["https://example.test/"]
    versions = dict(store.get_run(result.run.context.run_id).fact_schema_versions)
    assert versions["sitemap.discovery"] == "1"
    assert versions["sitemap.parsed"] == "1"
    assert versions["sitemap.urls"] == "1"


def test_audit_service_persists_real_robots_sitemap_discovery_run_facts() -> None:
    calls: list[str] = []
    documents = {
        "https://example.test/robots.txt": (
            200,
            "text/plain",
            b"User-agent: *\nSitemap: /sitemap-index.xml\n",
        ),
        "https://example.test/sitemap-index.xml": (
            200,
            "application/xml",
            b"<sitemapindex><sitemap><loc>/nested.xml</loc></sitemap></sitemapindex>",
        ),
        "https://example.test/nested.xml": (
            200,
            "application/xml",
            b"<urlset><url><loc>/page</loc></url></urlset>",
        ),
        "https://example.test/page": (
            200,
            "text/html",
            b"<title>Discovered</title>",
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        status, content_type, body = documents[url]
        return httpx.Response(status, headers={"content-type": content_type}, content=body)

    store = MemorySiteStore()
    result = AuditService().run(
        AuditRequest(
            target="https://example.test/",
            discovery_kind="robots-sitemap",
            max_pages=1,
            allow_private=True,
            transport=httpx.MockTransport(handler),
            store=store,
        )
    )

    assert "https://example.test/robots.txt" in calls
    assert "https://example.test/sitemap-index.xml" in calls
    assert "https://example.test/nested.xml" in calls
    assert "https://example.test/page" in calls
    facts = {(fact.family, fact.subject): fact for fact in store.iter_run_facts(result.run.context.run_id)}
    assert facts[("robots.fetch", "https://example.test")].payload["state"] == "available"
    assert facts[("sitemap.fetch", "https://example.test/sitemap-index.xml")].payload["source_kind"] == "robots_declared"
    assert facts[("sitemap.fetch", "https://example.test/nested.xml")].payload["source_kind"] == "sitemap_index"
    assert facts[("sitemap.urls", "https://example.test")].payload["same_origin"] == ["https://example.test/page"]
    versions = dict(store.get_run(result.run.context.run_id).fact_schema_versions)
    assert versions["robots.fetch"] == "1"
    assert versions["sitemap.fetch"] == "1"
