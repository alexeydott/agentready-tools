import builtins
import json
import logging

import httpx
import pytest

from agentready import google_indexing, indexnow
from agentready.cli import main
from agentready.google_indexing import GoogleIndexingError, get_metadata, publish_urls
from agentready.indexnow import (
    IndexNowError,
    build_payload,
    resolve_endpoint,
    submit_urls,
)
from agentready.structured_data import (
    extract_jsonld_nodes,
    google_indexing_eligible_types,
)


class FakeGoogleResponse:
    def __init__(self, status_code, payload=None, *, headers=None):
        self.status_code = status_code
        self.text = json.dumps(payload) if payload is not None else ""
        self.headers = headers or {}


class FakeGoogleSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.posts = []
        self.gets = []

    def post(self, endpoint, *, json, timeout):
        self.posts.append((endpoint, json, timeout))
        return self.responses.pop(0)

    def get(self, endpoint, *, params, timeout):
        self.gets.append((endpoint, params, timeout))
        return self.responses.pop(0)


def test_google_eligibility_detects_supported_jsonld_graphs():
    html = """
    <script type="application/ld+json">
    {
      "@graph": [
        {"@id": "#job", "@type": "JobPosting"},
        {"@id": "#event", "@type": "BroadcastEvent"},
        {"@type": "VideoObject", "publication": {"@id": "#event"}}
      ]
    }
    </script>
    """
    nodes, errors, blocks = extract_jsonld_nodes(html)
    assert errors == []
    assert blocks == 1
    assert google_indexing_eligible_types(nodes) == {"job-posting", "broadcast-event"}


def test_google_eligibility_requires_broadcast_event_inside_video_object():
    html = '<script type="application/ld+json">{"@type":"BroadcastEvent"}</script>'
    nodes, errors, _ = extract_jsonld_nodes(html)
    assert errors == []
    assert google_indexing_eligible_types(nodes) == set()


def test_indexnow_resolves_yandex_and_rejects_ambiguous_endpoint():
    assert resolve_endpoint(provider="yandex") == "https://yandex.com/indexnow"
    with pytest.raises(IndexNowError, match="either a named"):
        resolve_endpoint(provider="yandex", endpoint="https://example.com/indexnow")


def test_indexnow_key_location_enforces_host_and_path_scope():
    payload = build_payload(
        ["https://example.com/docs/a", "https://example.com/docs/b"],
        "12345678",
        key_location="https://example.com/docs/key.txt",
    )
    assert payload["keyLocation"] == "https://example.com/docs/key.txt"
    with pytest.raises(IndexNowError, match="outside its scope"):
        build_payload(
            ["https://example.com/other/a"],
            "12345678",
            key_location="https://example.com/docs/key.txt",
        )
    with pytest.raises(IndexNowError, match="submitted URL host"):
        build_payload(
            ["https://example.com/docs/a"],
            "12345678",
            key_location="https://other.example/docs/key.txt",
        )


@pytest.mark.parametrize(("status_code", "accepted"), [(200, True), (202, True), (422, False)])
def test_indexnow_uses_status_codes_without_requiring_json(monkeypatch, status_code, accepted):
    response = httpx.Response(status_code, text="", request=httpx.Request("POST", "https://yandex.com/indexnow"))
    monkeypatch.setattr(indexnow.httpx, "post", lambda *args, **kwargs: response)
    result = submit_urls(["https://example.com/a"], "12345678", provider="yandex")
    assert result.status_code == status_code
    assert result.accepted is accepted


def test_indexnow_logs_do_not_include_key(monkeypatch, caplog):
    response = httpx.Response(200, text="", request=httpx.Request("POST", "https://api.indexnow.org/indexnow"))
    monkeypatch.setattr(indexnow.httpx, "post", lambda *args, **kwargs: response)
    caplog.set_level(logging.DEBUG)
    submit_urls(["https://example.com/a"], "secret-key-123")
    assert "secret-key-123" not in caplog.text


def test_google_update_dry_run_uses_live_eligibility():
    inspected = []

    def inspect(url, **kwargs):
        inspected.append((url, kwargs))
        return {"job-posting"}

    result = publish_urls(
        ["https://example.com/jobs/1"],
        dry_run=True,
        eligibility_inspector=inspect,
    )
    assert inspected[0][0] == "https://example.com/jobs/1"
    assert result.dry_run is True
    assert result.results[0].eligible_type == "job-posting"


def test_google_mixed_preflight_failures_return_per_url_results():
    """A batch with one eligible and one ineligible URL must return typed per-URL outcomes, not raise."""
    calls = []

    def inspect(url, **kwargs):
        calls.append(url)
        if url.endswith("/unsupported"):
            raise GoogleIndexingError("no eligible structured data found")
        return {"job-posting"}

    result = publish_urls(
        ["https://example.com/jobs/1", "https://example.com/unsupported"],
        dry_run=True,
        eligibility_inspector=inspect,
    )
    assert len(calls) == 2
    assert result.failed_count == 1
    assert result.results[0].error is None
    assert result.results[0].eligible_type == "job-posting"
    assert result.results[1].error is not None
    assert "no eligible structured data" in result.results[1].error


def test_google_delete_requires_explicit_eligible_type():
    with pytest.raises(GoogleIndexingError, match="requires --eligible-type"):
        publish_urls(
            ["https://example.com/jobs/1"],
            notification_type="URL_DELETED",
            dry_run=True,
        )


def test_google_notification_guard_defaults_to_documented_quota():
    urls = [f"https://example.com/jobs/{index}" for index in range(201)]
    with pytest.raises(GoogleIndexingError, match="max_notifications is 200"):
        publish_urls(
            urls,
            notification_type="URL_DELETED",
            eligible_type="job-posting",
            dry_run=True,
        )


def test_google_retries_transient_response_and_honors_retry_after():
    session = FakeGoogleSession(
        [
            FakeGoogleResponse(429, {"error": "rate limited"}, headers={"Retry-After": "3"}),
            FakeGoogleResponse(200, {"urlNotificationMetadata": {"url": "https://example.com/jobs/1"}}),
        ]
    )
    delays = []
    result = publish_urls(
        ["https://example.com/jobs/1"],
        notification_type="URL_DELETED",
        eligible_type="job-posting",
        session=session,
        sleeper=delays.append,
    )
    assert result.accepted_count == 1
    assert result.results[0].attempts == 2
    assert delays == [3.0]


def test_google_returns_per_url_partial_failures():
    session = FakeGoogleSession(
        [
            FakeGoogleResponse(200, {"ok": True}),
            FakeGoogleResponse(403, {"error": {"status": "PERMISSION_DENIED"}}),
        ]
    )
    result = publish_urls(
        ["https://example.com/jobs/1", "https://example.com/jobs/2"],
        notification_type="URL_DELETED",
        eligible_type="job-posting",
        session=session,
    )
    assert result.accepted_count == 1
    assert result.failed_count == 1
    assert result.results[1].status_code == 403


def test_google_metadata_distinguishes_found_and_missing():
    found = get_metadata(
        "https://example.com/jobs/1",
        session=FakeGoogleSession([FakeGoogleResponse(200, {"url": "https://example.com/jobs/1"})]),
    )
    missing = get_metadata(
        "https://example.com/jobs/2",
        session=FakeGoogleSession([FakeGoogleResponse(404)]),
    )
    assert found.found is True
    assert missing.found is False


def test_google_missing_optional_dependency_is_actionable(monkeypatch, tmp_path):
    credentials = tmp_path / "credentials.json"
    credentials.write_text("{}", encoding="utf-8")
    original_import = builtins.__import__

    def missing_google(name, *args, **kwargs):
        if name.startswith("google."):
            raise ImportError("google auth unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_google)
    with pytest.raises(GoogleIndexingError, match=r"agentready-tools\[google\]"):
        publish_urls(
            ["https://example.com/jobs/1"],
            notification_type="URL_DELETED",
            eligible_type="job-posting",
            credentials_path=credentials,
        )


def test_google_credential_failure_redacts_path(monkeypatch, tmp_path, caplog):
    secret_path = tmp_path / "customer-private-key.json"
    secret_path.write_text("{}", encoding="utf-8")

    class BadCredentials:
        @classmethod
        def from_service_account_file(cls, path, scopes):
            raise ValueError(f"bad credential at {path}")

    monkeypatch.setattr(
        google_indexing,
        "_load_google_dependencies",
        lambda: (BadCredentials, object, ()),
    )
    caplog.set_level(logging.DEBUG)
    with pytest.raises(GoogleIndexingError) as exc_info:
        publish_urls(
            ["https://example.com/jobs/1"],
            notification_type="URL_DELETED",
            eligible_type="job-posting",
            credentials_path=secret_path,
        )
    assert str(secret_path) not in str(exc_info.value)
    assert str(secret_path) not in caplog.text


def test_google_cli_is_dry_run_by_default(capsys):
    exit_code = main(
        [
            "google-indexing",
            "publish",
            "https://example.com/jobs/1",
            "--type",
            "deleted",
            "--eligible-type",
            "job-posting",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["send"] is False
    assert payload["dry_run"] is True


def test_indexnow_cli_rejects_provider_endpoint_conflict(capsys):
    exit_code = main(
        [
            "indexnow",
            "submit",
            "https://example.com/a",
            "--key",
            "12345678",
            "--provider",
            "yandex",
            "--endpoint",
            "https://example.com/indexnow",
            "--dry-run",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "either a named IndexNow provider or an explicit endpoint" in captured.err


def test_google_inspect_url_eligibility_rejects_non_public_targets(monkeypatch):
    """inspect_url_eligibility must reject loopback / private targets, not just the initial URL."""
    from agentready import http as http_module
    from agentready.google_indexing import GoogleIndexingError, inspect_url_eligibility

    class _PrivateRedirectClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get(self, url, **kwargs):
            from agentready.target import TargetError
            raise TargetError("resolves to non-public IP address(es): 127.0.0.1")

    monkeypatch.setattr(http_module, "HttpClient", _PrivateRedirectClient)
    with pytest.raises(GoogleIndexingError, match="eligibility preflight"):
        inspect_url_eligibility("https://example.com/jobs/1")


def test_google_inspect_url_eligibility_enforces_response_size_limit(monkeypatch):
    """inspect_url_eligibility must raise when the response exceeds the byte cap."""
    from agentready import http as http_module
    from agentready.google_indexing import GoogleIndexingError, inspect_url_eligibility

    class _OversizedClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get(self, url, **kwargs):
            from agentready.http import FetchError
            raise FetchError("Response exceeds 5242880 byte limit")

    monkeypatch.setattr(http_module, "HttpClient", _OversizedClient)
    with pytest.raises(GoogleIndexingError, match="eligibility preflight"):
        inspect_url_eligibility("https://example.com/jobs/1")


def test_google_mixed_preflight_failures_in_live_path():
    """A batch with one preflight failure and one success must return per-URL results, not raise."""

    def inspect(url, **kwargs):
        if url.endswith("/bad"):
            raise GoogleIndexingError("unsupported content type")
        return {"job-posting"}

    session = FakeGoogleSession([FakeGoogleResponse(200, {"urlNotificationMetadata": {}})])
    result = publish_urls(
        ["https://example.com/jobs/good", "https://example.com/jobs/bad"],
        session=session,
        eligibility_inspector=inspect,
    )
    assert len(result.results) == 2
    good = next(r for r in result.results if r.url.endswith("/good"))
    bad = next(r for r in result.results if r.url.endswith("/bad"))
    assert good.accepted is True
    assert bad.accepted is False
    assert bad.error is not None
    assert "unsupported content type" in bad.error


def test_google_dry_run_counts_preflight_errors():
    result = publish_urls(
        ["https://example.com/jobs/bad"],
        dry_run=True,
        eligibility_inspector=lambda url, **kwargs: (_ for _ in ()).throw(
            GoogleIndexingError("unsupported content type")
        ),
    )
    assert result.failed_count == 1


def test_google_cli_returns_failure_for_dry_run_preflight_error(monkeypatch, capsys):
    def fail_preflight(url, **kwargs):
        raise GoogleIndexingError("unsupported content type")

    monkeypatch.setattr(
        "agentready.cli.publish_google_urls",
        lambda *args, **kwargs: publish_urls(
            args[0],
            dry_run=True,
            eligibility_inspector=fail_preflight,
        ),
    )
    exit_code = main(
        [
            "google-indexing",
            "publish",
            "https://example.com/jobs/bad",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["failed_count"] == 1
