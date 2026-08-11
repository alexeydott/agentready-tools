from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest

from agentready.audit_service import AuditRequest, AuditService
from agentready.crawler import CrawlCoverage, CrawlResult


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
    assert result.to_dict()["coverage"]["urls_fetched"] == 3
    assert result.to_dict()["coverage"]["limit"]["max_pages_hit"] is True
    assert result.report.run_id == result.run.context.run_id
    assert result.run.state.value == "partial"
    assert result.run.completed_at is not None


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
        def __init__(self, scope, *, config, policy, transport, store, run_context, render):
            captured["scope"] = scope
            captured["config"] = config
            captured["render"] = render
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
