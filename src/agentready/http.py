from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import httpx

from . import __version__
from .models import Evidence
from .target import TargetError, ensure_public_url

_REDIRECTS = {301, 302, 303, 307, 308}
_SENSITIVE = {"authorization", "proxy-authorization", "cookie", "set-cookie"}


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

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get(self, url: str, headers: dict[str, str] | None = None, *, use_cache: bool = True) -> Fetched:
        headers = headers or {}
        cache_key = (url, tuple(sorted((k.lower(), v) for k, v in headers.items())))
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        current = url
        chain: list[str] = []
        for hop in range(self.max_redirects + 1):
            try:
                if not self.allow_private:
                    ensure_public_url(current)
                with self._client.stream("GET", current, headers=headers) as resp:
                    if resp.status_code in _REDIRECTS and resp.headers.get("location"):
                        if hop >= self.max_redirects:
                            raise FetchError(f"Too many redirects (>{self.max_redirects})")
                        chain.append(current)
                        current = urljoin(current, resp.headers["location"])
                        continue
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in resp.iter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise FetchError(f"Response exceeds {self.max_bytes} byte limit")
                        chunks.append(chunk)
                    result = Fetched(
                        url=str(resp.url),
                        status_code=resp.status_code,
                        headers={k.lower(): v for k, v in resp.headers.items()},
                        body=b"".join(chunks),
                        redirected_from=chain[:],
                    )
            except (httpx.HTTPError, TargetError) as exc:
                raise FetchError(str(exc)) from exc
            if use_cache:
                self._cache[cache_key] = result
            return result
        raise FetchError("Redirect loop")
