from __future__ import annotations

import json
import logging
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import __version__

_KEY_RE = re.compile(r"^[A-Za-z0-9-]{8,128}$")
DEFAULT_ENDPOINT = "https://api.indexnow.org/indexnow"
YANDEX_ENDPOINT = "https://yandex.com/indexnow"
PROVIDER_ENDPOINTS = {
    "global": DEFAULT_ENDPOINT,
    "yandex": YANDEX_ENDPOINT,
}
MAX_URLS = 10_000
logger = logging.getLogger(__name__)


class IndexNowError(ValueError):
    pass


@dataclass(slots=True)
class IndexNowSubmission:
    endpoint: str
    host: str
    key_location: str
    url_count: int
    status_code: int | None
    accepted: bool
    response_text: str
    dry_run: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "endpoint": self.endpoint,
            "host": self.host,
            "key_location": self.key_location,
            "url_count": self.url_count,
            "status_code": self.status_code,
            "accepted": self.accepted,
            "response_text": self.response_text,
            "dry_run": self.dry_run,
        }


def validate_key(key: str) -> str:
    key = key.strip()
    if not _KEY_RE.fullmatch(key):
        logger.warning("IndexNow key validation failed")
        raise IndexNowError("IndexNow key must be 8-128 ASCII letters, digits, or hyphens")
    logger.debug("IndexNow key validation passed")
    return key


def generate_key(bytes_count: int = 16) -> str:
    if bytes_count < 4 or bytes_count > 64:
        raise IndexNowError("bytes_count must be between 4 and 64")
    return secrets.token_hex(bytes_count)


def write_key_file(directory: str | Path, key: str, *, overwrite: bool = False) -> Path:
    key = validate_key(key)
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{key}.txt"
    if path.exists() and not overwrite:
        raise IndexNowError(f"key file already exists: {path}")
    path.write_text(key, encoding="utf-8")
    return path


def default_key_location(site_url: str, key: str) -> str:
    key = validate_key(key)
    p = urlsplit(site_url if "://" in site_url else "https://" + site_url)
    if not p.hostname:
        raise IndexNowError("invalid site URL")
    scheme = p.scheme or "https"
    port = f":{p.port}" if p.port else ""
    return f"{scheme}://{p.hostname}{port}/{key}.txt"


def _normalize_urls(urls: list[str]) -> tuple[str, list[str]]:
    logger.debug("Normalizing IndexNow URLs: input_count=%d", len(urls))
    clean: list[str] = []
    host: str | None = None
    for raw in urls:
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        p = urlsplit(value)
        if p.scheme not in {"http", "https"} or not p.hostname:
            raise IndexNowError(f"URL must be absolute http(s): {value}")
        current_host = p.netloc.lower()
        if host is None:
            host = current_host
        elif current_host != host:
            raise IndexNowError(f"all URLs in one IndexNow batch must use the same host: {host} != {current_host}")
        if value not in clean:
            clean.append(value)
    if not clean:
        raise IndexNowError("no URLs to submit")
    if len(clean) > MAX_URLS:
        raise IndexNowError(f"IndexNow allows at most {MAX_URLS} URLs per request")
    if host is None:
        raise ValueError("URL host is required")
    logger.debug("Normalized IndexNow URLs: host=%s url_count=%d", host, len(clean))
    return host, clean


def resolve_endpoint(*, provider: str = "global", endpoint: str | None = None) -> str:
    normalized_provider = provider.strip().lower()
    if normalized_provider not in PROVIDER_ENDPOINTS:
        choices = ", ".join(sorted(PROVIDER_ENDPOINTS))
        raise IndexNowError(f"unknown IndexNow provider {provider!r}; expected one of: {choices}")
    if endpoint is not None and normalized_provider != "global":
        raise IndexNowError("choose either a named IndexNow provider or an explicit endpoint, not both")
    selected = endpoint or PROVIDER_ENDPOINTS[normalized_provider]
    parsed = urlsplit(selected)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise IndexNowError("IndexNow endpoint must be an absolute http(s) URL without credentials")
    logger.debug(
        "Resolved IndexNow endpoint: provider=%s explicit=%s endpoint_host=%s",
        normalized_provider,
        endpoint is not None,
        parsed.netloc,
    )
    return selected


def _validate_key_location(key_location: str, host: str, urls: list[str]) -> None:
    parsed = urlsplit(key_location)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise IndexNowError("keyLocation must be an absolute http(s) URL without credentials")
    if parsed.netloc.lower() != host:
        raise IndexNowError(f"keyLocation must use the submitted URL host: {host}")
    if parsed.query or parsed.fragment:
        raise IndexNowError("keyLocation must not contain a query string or fragment")

    location_path = parsed.path or "/"
    scope = location_path.rsplit("/", 1)[0] + "/"
    outside_scope = [url for url in urls if not (urlsplit(url).path or "/").startswith(scope)]
    if outside_scope:
        raise IndexNowError(
            f"keyLocation at {scope} can authorize only URLs under that path; "
            f"{len(outside_scope)} URL(s) are outside its scope"
        )
    logger.debug("Validated IndexNow keyLocation scope: host=%s scope=%s url_count=%d", host, scope, len(urls))


def verify_key_file(site_url: str, key: str, *, key_location: str | None = None, timeout: float = 10.0, verify_tls: bool = True) -> tuple[bool, int | None, str]:
    key = validate_key(key)
    location = key_location or default_key_location(site_url, key)
    try:
        response = httpx.get(
            location,
            timeout=timeout,
            verify=verify_tls,
            follow_redirects=True,
            headers={"User-Agent": f"agentready-tools/{__version__} IndexNow verifier"},
        )
    except httpx.HTTPError as exc:
        return False, None, str(exc)
    body = response.text.strip()
    ok = response.status_code == 200 and body == key
    detail = "key file is publicly reachable and matches the key" if ok else f"expected HTTP 200 with exact key body; got HTTP {response.status_code}"
    return ok, response.status_code, detail


def build_payload(urls: list[str], key: str, *, key_location: str | None = None) -> dict[str, object]:
    key = validate_key(key)
    host, clean = _normalize_urls(urls)
    payload: dict[str, object] = {"host": host, "key": key, "urlList": clean}
    if key_location:
        _validate_key_location(key_location, host, clean)
        payload["keyLocation"] = key_location
    logger.debug("Built IndexNow payload: host=%s url_count=%d custom_key_location=%s", host, len(clean), bool(key_location))
    return payload


def submit_urls(
    urls: list[str],
    key: str,
    *,
    endpoint: str | None = None,
    provider: str = "global",
    key_location: str | None = None,
    timeout: float = 15.0,
    verify_tls: bool = True,
    dry_run: bool = False,
) -> IndexNowSubmission:
    selected_endpoint = resolve_endpoint(provider=provider, endpoint=endpoint)
    payload = build_payload(urls, key, key_location=key_location)
    host = str(payload["host"])
    location = str(payload.get("keyLocation") or default_key_location("https://" + host, key))
    if dry_run:
        logger.info("Prepared IndexNow dry run: provider=%s host=%s url_count=%d", provider, host, len(payload["urlList"]))  # type: ignore[arg-type]
        return IndexNowSubmission(selected_endpoint, host, location, len(payload["urlList"]), None, False, json.dumps(payload, ensure_ascii=False), True)  # type: ignore[arg-type]
    logger.info("Submitting IndexNow URLs: provider=%s host=%s url_count=%d", provider, host, len(payload["urlList"]))  # type: ignore[arg-type]
    try:
        response = httpx.post(
            selected_endpoint,
            json=payload,
            timeout=timeout,
            verify=verify_tls,
            follow_redirects=False,
            headers={"User-Agent": f"agentready-tools/{__version__} IndexNow client"},
        )
    except httpx.HTTPError as exc:
        logger.error("IndexNow submission failed: provider=%s host=%s error_type=%s", provider, host, type(exc).__name__)
        raise IndexNowError(str(exc)) from exc
    accepted = response.status_code in {200, 202}
    logger.info(
        "IndexNow submission completed: provider=%s host=%s status_code=%d accepted=%s",
        provider,
        host,
        response.status_code,
        accepted,
    )
    return IndexNowSubmission(
        endpoint=selected_endpoint,
        host=host,
        key_location=location,
        url_count=len(payload["urlList"]),  # type: ignore[arg-type]
        status_code=response.status_code,
        accepted=accepted,
        response_text=response.text[:2000],
        dry_run=False,
    )
