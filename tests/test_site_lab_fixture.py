from __future__ import annotations

import httpx

from tests.fixtures.site_lab import SiteLabServer


def test_site_lab_manifest_and_core_scenarios_are_deterministic():
    manifest = SiteLabServer.manifest()
    assert manifest["name"] == "agentready-site-lab"
    assert "/redirect-loop-a" in manifest["scenarios"]["redirects"]

    with SiteLabServer() as site:
        response = httpx.get(site.base_url + "/", timeout=2)
        assert response.status_code == 200
        assert "Site Lab" in response.text

        redirect = httpx.get(site.base_url + "/redirect", follow_redirects=False, timeout=2)
        assert redirect.status_code == 302
        assert redirect.headers["location"] == "/"

        assert httpx.get(site.base_url + "/missing", timeout=2).status_code == 404
        assert httpx.get(site.base_url + "/gone", timeout=2).status_code == 410
        assert httpx.get(site.base_url + "/error", timeout=2).status_code == 500


def test_site_lab_handles_auth_and_sensitive_values_are_not_logged():
    events: list[str] = []
    with SiteLabServer(request_logger=events.append) as site:
        unauthorized = httpx.get(site.base_url + "/auth", timeout=2)
        assert unauthorized.status_code == 401
        authorized = httpx.get(
            site.base_url + "/auth",
            auth=("fixture", "secret"),
            timeout=2,
        )
        assert authorized.status_code == 200
        assert any("GET /auth" in event for event in events)
        assert all("secret" not in event for event in events)
