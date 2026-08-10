import json

import pytest

from agentready import credentials as creds
from agentready.seo_analytics import (
    ANALYTICS_CHECK_METADATA,
    AnalyticsContext,
    check_ga_bounce_rate,
    check_ga_no_traffic,
    check_gsc_no_clicks,
    check_gsc_no_impressions,
)

URL = "https://example.com/page"


def test_credentials_store_roundtrip(monkeypatch, tmp_path):
    vault: dict[tuple[str, str], str] = {}

    class FakeKeyring:
        @staticmethod
        def set_password(service, key, value):
            vault[(service, key)] = value

        @staticmethod
        def get_password(service, key):
            return vault.get((service, key))

        @staticmethod
        def delete_password(service, key):
            vault.pop((service, key), None)

    monkeypatch.setitem(__import__("sys").modules, "keyring", FakeKeyring)
    sa = tmp_path / "sa.json"
    sa.write_text(json.dumps({"type": "service_account", "client_email": "bot@example.iam.gserviceaccount.com"}), encoding="utf-8")

    creds.store_service_account(str(sa))
    info = creds.load_service_account_info()
    assert info and info["client_email"] == "bot@example.iam.gserviceaccount.com"
    status = creds.credential_status()
    assert status["configured"] is True and status["source"] == "keyring"
    assert creds.clear_service_account() is True
    assert creds.load_service_account_info() is None


def test_credentials_reject_invalid_json(monkeypatch, tmp_path):
    monkeypatch.setitem(__import__("sys").modules, "keyring", type("K", (), {"set_password": lambda *a: None})())
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"type": "authorized_user"}), encoding="utf-8")
    with pytest.raises(creds.CredentialsError, match="service_account"):
        creds.store_service_account(str(bad))


def test_analytics_checks_skip_without_configuration():
    ctx = AnalyticsContext()
    assert check_ga_no_traffic(URL, ctx).status == "skip"
    assert check_ga_bounce_rate(URL, ctx).status == "skip"
    assert check_gsc_no_clicks(URL, ctx).status == "skip"
    assert check_gsc_no_impressions(URL, ctx).status == "skip"


def test_ga_no_traffic_flags_zero_session_page(monkeypatch):
    import agentready.ga_gsc as ga

    monkeypatch.setattr(ga, "ga_bounce_rate", lambda prop, page: None)
    monkeypatch.setitem(__import__("sys").modules, "agentready.ga_gsc", ga)
    ctx = AnalyticsContext(ga_property="12345")
    result = check_ga_no_traffic(URL, ctx)
    assert result.status == "fail" and result.remediation


def test_ga_bounce_rate_threshold(monkeypatch):
    import agentready.ga_gsc as ga

    monkeypatch.setattr(ga, "ga_bounce_rate", lambda prop, page: 0.95)
    monkeypatch.setitem(__import__("sys").modules, "agentready.ga_gsc", ga)
    ctx = AnalyticsContext(ga_property="12345")
    assert check_ga_bounce_rate(URL, ctx).status == "warn"
    monkeypatch.setattr(ga, "ga_bounce_rate", lambda prop, page: 0.4)
    assert check_ga_bounce_rate(URL, ctx).status == "pass"


def test_gsc_no_clicks_and_impressions(monkeypatch):
    import agentready.ga_gsc as ga

    monkeypatch.setattr(ga, "gsc_pages_without_clicks", lambda site: [{"page": URL, "impressions": 120, "clicks": 0}])
    monkeypatch.setattr(ga, "gsc_pages_without_impressions", lambda site: [])
    monkeypatch.setitem(__import__("sys").modules, "agentready.ga_gsc", ga)
    ctx = AnalyticsContext(gsc_site="https://example.com/")
    assert check_gsc_no_clicks(URL, ctx).status == "fail"
    assert check_gsc_no_impressions(URL, ctx).status == "fail"


def test_analytics_metadata_is_localized():
    assert len(ANALYTICS_CHECK_METADATA) == 6
    for item in ANALYTICS_CHECK_METADATA:
        assert item["title"]["en"] and item["title"]["ru"]
        assert item["category"]["en"] == "Analytics" and item["category"]["ru"] == "Аналитика"


def test_audit_seo_runs_analytics_checks_when_configured(monkeypatch):
    from agentready import seo_scanner

    monkeypatch.setattr("agentready.seo_scanner.parse_target", lambda url: type("T", (), {"url": url, "origin": "https://example.com"})())

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def get(self, url, **kw):
            raise RuntimeError("network must not be used in this test")

    monkeypatch.setattr("agentready.seo_scanner.HttpClient", FakeClient)
    monkeypatch.setattr("agentready.seo_scanner.score_checks", lambda checks: (0, []))
    monkeypatch.setattr("agentready.seo_scanner.rank_recommendations", lambda checks, limit=10: [])

    report = seo_scanner.audit_seo(URL, checks=[], ga_property="12345")
    analytics = [c for c in report.checks if c.category == "analytics"]
    assert len(analytics) == 6
    # GA checks run (error without real credentials is fine), GSC checks skip
    assert any(c.id == "ga-no-traffic" for c in analytics)
    assert any(c.id == "gsc-no-clicks" and c.status == "skip" for c in analytics)


def test_cli_credentials_commands(monkeypatch, capsys):
    from agentready import cli

    monkeypatch.setattr("agentready.credentials.credential_status", lambda: {"configured": False, "source": None, "client_email": None})
    args = type("Args", (), {"seo_command": "credentials", "action": "status", "path": None})()
    assert cli._cmd_seo(args) == 0
    out = capsys.readouterr().out
    assert '"configured": false' in out
