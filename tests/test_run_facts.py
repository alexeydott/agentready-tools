import httpx

from agentready.audit_core import (
    MemorySiteStore,
    RunRecord,
    persist_robots_run_facts,
    persist_sitemap_run_facts,
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
    assert facts[("sitemap.parsed", "https://example.test/broken.xml")].payload["state"] == "parse-error"
    urls = facts[("sitemap.urls", "https://example.test")].payload
    assert urls["same_origin"] == ["https://example.test/a"]
    assert urls["cross_origin_unknown"] == ["/relative", "https://other.test/b"]


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
