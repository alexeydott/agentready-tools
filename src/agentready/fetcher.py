"""Async per-run Fetcher with bounded, policy-controlled HTTP access."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, Self
from urllib.parse import urljoin, urlsplit

import httpx

from .egress import (
    EgressPolicy,
    EgressPolicyError,
    PassivePublicContext,
    TrustedLocalCredentialContext,
)
from .security import SecretRedactor

logger = logging.getLogger(__name__)
_REDIRECTS = {301, 302, 303, 307, 308}


class FetchTransport(Protocol):
    """Minimal async transport accepted by the Fetcher boundary."""

    async def handle_async_request(self, request: Any) -> Any:
        """Send one request through an async HTTP transport."""


class FetchErrorKind(StrEnum):
    DNS = "dns"
    CONNECT = "connect"
    TIMEOUT = "timeout"
    TLS = "tls"
    PROTOCOL = "protocol"
    RESPONSE_TOO_LARGE = "response-too-large"
    INVALID_REDIRECT = "invalid-redirect"
    REDIRECT_LOOP = "redirect-loop"
    TOO_MANY_REDIRECTS = "too-many-redirects"
    BLOCKED_BY_POLICY = "blocked-by-policy"


@dataclass(frozen=True, slots=True)
class FetchRequest:
    url: str
    method: str = "GET"
    purpose: str = "audit"
    run_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    credential_context: str | None = None
    security_context: PassivePublicContext | TrustedLocalCredentialContext | None = None
    cache_mode: str = "run-deduplicate"


@dataclass(frozen=True, slots=True)
class RedirectHop:
    from_url: str
    status_code: int
    location_raw: str
    to_url: str | None
    cross_origin: bool
    downgrade_https_to_http: bool


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    redirects: tuple[str, ...]
    elapsed_ms: int
    retry_after: str | None = None
    redirect_records: tuple[RedirectHop, ...] = ()


class FetchError(RuntimeError):
    """Typed failure at the bounded fetch boundary."""

    def __init__(self, message: str, *, kind: FetchErrorKind = FetchErrorKind.PROTOCOL) -> None:
        super().__init__(message)
        self.kind = kind


class FetcherBoundary(Protocol):
    """Network collection contract exposed to crawler orchestration."""

    async def __aenter__(self) -> Self:
        ...

    async def __aexit__(self, *_: object) -> None:
        ...

    async def get(self, request: FetchRequest, *, use_cache: bool = True) -> FetchResult:
        ...


FetcherFactory = Callable[..., FetcherBoundary]


class Fetcher:
    def __init__(
        self,
        *,
        policy: EgressPolicy | None = None,
        timeout: float = 5.0,
        verify: bool = True,
        transport: FetchTransport | None = None,
        max_retries: int = 0,
        retry_backoff: float = 0.0,
    ) -> None:
        self.policy = policy or EgressPolicy()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            verify=verify,
            follow_redirects=False,
            transport=transport,
        )
        if max_retries < 0 or retry_backoff < 0:
            raise ValueError("retry settings must not be negative")
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._redactor = SecretRedactor()
        self._run_dedup: dict[
            tuple[str, str, tuple[tuple[str, str], ...], str, str | None],
            FetchResult,
        ] = {}
        logger.debug("[WP2.1] Fetcher initialized timeout=%s max_bytes=%d", timeout, self.policy.max_response_bytes)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get(self, request: FetchRequest, *, use_cache: bool = True) -> FetchResult:
        headers = self.policy.validate_headers(
            request.headers,
            purpose=request.purpose,
            context=request.security_context,
            target_url=request.url,
        )
        method = request.method.upper()
        if method not in {"GET", "HEAD", "OPTIONS"}:
            raise FetchError("Fetcher only permits safe methods", kind=FetchErrorKind.PROTOCOL)
        cache_key = (
            request.url,
            method,
            tuple(sorted((key.lower(), value) for key, value in headers.items())),
            request.purpose,
            request.credential_context,
            request.run_id,
        )
        if use_cache and request.cache_mode == "run-deduplicate" and cache_key in self._run_dedup:
            logger.debug("[WP2.2] Fetch cache hit purpose=%s url=%s", request.purpose, request.url)
            return self._run_dedup[cache_key]

        current = request.url
        redirects: list[str] = []
        redirect_records: list[RedirectHop] = []
        started = time.monotonic()
        visited = {request.url}
        retries = 0
        for hop in range(self.policy.max_redirects + 1):
            self.policy.validate_request(current, purpose=request.purpose)
            try:
                # httpx persists Set-Cookie responses in its client jar.  A
                # passive crawl must not turn one public response into a
                # credential-bearing request for the next URL; explicit
                # request headers remain governed by the egress policy.
                if self._client.cookies:
                    self._client.cookies.clear()
                    logger.info("[FIX:fetcher-cookie] cleared passive response cookie jar")
                async with self._client.stream(method, current, headers=headers) as response:
                    if response.status_code in _REDIRECTS and response.headers.get("location"):
                        target = urljoin(current, response.headers["location"])
                        if target in visited:
                            raise FetchError("Redirect loop", kind=FetchErrorKind.REDIRECT_LOOP)
                        source = urlsplit(current)
                        destination = urlsplit(target)
                        if (
                            (source.scheme, source.netloc) != (destination.scheme, destination.netloc)
                            and not self.policy.allow_cross_origin_credentials
                            and any(key.lower() in {"authorization", "proxy-authorization", "cookie"} for key in headers)
                        ):
                            raise EgressPolicyError("credential-bearing headers cannot cross origins")
                        self.policy.validate_redirect(current, target, hop + 1, purpose=request.purpose)
                        redirects.append(current)
                        redirect_records.append(
                            RedirectHop(
                                from_url=current,
                                status_code=response.status_code,
                                location_raw=response.headers["location"],
                                to_url=target,
                                cross_origin=(source.scheme, source.netloc) != (destination.scheme, destination.netloc),
                                downgrade_https_to_http=source.scheme == "https" and destination.scheme == "http",
                            )
                        )
                        visited.add(target)
                        current = target
                        continue
                    if response.status_code in {429, 502, 503, 504} and retries < self.max_retries:
                        retries += 1
                        if self.retry_backoff:
                            await asyncio.sleep(self.retry_backoff * retries)
                        continue
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        self.policy.validate_response_size(size)
                        chunks.append(chunk)
                    result = FetchResult(
                        url=str(response.url),
                        status_code=response.status_code,
                        headers=self._redactor.mapping(
                            {key.lower(): value for key, value in response.headers.items()}
                        ),
                        body=b"".join(chunks),
                        redirects=tuple(redirects),
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                        retry_after=response.headers.get("retry-after"),
                        redirect_records=tuple(redirect_records),
                    )
            except EgressPolicyError as exc:
                kind = (
                    FetchErrorKind.RESPONSE_TOO_LARGE
                    if str(exc).startswith("Response exceeds")
                    else FetchErrorKind.BLOCKED_BY_POLICY
                )
                raise FetchError(str(exc), kind=kind) from exc
            except httpx.TimeoutException as exc:
                raise FetchError(str(exc), kind=FetchErrorKind.TIMEOUT) from exc
            except httpx.ConnectError as exc:
                raise FetchError(str(exc), kind=FetchErrorKind.CONNECT) from exc
            except httpx.HTTPError as exc:
                logger.error("[WP2.1] fetch failed purpose=%s url=%s error_type=%s", request.purpose, current, type(exc).__name__)
                raise FetchError(str(exc), kind=FetchErrorKind.PROTOCOL) from exc
            if use_cache and request.cache_mode == "run-deduplicate":
                self._run_dedup[cache_key] = result
            logger.debug("[WP2.1] fetch completed purpose=%s status=%d bytes=%d", request.purpose, result.status_code, len(result.body))
            return result
        raise FetchError("Too many redirects", kind=FetchErrorKind.TOO_MANY_REDIRECTS)
