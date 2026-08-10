import asyncio
import ipaddress

import httpx
import pytest

from agentready.egress import EgressPolicy, EgressPolicyError
from agentready.fetcher import FetchError, FetchErrorKind, FetchRequest, Fetcher
from agentready.security import SecretRedactor


def test_egress_policy_rejects_credentials_and_sensitive_headers():
    policy = EgressPolicy(block_private=True)
    with pytest.raises(EgressPolicyError, match="credential-bearing URL"):
        policy.validate_request("https://user:pass@example.com/")
    with pytest.raises(EgressPolicyError, match="credential-bearing headers"):
        policy.validate_headers({"Authorization": "Bearer secret"})


def test_secret_redactor_removes_bearer_and_nested_secret_values():
    redactor = SecretRedactor()
    value = redactor.mapping({"Authorization": "Bearer secret", "nested": {"api_key": "secret"}})
    assert value == {"Authorization": "[REDACTED]", "nested": {"api_key": "[REDACTED]"}}
    assert "secret" not in redactor.text("Authorization: Bearer secret")



def test_fetcher_revalidates_redirects_and_preserves_chain():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"}, request=request)
        return httpx.Response(200, content=b"ok", request=request)

    async def run() -> object:
        transport = httpx.MockTransport(handler)
        async with Fetcher(transport=transport, policy=EgressPolicy(max_redirects=2)) as fetcher:
            return await fetcher.get(FetchRequest("https://example.com/start", purpose="test"))

    result = asyncio.run(run())
    assert result.body == b"ok"
    assert result.redirects == ("https://example.com/start",)
    assert result.redirect_records[0].status_code == 302
    assert not result.redirect_records[0].cross_origin



def test_fetcher_enforces_response_limit():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"012345", request=request)

    async def run() -> None:
        async with Fetcher(
            transport=httpx.MockTransport(handler),
            policy=EgressPolicy(max_response_bytes=4),
        ) as fetcher:
            with pytest.raises(FetchError, match="Response exceeds"):
                await fetcher.get(FetchRequest("https://example.com/large", purpose="test"))

    asyncio.run(run())


def test_egress_policy_rejects_private_resolver_results():
    policy = EgressPolicy(
        block_private=True,
        resolver=lambda _host, _port: [ipaddress.ip_address("127.0.0.1")],
    )
    with pytest.raises(EgressPolicyError, match="non-public"):
        policy.validate_request("https://example.com/")


def test_browser_subresources_use_the_same_egress_policy():
    policy = EgressPolicy(block_private=False, allowed_origins=frozenset({"https://example.com"}))
    policy.validate_browser_request("https://example.com/script.js", resource_type="script")
    with pytest.raises(EgressPolicyError, match="allowlist"):
        policy.validate_browser_request("https://cdn.example.net/script.js", resource_type="script")


def test_fetcher_run_deduplicates_by_purpose_and_headers():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=str(calls).encode(), request=request)

    async def run() -> tuple[object, object]:
        async with Fetcher(transport=httpx.MockTransport(handler)) as fetcher:
            first = await fetcher.get(FetchRequest("https://example.com/", purpose="html"))
            second = await fetcher.get(FetchRequest("https://example.com/", purpose="markdown"))
            return first, second

    first, second = asyncio.run(run())
    assert calls == 2
    assert first.body == b"1"
    assert second.body == b"2"


def test_fetcher_retries_only_safe_transient_responses():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        headers = {"retry-after": "1"} if calls == 1 else {}
        return httpx.Response(503 if calls == 1 else 200, headers=headers, request=request)

    async def run() -> object:
        async with Fetcher(
            transport=httpx.MockTransport(handler),
            max_retries=1,
        ) as fetcher:
            return await fetcher.get(FetchRequest("https://example.com/"))

    result = asyncio.run(run())
    assert calls == 2
    assert result.status_code == 200
    assert result.retry_after is None


def test_fetcher_classifies_response_limit_errors():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"012345", request=request)

    async def run() -> None:
        async with Fetcher(
            transport=httpx.MockTransport(handler),
            policy=EgressPolicy(max_response_bytes=4),
        ) as fetcher:
            with pytest.raises(FetchError) as error:
                await fetcher.get(FetchRequest("https://example.com/large", purpose="test"))
            assert error.value.kind == FetchErrorKind.RESPONSE_TOO_LARGE

    asyncio.run(run())
