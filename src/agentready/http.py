from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Self
from urllib.parse import urljoin

import httpx

from . import __version__
from .audit_core.collection import FactView
from .egress import EgressPolicy, EgressPolicyError
from .models import Evidence
from .security import SecretRedactor
from .target import TargetError

_REDIRECTS = {301, 302, 303, 307, 308}
_SENSITIVE = {"authorization", "proxy-authorization", "cookie", "set-cookie"}
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Fetched:
    url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    redirected_from: list[str]

    @property
    def text(self) -> str:
        charset = "utf-8"
        ct = self.headers.get("content-type", "")
        if "charset=" in ct.lower():
            charset = ct.lower().split("charset=", 1)[1].split(";", 1)[0].strip() or "utf-8"
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";", 1)[0].strip().lower()

    def evidence(self, action: str, *, preview: bool = True, finding: str | None = None) -> Evidence:
        clean_headers = {
            k: ("[redacted]" if k.lower() in _SENSITIVE else v[:1000])
            for k, v in self.headers.items()
            if k.lower() in {"content-type", "link", "content-signal", "www-authenticate", "payment-required", "location"}
        }
        body_preview = self.text[:600] if preview else None
        return Evidence(
            action=action,
            url=self.url,
            method="GET",
            status_code=self.status_code,
            content_type=self.content_type or None,
            finding=finding,
            body_preview=body_preview,
            headers=clean_headers,
        )


class FetchError(RuntimeError):
    pass


class HttpClient:
    def __init__(
        self,
        *,
        timeout: float = 5.0,
        max_redirects: int = 5,
        max_bytes: int = 5 * 1024 * 1024,
        verify: bool = True,
        allow_private: bool = True,
        user_agent: str | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.max_bytes = max_bytes
        self.verify = verify
        self.allow_private = allow_private
        self.egress_policy = EgressPolicy(
            block_private=not allow_private,
            max_redirects=max_redirects,
            max_response_bytes=max_bytes,
        )
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            verify=verify,
            follow_redirects=False,
            headers={
                "User-Agent": user_agent or f"agentready-tools/{__version__} (+https://isitagentready.com-inspired-audit)",
                "Accept-Encoding": "gzip, deflate, br",
            },
        )
        self._cache: dict[tuple[str, tuple[tuple[str, str], ...]], Fetched] = {}
        self._redactor = SecretRedactor()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get(self, url: str, headers: dict[str, str] | None = None, *, use_cache: bool = True) -> Fetched:
        headers = headers or {}
        try:
            headers = self.egress_policy.validate_headers(headers, purpose="bounded-http-client")
        except EgressPolicyError as exc:
            raise FetchError(str(exc)) from exc
        cache_key = (url, tuple(sorted((k.lower(), v) for k, v in headers.items())))
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        current = url
        chain: list[str] = []
        for hop in range(self.max_redirects + 1):
            try:
                self.egress_policy.validate_request(current, purpose="bounded-http-client")
                with self._client.stream("GET", current, headers=headers) as resp:
                    if resp.status_code in _REDIRECTS and resp.headers.get("location"):
                        if hop >= self.max_redirects:
                            raise FetchError(f"Too many redirects (>{self.max_redirects})")
                        chain.append(current)
                        next_url = urljoin(current, resp.headers["location"])
                        self.egress_policy.validate_redirect(
                            current,
                            next_url,
                            hop + 1,
                            purpose="bounded-http-client",
                        )
                        current = next_url
                        continue
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        self.egress_policy.validate_response_size(size)
                        chunks.append(chunk)
                    result = Fetched(
                        url=str(resp.url),
                        status_code=resp.status_code,
                        headers=self._redactor.mapping({k.lower(): v for k, v in resp.headers.items()}),
                        body=b"".join(chunks),
                        redirected_from=chain[:],
                    )
            except (httpx.HTTPError, TargetError, EgressPolicyError) as exc:
                raise FetchError(str(exc)) from exc
            if use_cache:
                self._cache[cache_key] = result
            return result
        raise FetchError("Redirect loop")

    def cached(self, url: str, headers: dict[str, str] | None = None) -> Fetched | None:
        """Return a response already collected by this bounded run, if present."""
        cache_key = (url, tuple(sorted((k.lower(), v) for k, v in (headers or {}).items())))
        return self._cache.get(cache_key)


class CachedHttpTransport:
    """Replay cached sync-client responses through an async HTTP boundary."""

    def __init__(self, client: HttpClient) -> None:
        self._client = client

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        cached = self._client.cached(str(request.url), dict(request.headers))
        if cached is not None:
            return httpx.Response(
                cached.status_code,
                headers=cached.headers,
                content=cached.body,
                request=request,
            )
        # Keep cache misses on the same bounded HttpClient boundary.  The old
        # async transport bypassed egress, timeout, and the collected cache.
        fetched = await asyncio.to_thread(
            self._client.get,
            str(request.url),
            headers=dict(request.headers),
        )
        return httpx.Response(
            fetched.status_code,
            headers=fetched.headers,
            content=fetched.body,
            request=request,
        )

    async def aclose(self) -> None:
        return None


class CollectedHttpClient:
    """Replay collected page representations before bounded fallback fetches."""

    def __init__(self, client: HttpClient | None, fact_views: tuple[FactView, ...]) -> None:
        self._client = client
        self._views: dict[str, FactView] = {}
        for view in fact_views:
            self._views[view.url] = view
            if view.page.requested_url:
                self._views[view.page.requested_url] = view

    @staticmethod
    def _is_collected_representation(headers: dict[str, str] | None) -> bool:
        if not headers:
            return True
        lowered = {key.lower(): value for key, value in headers.items()}
        if "user-agent" in lowered:
            return False
        accept = lowered.get("accept", "")
        return not accept or "text/html" in accept or "application/xhtml+xml" in accept or "*/*" in accept

    def get(self, url: str, headers: dict[str, str] | None = None, *, use_cache: bool = True) -> Fetched:
        view = self._views.get(url)
        if use_cache and view is not None and view.body is not None and self._is_collected_representation(headers):
            logger.debug("[FIX:fact-view-replay] replaying collected response url=%s", url)
            return Fetched(
                url=view.url,
                status_code=view.page.status_code or 0,
                headers=dict(view.headers),
                body=view.body,
                redirected_from=[],
            )
        if self._client is None:
            logger.error("[FIX:collection-replay] analyzer requested an uncollected representation url=%s", url)
            raise FetchError(f"representation was not collected for analyzer replay: {url}")
        return self._client.get(url, headers=headers, use_cache=use_cache)
