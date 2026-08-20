from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import agentready.server as server_module
from agentready.ai_provider import ProviderModel
from agentready.audit_core.store import (
    MemorySiteStore,
    ContentRetention,
    MetricRecord,
    PageRecord,
    RedirectFact,
    RunRecord,
    RunUrlRecord,
    RunUrlState,
)
from agentready.server import _V2_ROBOTS, _V2_RUNS, _remediation_confirmation, _render_v2_dashboard, _run_and_save_v2_job, _resolve_rescan_selection, app


def test_v2_dashboard_localizes_coverage_and_status_values():
    html = _render_v2_dashboard({
        "request": {"language": "ru"},
        "target": "https://example.test/",
        "coverage": {"classification": "partial_limit", "urls_fetched": 1},
        "findings": [{"id": "crawl-coverage", "status": "warn", "summary": "partial_limit"}],
    })
    assert "Частичное — достигнут лимит страниц" in html
    assert "предупреждение" in html
    assert "partial_limit" not in html.split("<script", 1)[0]


def test_finding_remediation_opens_evidence_and_confirmation_states():
    parent_id, child_id = "remediation-parent", "remediation-child"
    parent = MemorySiteStore()
    parent.put_finding(parent_id, "title", {
        "id": "title", "title": "Title", "status": "fail", "reason": "missing",
        "affected_urls": ["https://example.test/page"],
        "evidence": [{"id": "title", "summary": "missing", "url": "https://example.test/page"}],
    })
    child = MemorySiteStore()
    child.put_finding(child_id, "title", {
        "id": "title", "title": "Title", "status": "pass", "reason": "fixed",
        "evidence": [{"id": "title", "summary": "present", "url": "https://example.test/page"}],
    })
    _V2_RUNS.put(parent_id, parent)
    _V2_RUNS.put(child_id, child)
    client = TestClient(app)
    task = client.get(f"/v2/runs/{parent_id}/findings/title/remediation", params={"language": "ru"})
    assert task.status_code == 200
    assert task.json()["affected_urls"] == ["https://example.test/page"]
    assert "Исправьте" in task.json()["instructions"]
    confirmation = _remediation_confirmation(parent_id, child_id, ("title",))
    assert confirmation["status"] == "passed"
    assert confirmation["items"][0]["state"] == "resolved"


def test_schedule_crud_history_and_worker_status():
    server_module._V2_PROJECT_STORE = MemorySiteStore()
    client = TestClient(app)
    assert client.post("/v2/projects", json={"project_id": "sched-project", "name": "Schedule", "target": "https://example.test/"}).status_code == 200
    created = client.post("/v2/projects/sched-project/schedules", json={"schedule_id": "daily", "interval_seconds": 86400, "next_run_at": "2099-01-01T00:00:00+00:00"})
    assert created.status_code == 200 and created.json()["enabled"] is True
    assert client.get("/v2/projects/sched-project/schedules").json()["items"][0]["schedule_id"] == "daily"
    updated = client.patch("/v2/schedules/daily", json={"enabled": False})
    assert updated.status_code == 200 and updated.json()["enabled"] is False
    assert client.get("/v2/schedules/daily/history").json()["items"] == []
    assert client.get("/v2/schedules/worker").json()["running"] is False
    assert client.delete("/v2/schedules/daily").json()["deleted"] is True


def test_selected_rescan_maps_findings_and_rejects_stale_selection():
    store = MemorySiteStore()
    store.begin_run(RunRecord("parent-1", "config", "tool", "rules"))
    store.put_run_url(RunUrlRecord("parent-1", "https://example.test/page", RunUrlState.FETCHED))
    store.put_finding("parent-1", "title", {"id": "title", "status": "fail", "affected_urls": ["https://example.test/page"]})
    _V2_RUNS.put("parent-1", store)
    request = server_module.V2AuditRequest(url="https://example.test", rescan_of="parent-1", selected_finding_ids=["title"], confirm=True)
    urls, selection_hash, ids = _resolve_rescan_selection(request, "parent-1")
    assert urls == ["https://example.test/page"]
    assert selection_hash and ids == ("title",)
    stale = request.model_copy(update={"selection_hash": "stale-hash"})
    with pytest.raises(ValueError, match="stale"):
        _resolve_rescan_selection(stale, "parent-1")


def test_v2_dashboard_print_projection_is_summary_oriented():
    html = _render_v2_dashboard({
        "request": {"language": "ru"},
        "target": "https://example.test/",
        "coverage": {"classification": "complete_within_scope", "urls_fetched": 1200},
        "findings": [
            {"id": "a", "status": "fail", "summary": "broken"},
            {"id": "b", "status": "warn", "summary": "warning"},
        ],
    })
    assert "Сводка для печати" in html
    assert "Ошибки: 1" in html
    assert "@media print" in html


def test_v2_api_describes_all_discovered_page_mode():
    schema = server_module.V2AuditRequest.model_json_schema()
    assert "all discovered same-origin pages" in schema["properties"]["max_pages"]["description"]
    assert "all discovered same-origin pages" in schema["properties"]["discovery_kind"]["description"]


def test_v2_dashboard_print_table_localizes_finding_title_and_description():
    html = _render_v2_dashboard({
        "request": {"language": "ru"},
        "target": "https://example.test/",
        "coverage": {"classification": "complete_within_scope", "urls_fetched": 1},
        "findings": [{
            "id": "robots-txt",
            "title": "Robots policy",
            "status": "fail",
            "summary": "robots.txt must be HTTP 200 plain text and contain a User-agent directive",
        }],
    })
    visible = html.split("<script", 1)[0]
    assert "robots.txt должен возвращаться с HTTP 200" in visible
    assert "Robots policy" not in visible


def test_background_v2_job_persists_json_and_html_artifacts(monkeypatch):
    saved = []

    def fake_scan(request, progress_callback=None):
        return {"request": {"language": "ru"}, "target": request.url, "coverage": {}, "findings": []}

    monkeypatch.setattr(server_module, "_run_v2_scan", fake_scan)
    monkeypatch.setattr(server_module, "save_report", lambda content, **kwargs: saved.append(kwargs["fmt"]) or "report")
    result = _run_and_save_v2_job(SimpleNamespace(url="https://example.test/"), lambda values: None)
    assert result["target"] == "https://example.test/"
    assert saved == ["json", "html"]


def test_server_exposes_all_read_only_audit_modes():
    paths = {route.path for route in app.routes}
    assert {
        "/",
        "/dashboard",
        "/healthz",
        "/ai/status",
        "/ai/tools",
        "/ai/providers",
        "/ai/providers/active",
        "/ai/providers/{provider_id}/models",
        "/checks",
        "/seo/checks",
        "/v2/capabilities",
            "/v2/audit/dashboard",
            "/v2/seo/audit",
            "/v2/seo/audit/dashboard",
            "/v2/mobile/audit",
            "/v2/mobile/audit/dashboard",
    } <= paths


def test_custom_rules_endpoints_validate_and_debug_without_crawl():
    client = TestClient(app)
    rules = "version: 1\nrules:\n  - id: text\n    assert:\n      kind: text\n      pattern: agent\n"
    validated = client.post("/v2/custom-rules/validate", json={"rules": rules})
    assert validated.status_code == 200
    assert validated.json()["valid"] is True
    debugged = client.post("/v2/custom-rules/debug", json={"rules": rules, "text": "agent ready"})
    assert debugged.status_code == 200
    assert debugged.json()["matches"][0]["count"] == 1
    assert "/v2/custom-rules/apply" in {route.path for route in app.routes}


def test_custom_rules_debug_uses_saved_representation_when_run_is_selected():
    from agentready import server as server_module

    run_id = "debug-saved-run"
    url = "https://example.test/"
    server_module._V2_RULE_REPRESENTATIONS[(run_id, url)] = {
        "url": url,
        "text": "saved marker",
        "raw_text": '<p class="known">saved marker</p>',
        "headers": {},
        "structured_data": [],
        "links": [],
        "resources": [],
    }
    rules = "version: 1\nrules:\n  - id: marker\n    assert:\n      kind: text\n      pattern: saved\n  - id: css\n    assert:\n      kind: css\n      pattern: p.known\n"
    response = TestClient(app).post("/v2/custom-rules/debug", json={"rules": rules, "run_id": run_id, "url_key": url, "url": url, "text": url})
    assert response.status_code == 200
    payload = response.json()
    assert payload["matches"][0]["count"] == 1
    assert payload["matches"][1]["count"] == 1


def test_saved_representation_endpoint_is_loopback_only():
    from agentready import server as server_module

    run_id = "representation-boundary-run"
    url = "https://example.test/"
    server_module._V2_RULE_REPRESENTATIONS[(run_id, url)] = {"url": url, "text": "private"}
    remote = TestClient(app, client=("203.0.113.10", 41000))
    response = remote.get(f"/v2/runs/{run_id}/representations/{url}")
    assert response.status_code == 403


def test_link_graph_endpoints_project_cached_occurrences_and_node_detail():
    store = MemorySiteStore(retention=ContentRetention.FULL_CONTENT)
    run_id = "graph-api-run"
    store.put_page(PageRecord(run_id, "https://example.test/", "https://example.test/", depth=0))
    store.put_page(PageRecord(run_id, "https://example.test/a", "https://example.test/a", depth=1))
    store.put_page(PageRecord(run_id, "https://example.test/isolated", "https://example.test/isolated", depth=1))
    store.put_link(run_id, "https://example.test/", "/a", ordinal=0, target_key="https://example.test/a", rel="nofollow")
    _V2_RUNS.put(run_id, store)
    client = TestClient(app)
    response = client.get(f"/v2/runs/{run_id}/graph?limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert any(item["url"].endswith("/isolated") and item["disconnected"] for item in payload["items"])
    node = client.get(f"/v2/runs/{run_id}/graph/node", params={"url": "https://example.test/a"})
    assert node.status_code == 200
    assert node.json()["node"]["nofollow_inlinks"] == 1


def test_duplicate_cluster_endpoints_use_stored_page_content_and_detail():
    store = MemorySiteStore(retention=ContentRetention.FULL_CONTENT)
    run_id = "duplicate-api-run"
    store.put_page(PageRecord(run_id, "https://example.test/a", "https://example.test/a", content="same body"))
    store.put_page(PageRecord(run_id, "https://example.test/b", "https://example.test/b", content="same body"))
    _V2_RUNS.put(run_id, store)
    client = TestClient(app)
    response = client.get(f"/v2/runs/{run_id}/duplicates")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    cluster_id = payload["items"][0]["cluster_id"]
    detail = client.get(f"/v2/runs/{run_id}/duplicates/{cluster_id}")
    assert detail.status_code == 200
    assert len(detail.json()["cluster"]["members"]) == 2


def test_project_api_crud_and_history_contract():
    client = TestClient(app)
    project_id = "api-project-contract"
    created = client.post("/v2/projects", json={"project_id": project_id, "name": "Example", "target": "https://example.test/", "default_profile": "quick"})
    assert created.status_code == 200
    updated = client.patch(f"/v2/projects/{project_id}", json={"name": "Renamed"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"
    listed = client.get("/v2/projects")
    assert any(item["project_id"] == project_id for item in listed.json())
    history = client.get(f"/v2/projects/{project_id}/runs")
    assert history.status_code == 200
    deleted = client.delete(f"/v2/projects/{project_id}")
    assert deleted.json()["runs_retained"] is True


def test_server_rejects_removed_v1_audit_routes():
    client = TestClient(app)
    for path in ("/scan", "/scan/dashboard", "/seo/audit", "/mobile/audit"):
        assert client.post(path, json={"url": "https://example.com"}).status_code == 404


def test_virtual_robots_endpoint_uses_stored_inventory_without_fetching():
    run_id = "run-robots-http"
    store = MemorySiteStore()
    store.begin_run(RunRecord(run_id, "config", "tool", "rules"))
    for url in ("https://example.com/public/a", "https://example.com/private/a"):
        store.put_run_url(RunUrlRecord(run_id, url, RunUrlState.PARSED))
    server_module._V2_RUNS.put(run_id, store)

    response = TestClient(app).post(
        f"/v2/runs/{run_id}/robots/simulate",
        json={
            "live_robots": "User-agent: *\nAllow: /\n",
            "proposed_robots": "User-agent: *\nDisallow: /private\n",
            "user_agents": ["Googlebot", "GPTBot"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == "agentready.robots-simulation.v2"
    assert payload["newly_blocked"] == ["https://example.com/private/a"]
    assert set(payload["per_bot_diff"]) == {"Googlebot", "GPTBot"}
    assert payload["label"].startswith("SIMULATION")


def test_provider_enrichment_is_cached_opt_in_and_persists_typed_metrics():
    run_id = "run-provider-http"
    store = MemorySiteStore()
    store.begin_run(RunRecord(run_id, "config", "tool", "rules"))
    store.put_run_url(RunUrlRecord(run_id, "https://example.com/", RunUrlState.PARSED))
    server_module._V2_RUNS.put(run_id, store)
    client = TestClient(app)

    not_requested = client.post(
        f"/v2/runs/{run_id}/provider-enrichment",
        json={"provider": "ga4"},
    )
    assert not_requested.status_code == 200
    assert not_requested.json()["status"] == "not_requested"
    assert "credential" in not_requested.json()["detail"]

    cached = client.post(
        f"/v2/runs/{run_id}/provider-enrichment",
        json={
            "provider": "pagespeed",
            "cached_metrics": [{
                "name": "lcp",
                "value": 1200,
                "unit": "ms",
                "source": "fixture",
                "version": "psi-v5",
                "observed_at": "2026-08-12T00:00:00+00:00",
            }],
        },
    )
    assert cached.status_code == 200
    assert cached.json()["from_cache"] is True
    assert next(iter(store.iter_metrics(run_id))).provider == "pagespeed"


def test_provider_job_endpoint_uses_bounded_job_path():
    run_id = "run-provider-job"
    store = MemorySiteStore()
    store.begin_run(RunRecord(run_id, "config", "tool", "rules"))
    server_module._V2_RUNS.put(run_id, store)
    response = TestClient(app).post(
        f"/v2/runs/{run_id}/provider-jobs",
        json={"provider": "gsc"},
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    assert response.json()["provider"] == "gsc"
    assert TestClient(app).get(f"/v2/jobs/{job_id}").status_code == 200


def test_v2_endpoint_maps_request_fields_to_shared_audit_service(monkeypatch):
    captured = {}

    def fake_run(request):
        captured["request"] = request
        return SimpleNamespace(to_dict=lambda: {"schema": "agentready.audit.v2"})

    monkeypatch.setattr(server_module._AUDIT_SERVICE, "run", fake_run)
    response = server_module.audit_v2_endpoint(
        server_module.V2AuditRequest(
            url="https://example.com",
            profile="quick",
            max_pages=7,
            limits={"max_depth": 3},
            include=["https://example.com/*"],
            exclude=["https://example.com/private"],
            render=True,
            provider="local",
            language="ru",
            selected_urls=["https://example.com/page"],
        )
    )
    request = captured["request"]
    assert response["schema"] == "agentready.audit.v2"
    assert request.profile == "quick"
    assert request.max_pages == 7
    assert request.limits == {"max_depth": 3}
    assert request.include == ("https://example.com/*",)
    assert request.exclude == ("https://example.com/private",)
    assert request.render is True
    assert request.provider == "local"
    assert request.language == "ru"
    assert request.selected_urls == ("https://example.com/page",)


def test_v2_endpoint_propagates_all_supported_profiles(monkeypatch):
    captured = []

    def fake_run(request):
        captured.append(request)
        return SimpleNamespace(to_dict=lambda: {"schema": "agentready.audit.v2"})

    monkeypatch.setattr(server_module._AUDIT_SERVICE, "run", fake_run)
    for profile in ("quick", "standard", "deep", "custom"):
        response = server_module.audit_v2_endpoint(
            server_module.V2AuditRequest(
                url="https://example.com",
                profile=profile,
                limits={"max_depth": 2} if profile == "custom" else {},
            )
        )
        assert response["schema"] == "agentready.audit.v2"

    assert [request.profile for request in captured] == ["quick", "standard", "deep", "custom"]
    assert captured[-1].limits == {"max_depth": 2}


def test_v2_job_exposes_crawl_progress_and_rendered_report(monkeypatch):
    def fake_scan(request, *, parent_run_id=None, progress_callback=None):
        if progress_callback:
            progress_callback({"phase": "crawl", "fetched": 2, "discovered": 5})
        return {"schema": "agentready.audit.v2", "target": request.url, "coverage": {}, "findings": [], "run": {"id": "job-run"}}

    monkeypatch.setattr(server_module, "_run_v2_scan", fake_scan)
    client = TestClient(app)
    response = client.post("/v2/jobs", json={"url": "https://example.com", "max_pages": 2})
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    import time

    for _ in range(20):
        status = client.get(f"/v2/jobs/{job_id}").json()
        if status["status"] == "completed":
            assert status["progress"]["fetched"] == 2
            assert "html" in status
            break
        time.sleep(0.01)
    else:
        raise AssertionError("job did not complete")


def test_v2_job_status_list_is_bounded_and_does_not_expose_results():
    response = TestClient(app).get("/v2/jobs")
    assert response.status_code == 200
    assert isinstance(response.json()["items"], list)
    assert all("result" not in item for item in response.json()["items"])


def test_v2_inventory_endpoints_paginate_typed_store_records():
    run_id = "server-pagination"
    store = MemorySiteStore()
    for index in range(3):
        store.put_page(PageRecord(run_id, f"https://example.com/{index}", f"https://example.com/{index}"))
        store.put_run_url(RunUrlRecord(run_id, f"https://example.com/{index}", RunUrlState.FETCHED))
    store.put_link(run_id, "https://example.com/0", "/one", ordinal=0)
    store.put_link(run_id, "https://example.com/0", "/two", ordinal=1)
    store.put_resource(run_id, "https://example.com/0", "/asset.js", "script", ordinal=0)
    store.put_redirect(RedirectFact(run_id, "https://example.com/old", "https://example.com/new", 301, "/new"))
    store.put_metric(MetricRecord(run_id, "https://example.com/0", "test", "bytes", 10, "B", "test", "1", "now"))
    store.put_finding(run_id, "finding-1", {"status": "warn", "reason": "bounded"})
    server_module._V2_RUNS.put(run_id, store)
    client = TestClient(app)

    first = client.get(f"/v2/runs/{run_id}/pages", params={"limit": 2})
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    assert first.json()["next_cursor"]
    second = client.get(
        f"/v2/runs/{run_id}/pages",
        params={"limit": 2, "cursor": first.json()["next_cursor"]},
    )
    assert [item["url_key"] for item in second.json()["items"]] == ["https://example.com/2"]
    assert client.get(f"/v2/runs/{run_id}/run-urls").json()["total"] == 3
    assert client.get(f"/v2/runs/{run_id}/links").json()["total"] == 2
    assert client.get(f"/v2/runs/{run_id}/resources").json()["total"] == 1
    assert client.get(f"/v2/runs/{run_id}/redirects").json()["total"] == 1
    assert client.get(f"/v2/runs/{run_id}/findings").json()["total"] == 1
    assert client.get(f"/v2/runs/{run_id}/metrics").json()["total"] == 1
    assert client.get(f"/v2/runs/{run_id}/inventory/pages", params={"limit": 1}).json()["next_cursor"]
    overview = client.get(f"/v2/runs/{run_id}/overview")
    assert overview.status_code == 200
    assert overview.json()["inventory"]["pages"] == 3
    assert overview.json()["inventory"]["links"] == 2


def test_v2_run_registry_evicts_by_run_count_and_record_budget():
    registry = server_module._V2RunRegistry(max_runs=3, max_records=5)

    def make_store(run_id: str, pages: int) -> MemorySiteStore:
        store = MemorySiteStore()
        for index in range(pages):
            store.put_page(PageRecord(run_id, f"https://example.com/{run_id}/{index}", f"https://example.com/{run_id}/{index}"))
        return store

    for run_id in ("r1", "r2", "r3", "r4"):
        registry.put(run_id, make_store(run_id, 1))
    with pytest.raises(KeyError):
        registry.get("r1")
    assert registry.get("r4") is not None

    registry.put("big", make_store("big", 20))
    for run_id in ("r2", "r3", "r4"):
        with pytest.raises(KeyError):
            registry.get(run_id)
    assert registry.get("big") is not None


def test_v2_inventory_returns_404_for_evicted_runs(monkeypatch):
    registry = server_module._V2RunRegistry(max_runs=1, max_records=1_000)
    monkeypatch.setattr(server_module, "_V2_RUNS", registry)
    first = MemorySiteStore()
    first.put_page(PageRecord("evicted", "https://example.com/", "https://example.com/"))
    registry.put("evicted", first)
    second = MemorySiteStore()
    second.put_page(PageRecord("kept", "https://example.com/", "https://example.com/"))
    registry.put("kept", second)

    client = TestClient(app)
    assert client.get("/v2/runs/evicted/pages").status_code == 404
    assert client.get("/v2/runs/kept/pages").status_code == 200


def test_v2_inventory_rejects_invalid_kind_limits_and_unknown_runs():
    client = TestClient(app)
    assert client.get("/v2/runs/missing/pages").status_code == 404
    assert client.get("/v2/runs/missing/not-an-allowlisted-kind").status_code == 404
    assert client.get("/v2/runs/missing/inventory/not-an-allowlisted-kind").status_code == 422
    assert client.get("/v2/runs/missing/pages", params={"limit": 0}).status_code == 422
    assert client.get("/v2/runs/missing/pages", params={"limit": 1001}).status_code == 422


def test_v2_saved_views_execute_and_export_the_same_typed_query():
    run_id = "saved-view-server"
    store = MemorySiteStore()
    for index in range(2):
        store.put_page(PageRecord(run_id, f"https://example.com/{index}", f"https://example.com/{index}"))
    server_module._V2_RUNS.put(run_id, store)
    client = TestClient(app)

    created = client.post(
        "/v2/saved-views",
        json={
            "id": "saved-pages",
            "name": "Saved pages",
            "run_id": run_id,
            "kind": "pages",
            "limit": 1,
        },
    )
    assert created.status_code == 200
    assert created.json()["query"] == "PageQuery"
    executed = client.get("/v2/saved-views/saved-pages", params={"limit": 1})
    assert executed.status_code == 200
    assert executed.json()["total"] == 2
    exported = client.get("/v2/saved-views/saved-pages/export", params={"format": "csv"})
    assert exported.status_code == 200
    assert "url_key" in exported.json()["content"]


def test_v2_dashboard_inventory_reads_do_not_start_a_second_crawl(monkeypatch):
    run_id = "single-crawl"
    store = MemorySiteStore()
    store.put_page(PageRecord(run_id, "https://example.com/", "https://example.com/"))
    server_module._V2_RUNS.put(run_id, store)
    calls = []

    def fake_run(request, *, parent_run_id=None):
        calls.append(request)
        return {
            "schema": "agentready.audit.v2",
            "run": {"id": run_id},
            "request": {"language": "en"},
        }

    monkeypatch.setattr(server_module, "_run_v2_scan", fake_run)
    monkeypatch.setattr(server_module, "_render_v2_dashboard", lambda payload: "<html>ok</html>")
    client = TestClient(app)
    response = client.post(
        "/v2/audit/dashboard",
        json={"url": "https://example.com", "profile": "quick", "max_pages": 1},
    )
    assert response.status_code == 200
    assert client.get(f"/v2/runs/{run_id}/overview").status_code == 200
    assert client.get(f"/v2/runs/{run_id}/inventory/pages").status_code == 200
    assert len(calls) == 1


def test_v2_inventory_routes_use_typed_queries_not_arbitrary_sql(monkeypatch):
    run_id = "typed-query"
    store = MemorySiteStore()
    store.put_page(PageRecord(run_id, "https://example.com/", "https://example.com/"))
    server_module._V2_RUNS.put(run_id, store)
    captured = []
    original = server_module.QueryService.execute

    def execute(self, query):
        captured.append(type(query).__name__)
        return original(self, query)

    monkeypatch.setattr(server_module.QueryService, "execute", execute)
    response = TestClient(app).get(f"/v2/runs/{run_id}/pages")
    assert response.status_code == 200
    assert captured == ["PageQuery"]


def test_v2_dashboard_projection_uses_shared_service_and_escapes_html(monkeypatch):
    payload = {
        "target": "https://example.com/?q=<script>",
        "request": {"language": "ru"},
        "coverage": {"classification": "complete_within_scope", "urls_fetched": 1},
        "findings": [{"id": "f-1", "status": "warn", "summary": "safe <summary>"}],
    }
    captured = {}

    def fake_scan(request):
        captured["request"] = request
        return payload

    monkeypatch.setattr(server_module, "_run_v2_scan", fake_scan)
    response = server_module.audit_v2_dashboard_endpoint(
        server_module.V2AuditRequest(url="https://example.com", profile="quick", language="ru")
    )

    assert response.status_code == 200
    assert "&lt;script&gt;" in response.body.decode()
    assert "safe &lt;summary&gt;" in response.body.decode()
    assert '"id":"f-1"' in response.body.decode()
    assert captured["request"].profile == "quick"


def test_ai_tools_exposes_localized_builtin_skills(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module, "_SERVER_DATA_DIR", tmp_path)
    monkeypatch.setattr(server_module, "_require_loopback", lambda request: None)
    client = TestClient(app, base_url="http://127.0.0.1")
    response = client.get("/ai/tools", params={"language": "ru"})
    assert response.status_code == 200
    data = response.json()
    assert "seo-security-interpreter" in data["skills"]
    skill = next(item for item in data["skills_catalog"] if item["id"] == "seo-security-interpreter")
    assert skill["title"] == "Интерпретатор SEO-безопасности"
    assert skill["description"]


def test_ai_prompt_updates_preserve_other_language(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module, "_SERVER_DATA_DIR", tmp_path)
    monkeypatch.setattr(server_module, "_require_loopback", lambda request: None)
    client = TestClient(app, base_url="http://127.0.0.1")

    first = client.post(
        "/ai/prompts",
        json={"title": "English title", "prompt": "English prompt", "language": "en"},
    )
    assert first.status_code == 200
    prompt_id = first.json()["prompt"]["id"]
    second = client.post(
        "/ai/prompts",
        json={
            "id": prompt_id,
            "title": "Название",
            "prompt": "Русский промт",
            "language": "ru",
        },
    )
    assert second.status_code == 200
    assert second.json()["prompt"]["title"] == {"en": "English title", "ru": "Название"}
    assert second.json()["prompt"]["prompt"] == {"en": "English prompt", "ru": "Русский промт"}


def test_dashboard_is_localized_and_describes_each_operation():
    response = TestClient(app).get("/dashboard", params={"language": "ru"})
    assert response.status_code == 200
    assert "Настройка и запуск аудита сайта" in response.text
    assert "Запустить" in response.text
    assert "Запустить аудит готовности AI-агентов" not in response.text
    assert 'id="result" hidden' in response.text
    assert "#result { min-height:80px; background:#fff8f2" in response.text
    assert "background:#24130d; color:#ffe8d8; border-radius:12px; padding:18px" not in response.text
    assert 'id="result-panel" class="panel" hidden' in response.text
    assert 'class="operation-grid"' not in response.text
    assert 'class="cards"' not in response.text
    assert 'class="advanced-links"' in response.text
    assert 'class="text-link"' in response.text
    assert "loadChecks(false)" in response.text
    assert "function showResult()" in response.text
    assert "Проверки, включённые в запуск" in response.text
    assert "<details><summary>Проверки, включённые в запуск" in response.text
    assert 'id="ai-result" class="ai-report" hidden' in response.text
    assert response.text.count('id="ai-assistant-panel"') == 1
    assert response.text.index('id="result-panel"') < response.text.index('id="ai-assistant-panel"')
    assert 'id="ai-assistant-panel" class="panel ai-workspace" hidden' in response.text
    assert "function renderAiReport(data)" in response.text
    assert "Приоритетные рекомендации" in response.text
    assert "Данные аудита" in response.text
    assert "AI получает выбранные данные аудита и ваш необязательный запрос" in response.text
    assert 'translations[language.value].ai_generated_with_model' in response.text
    assert "Сгенерировано: agent-ready-tools" in response.text
    assert "function updateAiModeHint()" in response.text
    assert "function runAll()" in response.text
    assert 'if (preset === "all") { await runAll(); return; }' in response.text
    assert "combinedReportDocument" in response.text
    assert "geo.querySelectorAll(\"style\")" in response.text
    assert "seo.querySelectorAll(\"style\")" in response.text
    assert "<meta charset='utf-8>" not in response.text
    assert "checks:null" in response.text
    assert "AI-помощник обрабатывает запрос..." in response.text
    assert "function setAiBusy(busy)" in response.text
    assert 'id="threshold" type="text" inputmode="decimal" data-decimal' in response.text
    assert 'value="0.8"' in response.text
    assert "function decimalValue(id, fallback=0)" in response.text
    assert 'replace(/^(-?)\\./, "$10.")' in response.text
    assert "element.dataset.decimal !== undefined ? normalizeDecimalString(state[id])" in response.text
    assert 'input.inputMode = "decimal"' in response.text
    assert 'input_price_per_million:decimalValue("ai-provider-input-price")' in response.text
    assert 'role", "status"' in response.text
    assert "Скачать отчёт" in response.text
    assert "Распечатать отчёт" in response.text
    assert "URL.createObjectURL" in response.text
    assert "frame.contentWindow.print()" in response.text
    assert "reportFilename(" in response.text
    assert '"agentready-report-" + slug + ".html"' in response.text
    assert "Запустить SEO-аудит" in response.text
    assert "Обновить каталог проверок" in response.text
    assert "Проверить состояние сервиса" in response.text
    assert "Управляйте именованными AI-провайдерами" in response.text
    assert ">AI<" in response.text
    assert "Base URL OpenAI-compatible API" in response.text
    assert "Модель, выбранная для этого провайдера" in response.text
    assert "Скрывает в списках embedding-" in response.text
    assert "Включает помощника и loopback-only HTTP-транспорт" in response.text
    assert "Интерпретатор SEO-безопасности" in response.text
    assert "Аналитик аудита" in response.text
    assert ".model-control button { width:auto; flex:0 0 46px" in response.text
    assert "/ai/providers" in response.text
    assert "function activateAiProvider()" in response.text
    assert 'id="ai-provider-chat-only"' in response.text
    assert 'value="v2"' in response.text
    assert '/v2/audit/dashboard' in response.text
    assert "function toggleChatOnly()" in response.text
    assert "chat_only:document.getElementById(\"ai-provider-chat-only\").checked" in response.text
    assert 'id="ai-model"' in response.text
    assert "model:document.getElementById(\"ai-model\").value" in response.text
    assert "/v2/audit/dashboard" in response.text
    assert "/v2/seo/audit/dashboard" in response.text
    assert 'value="seo"' in response.text
    assert "progress-bar" in response.text
    assert "white-space:pre-line" in response.text
    assert "event.preventDefault()" in response.text
    assert 'id="help-toggle"' in response.text
    assert ">Справка<" in response.text
    assert 'id="help-content" class="panel help-content" hidden' in response.text
    assert "Скрыть справку" in response.text
    assert "Dashboard help toggled" in response.text
    assert "See Also" not in response.text
    assert "Back to README" not in response.text
    assert "dashboard-layout" in response.text
    assert "grid-template-columns:minmax(0,1fr) 0" in response.text
    assert ".dashboard-layout.help-open" in response.text
    assert "resize:horizontal" in response.text
    assert "max-width:50vw" in response.text
    assert response.text.count('id="help-toggle"') == 1
    assert response.text.index('id="language"') < response.text.index('id="help-toggle"')
    assert response.text.index('class="help-sidebar"') > response.text.index("<main class=\"dashboard-main\">")
    assert 'class="header-actions"' in response.text
    assert "body { width:100%; min-height:100vh; margin:0;" in response.text
    assert "max-width:1220px" not in response.text


def test_dashboard_uses_browser_locale_only_without_explicit_language():
    client = TestClient(app)
    russian = client.get("/dashboard", headers={"Accept-Language": "ru-RU,ru;q=0.9"})
    assert russian.status_code == 200
    assert '<html lang="ru">' in russian.text
    assert "Запустить аудит готовности AI-агентов" not in russian.text
    assert "const languageExplicit = new URLSearchParams(location.search).has(\"language\");" in russian.text
    assert "if (!languageExplicit && state.language" in russian.text

    english = client.get("/dashboard", headers={"Accept-Language": "de-DE,de;q=0.9"})
    assert english.status_code == 200
    assert '<html lang="en">' in english.text
    assert ">Help<" in english.text
    assert "Dashboard help" in english.text

    explicit_english = client.get("/dashboard", headers={"Accept-Language": "ru-RU"}, params={"language": "en"})
    assert explicit_english.status_code == 200
    assert '<html lang="en">' in explicit_english.text
    assert ">Execute<" in explicit_english.text
    assert ">Help<" in explicit_english.text

    explicit_russian = client.get("/dashboard", headers={"Accept-Language": "en-US"}, params={"language": "ru"})
    assert explicit_russian.status_code == 200
    assert '<html lang="ru">' in explicit_russian.text
    assert ">Запустить<" in explicit_russian.text
    assert ">Справка<" in explicit_russian.text


def test_dashboard_refreshes_provider_models_and_clears_new_provider_catalog():
    response = TestClient(app).get("/dashboard", params={"language": "ru"})
    assert response.status_code == 200
    assert 'id="ai-provider-model-refresh"' in response.text
    assert "function refreshAiModels()" in response.text
    assert "renderModelCatalog([], null)" in response.text
    assert "loadAiModels(provider.id, restoredDashboardState[\"ai-model\"] || provider.model)" in response.text
    assert 'id="ai-chat-provider"' in response.text
    assert "agentready.dashboard.state.v2" in response.text
    assert "localStorage.setItem" in response.text
    assert "provider-spin" in response.text
    assert 'id="ai-skill"' in response.text
    assert 'id="ai-mcp-tool"' in response.text
    assert 'id="ai-attachments"' in response.text
    assert ".docx" in response.text
    assert "clipboardData.files" in response.text
    assert "aiConversationHistory" in response.text
    assert "mcp_tools:selectedValues" in response.text
    assert "let aiPromptEditingId = null" in response.text
    assert "id:aiPromptEditingId" in response.text
    assert "language:language.value" in response.text
    assert '<textarea id="ai-message" placeholder=' in response.text
    assert 'id="ai-retry-button"' in response.text
    assert "function exportChat()" in response.text
    assert "function startNewChat()" in response.text
    assert "const controller = `<script>" in response.text
    assert "const controller = \"<script>" not in response.text


def test_dashboard_inline_script_does_not_close_html_script_early():
    """Regression: a literal closing script tag breaks the dashboard parser."""
    response = TestClient(app).get("/dashboard", params={"language": "en"})
    assert response.status_code == 200
    assert 'reportText.indexOf("<" + "/script>", start)' in response.text
    assert 'reportText.indexOf("</script>", start)' not in response.text


def test_v2_robots_source_endpoint_returns_session_document_without_leaking_unknown_runs():
    _V2_ROBOTS["robots-test"] = "User-agent: *\nDisallow: /private\n"
    client = TestClient(app)
    response = client.get("/v2/runs/robots-test/robots/source")
    assert response.status_code == 200
    assert response.json() == {
        "run_id": "robots-test",
        "found": True,
        "robots": "User-agent: *\nDisallow: /private\n",
    }
    missing = client.get("/v2/runs/missing-robots/robots/source")
    assert missing.status_code == 404
    _V2_ROBOTS.pop("robots-test", None)


def test_dashboard_project_history_checks_project_list_response():
    response = TestClient(app).get("/dashboard", params={"language": "en"})
    assert response.status_code == 200
    assert 'const projectsResponse = await fetch("/v2/projects")' in response.text
    assert "if (!projectsResponse.ok)" in response.text
    assert "if (!Array.isArray(projectsPayload))" in response.text


def test_dashboard_state_round_trips_bounded_tool_controls():
    client = TestClient(app)
    payload = {
        "robots-live": "User-agent: *\nAllow: /",
        "robots-proposed": "User-agent: *\nDisallow: /private",
        "robots-user-agents": "Googlebot, *",
        "sitemap-reconciliation-origin": "https://example.test",
        "sitemap-reconciliation-xml": "<urlset></urlset>",
        "custom-rules-document": "version: 1\nrules: []",
        "link-graph-dead-end": True,
        "link-graph-disconnected": False,
        "duplicate-clusters-kind": "near",
        "project-id": "demo",
        "project-name": "Demo",
        "credential": "must-not-persist",
    }
    saved = client.put("/dashboard/state", json=payload)
    assert saved.status_code == 200
    assert saved.json()["state"]["link-graph-dead-end"] is True
    assert "credential" not in saved.json()["state"]
    restored = client.get("/dashboard/state")
    assert restored.status_code == 200
    assert restored.json()["state"]["duplicate-clusters-kind"] == "near"
    assert "credential" not in restored.json()["state"]


def test_dashboard_project_history_uses_explanatory_localized_headers():
    english = TestClient(app).get("/dashboard", params={"language": "en"}).text
    russian = TestClient(app).get("/dashboard", params={"language": "ru"}).text
    assert 'history_run' in english and 'history_trigger' in english and 'history_baseline' in english
    assert "Audit run" in english and "Started by" in english
    assert "Запуск аудита" in russian and "Источник запуска" in russian
    assert "Started by shows what created each audit" in english
    assert "«Источник запуска» показывает" in russian


def test_dashboard_hints_use_hover_tooltips_like_reports():
    """All dashboard hints use the report-style hover tooltip, not click popovers."""
    for language in ("en", "ru"):
        response = TestClient(app).get("/dashboard", params={"language": language})
        assert response.status_code == 200
        # New hover-tooltip pattern (same as report files)
        assert "class='hint'" in response.text
        assert "data-tooltip=" in response.text
        assert ".hint:hover::after" in response.text
        assert ".hint:focus::after" in response.text
        assert "content:attr(data-tooltip)" in response.text
        # Old click-popover pattern is fully removed
        assert "hint-popover" not in response.text
        assert "static-hint-button" not in response.text
        assert "bindStaticHints" not in response.text
        assert "data-hint-target" not in response.text


def test_dashboard_offers_mobile_profile_with_localized_hint_and_debug_gate():
    response = TestClient(app).get("/dashboard", params={"language": "ru"})
    assert response.status_code == 200
    # 1.1 mobile audit profile is selectable and routed to the mobile endpoints
    assert 'value="mobile"' in response.text
    assert "Мобильная дружественность" in response.text
    assert "/mobile/checks" in response.text
    assert "/v2/mobile/audit/dashboard" in response.text
    assert "runMobile()" in response.text
    # 1.2 selected profile purpose is exposed only via the (?) hover tooltip
    assert 'id="preset-desc"' not in response.text
    assert "Что проверяет выбранный профиль аудита" in response.text
    assert "profile_mobile" in response.text
    assert "updatePresetHint()" in response.text
    assert "label[for='preset'] .hint" in response.text
    # 1.3 raw JSON responses are gated behind the debug flag
    assert 'id="debug"' in response.text
    assert "Отладка результатов" in response.text
    assert "debugMode()" in response.text
    assert "Каталог проверок обновлён." in response.text
    assert "Сервис работает" in response.text or "сервис аудита работает" in response.text.lower()


def test_dashboard_english_locale_has_mobile_profile_texts():
    response = TestClient(app).get("/dashboard", params={"language": "en"})
    assert response.status_code == 200
    assert ">Execute<" in response.text
    assert "Mobile-friendliness" in response.text
    assert "Debug results" in response.text
    assert "What the selected audit profile checks" in response.text


def test_ai_provider_profiles_are_selectable_and_shared(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("agentready.ai_credentials.store_api_key", lambda *args, **kwargs: None)
    monkeypatch.setattr("agentready.ai_credentials.clear_api_key", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "agentready.ai_credentials.api_key_status",
        lambda credential_id: {"configured": True, "source": "keyring", "credential_id": credential_id},
    )
    monkeypatch.setattr(server_module, "_require_loopback", lambda request: None)
    client = TestClient(app, base_url="http://127.0.0.1")
    saved = client.post(
        "/ai/providers",
        json={
            "name": "Local gateway",
            "base_url": "http://127.0.0.1:8080/v1",
            "api_key": "secret-key",
            "active": True,
        },
    )
    assert saved.status_code == 400
    # Loopback HTTP is rejected until explicitly enabled in trusted config.
    saved = client.post(
        "/ai/providers",
        json={
            "name": "Gateway",
            "base_url": "https://gateway.example/v1",
            "api_key": "secret-key",
            "active": True,
            "enable_ai": True,
            "chat_only": True,
            "input_price_per_million": 1.25,
            "output_price_per_million": 4.5,
        },
    )
    assert saved.status_code == 200
    status = client.get("/ai/status")
    assert status.status_code == 200
    assert status.json()["active_provider"] == "gateway"
    assert status.json()["enabled"] is True
    assert status.json()["transport_enabled"] is True
    assert status.json()["timeout_seconds"] >= 1
    assert status.json()["max_retries"] >= 0
    assert status.json()["context_limit"] >= 1000
    gateway = next(item for item in status.json()["providers"] if item["id"] == "gateway")
    assert gateway["credential"]["configured"] is True
    assert gateway["chat_only"] is True
    assert gateway["input_price_per_million"] == 1.25
    assert gateway["output_price_per_million"] == 4.5
    assert client.post("/ai/providers/active", json={"provider_id": "openai"}).status_code == 200
    assert client.get("/ai/status").json()["active_provider"] == "openai"


def test_ai_provider_model_catalog_is_available_without_exposing_credentials(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("agentready.ai_credentials.store_api_key", lambda *args, **kwargs: None)
    monkeypatch.setattr("agentready.ai_credentials.api_key_status", lambda credential_id: {"configured": True})
    monkeypatch.setattr(server_module, "_require_loopback", lambda request: None)

    async def fake_list_models(self):
        return [ProviderModel("embed-small", ("embedding",)), ProviderModel("chat-model", ("chat",))]

    monkeypatch.setattr("agentready.ai_provider.OpenAICompatibleProvider.list_models", fake_list_models)
    client = TestClient(app, base_url="http://127.0.0.1")
    saved = client.post("/ai/providers", json={
        "name": "Catalog gateway",
        "base_url": "https://gateway.example/v1",
        "api_key": "secret-key",
        "model": "chat-model",
        "input_price_per_million": 1.25,
        "output_price_per_million": 4.5,
        "active": True,
    })
    assert saved.status_code == 200
    response = client.get("/ai/providers/catalog-gateway/models")
    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_model"] == "chat-model"
    assert [item["id"] for item in payload["models"]] == ["embed-small", "chat-model"]
    assert "secret-key" not in response.text


def test_every_dashboard_element_has_a_localized_hint():
    expected = ["url_hint", "language_hint", "run_hint", "checks_hint", "select_all_hint", "clear_checks_hint", "download_hint", "print_hint"]
    for language in ("ru", "en"):
        response = TestClient(app).get("/dashboard", params={"language": language})
        assert response.status_code == 200
        # Every hint key must have a non-empty localized text in the translations payload
        for key in expected:
            assert f'"{key}":' in response.text, f"{key} missing for {language}"
    ru = TestClient(app).get("/dashboard", params={"language": "ru"}).text
    assert "Публичный URL сайта для аудита" in ru
    assert "Переключает язык интерфейса дашборда" in ru
    assert "Сохраняет сформированный HTML-отчёт" in ru


def test_checks_endpoint_supports_localized_catalog():
    response = TestClient(app).get("/checks", params={"language": "ru"})
    assert response.status_code == 200
    payload = response.json()
    assert payload and all(item["language"] == "ru" for item in payload)
    assert {"all", "content", "api", "ai-search"} <= set(payload[0]["presets"])
    assert all(item["description"] for item in payload)
    assert all(item["hint"] for item in payload)
    robots = next(item for item in payload if item["id"] == "robots-txt")
    assert "robots.txt" in robots["hint"]
    robots = next(item for item in payload if item["id"] == "robots-txt")
    assert "Опубликуйте" in robots["description"]


def test_seo_checks_endpoint_returns_localized_descriptions():
    response = TestClient(app).get("/seo/checks", params={"language": "ru"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 29
    assert all(item["language"] == "ru" and item["description"] for item in payload)
    assert all(item["hint"] for item in payload)
    assert any(item["id"] == "jsonld" and "JSON-LD" in item["description"] for item in payload)
    insecure_pages = next(item for item in payload if item["id"] == "insecure-links-pages")
    assert "включённом обходе" in insecure_pages["hint"]


def test_seo_audit_endpoints_execute(monkeypatch):
    """Regression: canonical v2 SEO routes call the defined SEO runner."""
    from agentready.seo_models import SeoCategoryScore, SeoCheckResult, SeoReport

    report = SeoReport(
        schema="agentready.seo.v2",
        target="https://example.com/",
        origin="https://example.com",
        checks=[SeoCheckResult("page-metadata", "t", "metadata", "pass", True, "ok")],
        score=100,
        categories=[SeoCategoryScore("metadata", 1, 1, 100)],
        recommendations=[],
        started_at="now",
        finished_at="now",
    )
    monkeypatch.setattr(server_module, "audit_seo", lambda *args, **kwargs: report)
    assert hasattr(server_module, "_run_seo")

    client = TestClient(app)
    json_response = client.post("/v2/seo/audit", json={"url": "https://example.com"})
    assert json_response.status_code == 200
    assert json_response.json()["schema"] == "agentready.seo.v2"

    html_response = client.post("/v2/seo/audit/dashboard", json={"url": "https://example.com"})
    assert html_response.status_code == 200
    assert "SEO" in html_response.text


def test_seo_endpoint_preserves_crawl_profile_and_budget(monkeypatch):
    captured = {}

    def fake_audit(*args, **kwargs):
        captured.update(kwargs)
        from agentready.seo_models import SeoCategoryScore, SeoCheckResult, SeoReport

        return SeoReport(
            schema="agentready.seo.v2", target=args[0], origin="https://example.com",
            checks=[SeoCheckResult("page-metadata", "t", "metadata", "pass", True, "ok")],
            score=100, categories=[SeoCategoryScore("metadata", 1, 1, 100)],
            recommendations=[], started_at="now", finished_at="now",
        )

    monkeypatch.setattr(server_module, "audit_seo", fake_audit)
    response = TestClient(app).post(
        "/v2/seo/audit",
        json={"url": "https://example.com", "profile": "deep", "crawl": True, "max_pages": 9},
    )
    assert response.status_code == 200
    assert captured["profile"] == "deep"
    assert captured["crawl"] is True
    assert captured["max_pages"] == 9


def test_seo_audit_accepts_crawl_check_ids(monkeypatch):
    """Regression: dashboard sends crawl check IDs from /seo/checks; they must not 400."""
    from agentready.seo_models import SeoCategoryScore, SeoCheckResult, SeoReport

    captured: dict = {}

    def fake_audit(url, **kwargs):
        captured.update(kwargs)
        return SeoReport(
        schema="agentready.seo.v2",
            target=url,
            origin="https://example.com",
            checks=[SeoCheckResult("page-metadata", "t", "metadata", "pass", True, "ok")],
            score=100,
            categories=[SeoCategoryScore("metadata", 1, 1, 100)],
            recommendations=[],
            started_at="now",
            finished_at="now",
        )

    monkeypatch.setattr(server_module, "audit_seo", fake_audit)
    client = TestClient(app)
    response = client.post(
        "/v2/seo/audit/dashboard",
        json={"url": "https://example.com", "checks": ["page-metadata", "broken-links", "duplicate-metadata"]},
    )
    assert response.status_code == 200
    assert captured["crawl"] is True
    assert captured["crawl_checks"] is not None and len(captured["crawl_checks"]) == 2
    assert captured["checks"] is not None and len(captured["checks"]) == 1

    unknown = client.post("/v2/seo/audit", json={"url": "https://example.com", "checks": ["bogus-id"]})
    assert unknown.status_code == 400
