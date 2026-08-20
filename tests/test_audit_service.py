from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from agentready.audit_service import AuditRequest, AuditService
from agentready.crawler import CrawlCoverage, CrawlResult
from agentready.audit_core.store import MemorySiteStore
from tests.fixtures.site_lab import SiteLabServer


def test_seo_normalizes_content_type_parameters_from_fixture():
    with SiteLabServer() as site:
        result = AuditService().run(
            AuditRequest(
                target=site.base_url,
                mode="seo",
                crawl=True,
                max_pages=4,
                allow_private=True,
            )
        )

    page_available = [check for check in result.seo_report.checks if check.id == "page-available"]
    assert page_available
    assert page_available[0].status == "pass"


def test_audit_request_exposes_bounded_discovery_sources_and_provenance():
    request = AuditRequest(
        target="https://example.test/",
        discovery_kind="list",
        discovery_urls=("https://example.test/b", "https://example.test/a", "https://example.test/b"),
        discovery_limit=2,
    )
    seeds, plan_hash = AuditService._discovery_seeds(request.target, request)
    assert seeds == ("https://example.test/b", "https://example.test/a")
    assert len(plan_hash) == 64
    assert request.configuration()["discovery_kind"] == "list"


def test_audit_request_records_full_discovered_mode():
    request = AuditRequest(target="https://example.test/", profile="quick", full_discovered=True)
    assert request.full_discovered is True
    assert request.configuration()["full_discovered"] is True


def test_audit_request_sitemap_rejects_external_urls_and_missing_xml():
    with pytest.raises(ValueError, match="discovery_sitemap_xml"):
        AuditRequest(target="https://example.test/", discovery_kind="sitemap")
    request = AuditRequest(
        target="https://example.test/sitemap.xml",
        discovery_kind="sitemap",
        discovery_sitemap_xml="<urlset><url><loc>/a</loc></url><url><loc>https://other.test/b</loc></url></urlset>",
    )
    seeds, _ = AuditService._discovery_seeds("https://example.test/", request)
    assert seeds == ("https://example.test/a",)


def test_audit_check_limit_is_bounded_and_zero_means_unlimited():
    checks = [object(), object(), object()]
    assert len(AuditService._apply_check_limit(checks, {"check_limit": 2})) == 2
    assert AuditService._apply_check_limit(checks, {"check_limit": 0}) == checks
    with pytest.raises(ValueError, match="check_limit"):
        AuditService._apply_check_limit(checks, {"check_limit": 501})


def _transport(page_count: int = 10) -> httpx.MockTransport:
    pages = {
        "https://example.test/": "".join(f'<a href="/page-{index}">page</a>' for index in range(page_count)),
    }
    pages.update({f"https://example.test/page-{index}": "<title>Page</title>" for index in range(page_count)})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=pages.get(str(request.url), "").encode(),
        )

    return httpx.MockTransport(handler)


def test_audit_service_applies_exact_max_pages_and_reports_partial_coverage():
    result = AuditService().run(
        AuditRequest(
            target="https://example.test/",
            max_pages=3,
            limits={"max_depth": 2, "concurrency": 1},
            allow_private=True,
            transport=_transport(),
        )
    )

    assert result.crawl.coverage.fetched == 3
    assert result.crawl.coverage.max_pages_hit is True
    assert result.crawl.coverage.classification.value == "partial_limit"
    assert len(result.fact_views) == result.crawl.coverage.fetched
    assert result.to_dict()["coverage"]["urls_fetched"] == 3
    assert result.to_dict()["coverage"]["limit"]["max_pages_hit"] is True
    assert result.report.run_id == result.run.context.run_id
    assert result.run.state.value == "partial"
    assert result.run.completed_at is not None


def test_audit_service_applies_ruleset_to_saved_facts_without_extra_fetches():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b'<p class="known">agent marker</p>')

    rules = "version: 1\nrules:\n  - id: marker\n    title: Marker\n    assert:\n      kind: text\n      pattern: agent\n  - id: css\n    assert:\n      kind: css\n      pattern: p.known\n"
    store = MemorySiteStore()
    result = AuditService().run(AuditRequest(target="https://example.test/", max_pages=1, allow_private=True, transport=httpx.MockTransport(handler), store=store, ruleset=rules))
    assert len(calls) == 1
    assert result.run.context.ruleset_version == "1"
    assert result.run.context.ruleset_hash
    assert any(item.id.startswith("custom-rule:marker:") and item.status.value == "fail" for item in result.report.findings)
    assert any(item.id.startswith("custom-rule:css:") and item.status.value == "fail" for item in result.report.findings)
    assert list(store.iter_findings(result.run.context.run_id))


def test_audit_service_ignores_non_http_links_without_aborting_crawl():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b'<a href="tel:+10000000000">call</a><a href="mailto:test@example.test">mail</a>',
        )

    result = AuditService().run(
        AuditRequest(
            target="https://example.test/",
            max_pages=1,
            allow_private=True,
            transport=httpx.MockTransport(handler),
        )
    )

    assert result.crawl.coverage.fetched == 1
    assert result.crawl.coverage.failed == 0


def test_audit_service_seo_mode_uses_shared_crawler_and_atomic_facts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=(
                b"<title>Canonical SEO page</title><meta name='robots' content='noindex'>"
                b"<link rel='canonical' href='/preferred'><h1>Heading</h1>"
            ),
        )

    result = AuditService().run(
        AuditRequest(
            target="https://example.test/",
            mode="seo",
            max_pages=5,
            allow_private=True,
            transport=httpx.MockTransport(handler),
        )
    )

    assert result.seo_report is not None
    assert result.seo_report.schema == "agentready.seo.v2"
    assert result.crawl.coverage.fetched == 1
    assert len(result.fact_views) == 1
    assert result.fact_views[0].facts is not None
    assert {check.id for check in result.seo_report.checks} >= {
        "page-available",
        "metadata",
        "indexability",
        "canonical",
        "crawl-coverage",
    }
    assert next(check for check in result.seo_report.checks if check.id == "indexability").status == "fail"
    assert result.seo_report.recommendations
    assert all(check.remediation for check in result.seo_report.checks if check.status in {"fail", "warn", "error"})
    assert result.to_dict()["request"]["mode"] == "seo"


def test_audit_service_seo_mode_adds_site_wide_diagnostics() -> None:
    pages = {
        "https://example.test/": b'<title>Same</title><h1>Home</h1><a href="/de">de</a>',
        "https://example.test/de": b'<title>Same</title><h1>Home</h1><a href="/">en</a>',
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=pages[str(request.url)])

    result = AuditService().run(
        AuditRequest(
            target="https://example.test/",
            mode="seo",
            crawl=True,
            max_pages=2,
            allow_private=True,
            transport=httpx.MockTransport(handler),
        )
    )
    ids = {check.id for check in result.seo_report.checks}
    assert {
        "duplicate-metadata-site",
        "duplicate-content-site",
        "thin-content-site",
        "heading-structure-site",
        "canonical-consistency-site",
        "hreflang-reciprocity-site",
    } <= ids
    assert next(check for check in result.seo_report.checks if check.id == "duplicate-metadata-site").status == "fail"


def test_audit_service_seo_selection_is_symmetric_for_site_rules() -> None:
    pages = {
        "https://example.test/": b"<title>Same</title><h1>Home</h1><a href='/de'>de</a>",
        "https://example.test/de": b"<title>Same</title><h1>Home</h1><a href='/'>en</a>",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, content=pages[str(request.url)])

    included = AuditService().run(AuditRequest(
        target="https://example.test/",
        mode="seo",
        crawl=True,
        max_pages=2,
        include=("duplicate-metadata-site",),
        allow_private=True,
        transport=httpx.MockTransport(handler),
    ))
    assert {check.id for check in included.seo_report.checks} == {"duplicate-metadata-site"}

    excluded = AuditService().run(AuditRequest(
        target="https://example.test/",
        mode="seo",
        crawl=True,
        max_pages=2,
        exclude=("duplicate-metadata-site",),
        allow_private=True,
        transport=httpx.MockTransport(handler),
    ))
    assert all(check.id != "duplicate-metadata-site" for check in excluded.seo_report.checks)


def test_audit_service_profile_selection_changes_config_identity_deterministically():
    requests = (
        AuditRequest(
            target="https://example.test/",
            profile="quick",
            max_pages=1,
            allow_private=True,
            transport=_transport(1),
        ),
        AuditRequest(
            target="https://example.test/",
            profile="standard",
            max_pages=1,
            allow_private=True,
            transport=_transport(1),
        ),
        AuditRequest(
            target="https://example.test/",
            profile="deep",
            max_pages=1,
            allow_private=True,
            transport=_transport(1),
        ),
        AuditRequest(
            target="https://example.test/",
            profile="custom",
            max_pages=1,
            limits={"max_depth": 2, "concurrency": 1},
            allow_private=True,
            transport=_transport(1),
        ),
    )

    results = [AuditService().run(request) for request in requests]

    assert [result.request.profile for result in results] == [
        "quick",
        "standard",
        "deep",
        "custom",
    ]
    assert len({result.run.context.config_hash for result in results}) == 4
    assert all(result.to_dict()["run"]["config_hash"] == result.run.context.config_hash for result in results)


def test_audit_request_fields_reach_canonical_execution_without_network(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    class FakeCrawler:
        def __init__(self, scope, *, config, policy, transport, store, run_context, render, verify):
            captured["scope"] = scope
            captured["config"] = config
            captured["render"] = render
            captured["verify"] = verify
            captured["run_context"] = run_context

        async def crawl(self):
            return CrawlResult(
                (),
                CrawlCoverage(
                    discovered=1,
                    queued_remaining=0,
                    fetched=1,
                    parsed_html=1,
                    skipped_policy=0,
                    failed=0,
                    max_pages_hit=False,
                    max_depth_hit=False,
                    deadline_hit=False,
                    frontier_exhausted=True,
                ),
            )

    monkeypatch.setattr("agentready.audit_service.AsyncCrawler", FakeCrawler)
    request = AuditRequest(
        target="https://example.test/",
        profile="custom",
        max_pages=7,
        timeout=4,
        limits={"max_depth": 3, "concurrency": 2},
        include=("https://example.test/docs/*",),
        exclude=("https://example.test/private",),
        render=True,
        provider="pagespeed-fixture",
        language="ru",
        allow_private=True,
        run_rules=False,
    )

    result = AuditService().run(request)
    payload = result.to_dict()

    assert captured["config"].max_pages == 7
    assert captured["config"].max_depth == 3
    assert captured["config"].concurrency == 2
    assert captured["config"].timeout == 4
    assert captured["scope"].include_rules == request.include
    assert captured["scope"].exclude_rules == request.exclude
    assert captured["render"] is True
    assert captured["verify"] is True
    assert payload["request"] == {
        "preset": "all",
        "profile": "custom",
        "max_pages": 7,
        "timeout": 4,
        "limits": {"max_depth": 3, "concurrency": 2},
        "include": ["https://example.test/docs/*"],
        "exclude": ["https://example.test/private"],
        "selected_urls": [],
        "render": True,
        "provider": "pagespeed-fixture",
        "language": "ru",
        "run_rules": False,
    }
    assert payload["run"]["config_hash"] == result.run.context.config_hash
    assert result.report.coverage.urls_fetched == 1
    assert "provider" not in captured


def test_audit_request_projection_fields_are_preserved_and_rescans_have_lineage(monkeypatch: pytest.MonkeyPatch):
    class FakePage:
        url = ""

        async def content(self) -> str:
            if self.url.endswith("/"):
                return '<a href="/page-0">page</a><a href="/page-1">page</a>'
            return "<title>Page</title>"

    class FakeBrowserPool:
        def __init__(self, policy):
            self.page_instance = FakePage()

        async def start(self) -> None:
            return None

        async def close(self) -> None:
            return None

        @asynccontextmanager
        async def page(self):
            yield self.page_instance

        async def goto(self, page, url: str, **kwargs):
            page.url = url
            return SimpleNamespace(status=200)

    monkeypatch.setattr("agentready.crawler.BrowserPool", FakeBrowserPool)
    service = AuditService()
    first = service.run(
        AuditRequest(
            target="https://example.test/",
            profile="quick",
            max_pages=1,
            render=True,
            provider="local-provider",
            language="ru",
            allow_private=True,
            transport=_transport(2),
        )
    )
    second = service.run(
        AuditRequest(
            target="https://example.test/",
            max_pages=1,
            parent_run_id=first.run.context.run_id,
            allow_private=True,
            transport=_transport(2),
        )
    )

    assert first.to_dict()["request"]["profile"] == "quick"
    assert first.to_dict()["request"]["render"] is True
    assert first.to_dict()["request"]["provider"] == "local-provider"
    assert first.to_dict()["request"]["language"] == "ru"
    assert first.to_dict()["run"]["config_hash"] == first.run.context.config_hash
    assert second.run.context.run_id != first.run.context.run_id
    assert second.to_dict()["run"]["parent_run_id"] == first.run.context.run_id
    assert second.lineage_id == first.run.context.run_id


def test_audit_service_applies_include_and_exclude_scope_rules():
    result = AuditService().run(
        AuditRequest(
            target="https://example.test/",
            max_pages=10,
            include=("https://example.test/*",),
            exclude=("https://example.test/page-1",),
            allow_private=True,
            transport=_transport(3),
        )
    )
    assert {page.url for page in result.crawl.pages} == {
        "https://example.test/",
        "https://example.test/page-0",
        "https://example.test/page-2",
    }


def test_audit_service_separates_check_ids_from_url_scope_rules(monkeypatch):
    captured = {}

    class FakeCrawler:
        def __init__(self, scope, **kwargs):
            captured["scope"] = scope

        async def crawl(self):
            return CrawlResult(
                (),
                CrawlCoverage(1, 0, 1, 1, 0, 0, False, False, False, True),
            )

    monkeypatch.setattr("agentready.audit_service.AsyncCrawler", FakeCrawler)
    result = AuditService().run(
        AuditRequest(
            target="https://example.test/",
            include=("robots-txt", "https://example.test/docs/*"),
            exclude=("https://example.test/private",),
            run_rules=False,
            allow_private=True,
        )
    )
    assert result.report.to_dict()["schema"] == "agentready.audit.v2"
    assert captured["scope"].include_rules == ("https://example.test/docs/*",)
    assert captured["scope"].exclude_rules == ("https://example.test/private",)


def test_audit_service_selects_same_origin_urls_for_child_rescan():
    result = AuditService().run(
        AuditRequest(
            target="https://example.test/",
            selected_urls=("https://example.test/page-1",),
            parent_run_id="parent-run",
            max_pages=10,
            allow_private=True,
            transport=_transport(3),
        )
    )
    assert {page.url for page in result.crawl.pages} == {"https://example.test/page-1"}
    assert result.lineage_id == "parent-run"


def test_selected_rescan_does_not_follow_links_from_selected_pages():
    result = AuditService().run(
        AuditRequest(
            target="https://example.test/",
            selected_urls=("https://example.test/",),
            parent_run_id="parent-run",
            max_pages=10,
            allow_private=True,
            transport=_transport(3),
        )
    )

    assert {page.url for page in result.crawl.pages} == {"https://example.test/"}
    assert result.crawl.coverage.classification.value == "complete_within_scope"
