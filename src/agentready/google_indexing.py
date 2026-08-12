from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import __version__
from .structured_data import extract_jsonld_nodes, google_indexing_eligible_types
from .target import TargetError, ensure_public_url

PUBLISH_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
METADATA_ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications/metadata"
GOOGLE_INDEXING_SCOPE = "https://www.googleapis.com/auth/indexing"
DEFAULT_MAX_NOTIFICATIONS = 200
MAX_RETRY_DELAY_SECONDS = 60.0
NOTIFICATION_TYPES = {"URL_UPDATED", "URL_DELETED"}
ELIGIBLE_TYPES = {"job-posting", "broadcast-event"}

logger = logging.getLogger(__name__)


class GoogleIndexingError(ValueError):
    pass


@dataclass(slots=True)
class GoogleNotificationResult:
    url: str
    notification_type: str
    eligible_type: str
    accepted: bool
    status_code: int | None
    attempts: int
    response: object | None = None
    error: str | None = None
    dry_run: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "notification_type": self.notification_type,
            "eligible_type": self.eligible_type,
            "accepted": self.accepted,
            "status_code": self.status_code,
            "attempts": self.attempts,
            "response": self.response,
            "error": self.error,
            "dry_run": self.dry_run,
        }


@dataclass(slots=True)
class GooglePublishResult:
    results: list[GoogleNotificationResult]
    dry_run: bool

    @property
    def accepted_count(self) -> int:
        return sum(1 for result in self.results if result.accepted)

    @property
    def failed_count(self) -> int:
        return sum(
            1
            for result in self.results
            if not result.accepted and (not result.dry_run or result.error is not None)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "url_count": len(self.results),
            "accepted_count": self.accepted_count,
            "failed_count": self.failed_count,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(slots=True)
class GoogleMetadataResult:
    url: str
    status_code: int
    found: bool
    metadata: object | None

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "found": self.found,
            "metadata": self.metadata,
        }


def _validate_url(value: str) -> str:
    url = value.strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise GoogleIndexingError(f"URL must be absolute http(s): {url}")
    if parsed.username or parsed.password:
        raise GoogleIndexingError("URL must not contain credentials")
    return url


def normalize_urls(urls: list[str], *, max_notifications: int = DEFAULT_MAX_NOTIFICATIONS) -> list[str]:
    if max_notifications < 1:
        raise GoogleIndexingError("max_notifications must be at least 1")
    clean: list[str] = []
    for raw in urls:
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        url = _validate_url(value)
        if url not in clean:
            clean.append(url)
    if not clean:
        raise GoogleIndexingError("no URLs to publish")
    if len(clean) > max_notifications:
        raise GoogleIndexingError(
            f"refusing {len(clean)} Google notifications because max_notifications is {max_notifications}; "
            "the documented default publish quota is 200 per project per day"
        )
    logger.debug("Normalized Google notification URLs: url_count=%d max_notifications=%d", len(clean), max_notifications)
    return clean


_ELIGIBILITY_MAX_BYTES = 5 * 1024 * 1024


def inspect_url_eligibility(url: str, *, timeout: float = 15.0, verify_tls: bool = True) -> set[str]:
    from .http import FetchError, HttpClient

    url = _validate_url(url)
    try:
        ensure_public_url(url)
    except TargetError as exc:
        raise GoogleIndexingError(f"Google eligibility preflight requires a public URL: {exc}") from exc
    logger.debug("Starting Google eligibility preflight: host=%s", urlsplit(url).netloc)
    # Use the project's hardened HttpClient so that:
    # - every redirect target is validated through ensure_public_url (SSRF guard)
    # - the response body is capped at _ELIGIBILITY_MAX_BYTES
    try:
        with HttpClient(
            timeout=timeout,
            verify=verify_tls,
            allow_private=False,
            max_bytes=_ELIGIBILITY_MAX_BYTES,
            user_agent=f"agentready-tools/{__version__} Google Indexing eligibility verifier",
        ) as client:
            fetched = client.get(url, use_cache=False)
    except (FetchError, TargetError) as exc:
        logger.error(
            "Google eligibility preflight failed: host=%s error_type=%s",
            urlsplit(url).netloc,
            type(exc).__name__,
        )
        raise GoogleIndexingError(f"failed to fetch URL for Google eligibility preflight ({type(exc).__name__})") from exc
    content_type = fetched.content_type
    if fetched.status_code != 200 or "html" not in content_type:
        raise GoogleIndexingError(
            f"Google URL_UPDATED eligibility preflight requires HTTP 200 HTML; got HTTP {fetched.status_code}"
        )
    nodes, errors, block_count = extract_jsonld_nodes(fetched.text)
    eligible = google_indexing_eligible_types(nodes)
    logger.debug(
        "Completed Google eligibility preflight: host=%s jsonld_blocks=%d parse_errors=%d eligible_types=%s",
        urlsplit(url).netloc,
        block_count,
        len(errors),
        sorted(eligible),
    )
    if not eligible:
        raise GoogleIndexingError(
            "Google Indexing API supports only JobPosting or BroadcastEvent embedded in VideoObject"
        )
    return eligible


def _load_google_dependencies() -> tuple[type[Any], type[Any], tuple[type[BaseException], ...]]:
    try:
        from google.auth.exceptions import GoogleAuthError
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2.service_account import Credentials
        from requests import RequestException
    except ImportError as exc:
        raise GoogleIndexingError(
            "Google Indexing support requires the optional dependency: pip install 'agentready-tools[google]'"
        ) from exc
    return Credentials, AuthorizedSession, (GoogleAuthError, RequestException)


def _authorized_session(credentials_path: str | Path | None) -> tuple[Any, tuple[type[BaseException], ...]]:
    path_value = str(credentials_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")).strip()
    if not path_value:
        raise GoogleIndexingError(
            "Google service-account credentials are required via --credentials or GOOGLE_APPLICATION_CREDENTIALS"
        )
    path = Path(path_value)
    if not path.is_file():
        raise GoogleIndexingError("Google service-account credentials file does not exist")
    credentials_type, session_type, request_errors = _load_google_dependencies()
    try:
        credentials = credentials_type.from_service_account_file(path, scopes=[GOOGLE_INDEXING_SCOPE])
        session = session_type(credentials)
    except (OSError, ValueError, *request_errors) as exc:
        logger.error("Failed to initialize Google credentials: error_type=%s", type(exc).__name__)
        raise GoogleIndexingError(f"failed to initialize Google credentials ({type(exc).__name__})") from exc
    logger.debug("Initialized Google authorized session with indexing-only scope")
    return session, request_errors


def _response_payload(response: Any) -> object | None:
    text = str(getattr(response, "text", ""))[:2000]
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _retry_delay(response: Any, attempt: int) -> float:
    header = str(getattr(response, "headers", {}).get("Retry-After", "")).strip()
    if header:
        try:
            return min(max(float(header), 0.0), MAX_RETRY_DELAY_SECONDS)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(header)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                seconds = (retry_at - datetime.now(UTC)).total_seconds()
                return min(max(seconds, 0.0), MAX_RETRY_DELAY_SECONDS)
            except (TypeError, ValueError, OverflowError):
                pass
    return min(float(2 ** max(0, attempt - 1)), MAX_RETRY_DELAY_SECONDS)


def _publish_one(
    session: Any,
    request_errors: tuple[type[BaseException], ...],
    url: str,
    notification_type: str,
    eligible_type: str,
    *,
    timeout: float,
    max_retries: int,
    sleeper: Callable[[float], None],
) -> GoogleNotificationResult:
    payload = {"url": url, "type": notification_type}
    host = urlsplit(url).netloc
    for attempt in range(1, max_retries + 2):
        logger.debug(
            "Publishing Google URL notification: host=%s type=%s attempt=%d",
            host,
            notification_type,
            attempt,
        )
        try:
            response = session.post(PUBLISH_ENDPOINT, json=payload, timeout=timeout)
        except request_errors as exc:
            logger.error(
                "Google notification request failed: host=%s type=%s attempt=%d error_type=%s",
                host,
                notification_type,
                attempt,
                type(exc).__name__,
            )
            return GoogleNotificationResult(
                url,
                notification_type,
                eligible_type,
                False,
                None,
                attempt,
                error=f"request failed ({type(exc).__name__})",
            )
        status_code = int(response.status_code)
        if status_code == 200:
            logger.info("Google notification accepted: host=%s type=%s attempts=%d", host, notification_type, attempt)
            return GoogleNotificationResult(
                url,
                notification_type,
                eligible_type,
                True,
                status_code,
                attempt,
                response=_response_payload(response),
            )
        if status_code not in {429, 500, 503} or attempt > max_retries:
            logger.error(
                "Google notification rejected: host=%s type=%s status_code=%d attempts=%d",
                host,
                notification_type,
                status_code,
                attempt,
            )
            return GoogleNotificationResult(
                url,
                notification_type,
                eligible_type,
                False,
                status_code,
                attempt,
                response=_response_payload(response),
                error=f"Google Indexing API returned HTTP {status_code}",
            )
        delay = _retry_delay(response, attempt)
        logger.warning(
            "Retrying Google notification: host=%s type=%s status_code=%d delay_seconds=%.1f",
            host,
            notification_type,
            status_code,
            delay,
        )
        sleeper(delay)
    raise AssertionError("unreachable Google notification retry state")


def publish_urls(
    urls: list[str],
    *,
    notification_type: str = "URL_UPDATED",
    eligible_type: str | None = None,
    credentials_path: str | Path | None = None,
    max_notifications: int = DEFAULT_MAX_NOTIFICATIONS,
    timeout: float = 15.0,
    verify_tls: bool = True,
    max_retries: int = 2,
    dry_run: bool = False,
    session: Any | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    eligibility_inspector: Callable[..., set[str]] = inspect_url_eligibility,
) -> GooglePublishResult:
    normalized_type = notification_type.strip().upper()
    if normalized_type not in NOTIFICATION_TYPES:
        raise GoogleIndexingError(f"notification_type must be one of: {', '.join(sorted(NOTIFICATION_TYPES))}")
    if max_retries < 0 or max_retries > 10:
        raise GoogleIndexingError("max_retries must be between 0 and 10")
    normalized_eligible_type = eligible_type.strip().lower() if eligible_type else None
    if normalized_eligible_type and normalized_eligible_type not in ELIGIBLE_TYPES:
        raise GoogleIndexingError(f"eligible_type must be one of: {', '.join(sorted(ELIGIBLE_TYPES))}")
    if normalized_type == "URL_DELETED" and not normalized_eligible_type:
        raise GoogleIndexingError(
            "URL_DELETED requires --eligible-type job-posting|broadcast-event because the removed page cannot be preflighted"
        )

    clean = normalize_urls(urls, max_notifications=max_notifications)
    eligibility: dict[str, str] = {}
    preflight_failures: dict[str, str] = {}
    for url in clean:
        if normalized_type == "URL_DELETED":
            eligibility[url] = normalized_eligible_type or ""
            continue
        try:
            detected = eligibility_inspector(url, timeout=timeout, verify_tls=verify_tls)
        except (GoogleIndexingError, TargetError) as exc:
            logger.error(
                "Google eligibility preflight failed for url: host=%s error=%s",
                urlsplit(url).netloc,
                type(exc).__name__,
            )
            preflight_failures[url] = str(exc)
            continue
        if normalized_eligible_type and normalized_eligible_type not in detected:
            preflight_failures[url] = (
                f"requested eligible type {normalized_eligible_type} was not detected for {url}"
            )
            continue
        eligibility[url] = normalized_eligible_type or min(detected)

    if dry_run:
        logger.info("Prepared Google Indexing dry run: url_count=%d type=%s", len(clean), normalized_type)
        results: list[GoogleNotificationResult] = []
        for url in clean:
            if url in preflight_failures:
                results.append(
                    GoogleNotificationResult(
                        url,
                        normalized_type,
                        normalized_eligible_type or "",
                        False,
                        None,
                        0,
                        error=preflight_failures[url],
                        dry_run=True,
                    )
                )
            else:
                results.append(
                    GoogleNotificationResult(
                        url,
                        normalized_type,
                        eligibility[url],
                        False,
                        None,
                        0,
                        response={"url": url, "type": normalized_type},
                        dry_run=True,
                    )
                )
        return GooglePublishResult(results, True)

    request_errors: tuple[type[BaseException], ...] = ()
    active_session = session
    if active_session is None:
        active_session, request_errors = _authorized_session(credentials_path)
    live_results: list[GoogleNotificationResult] = []
    for url in clean:
        if url in preflight_failures:
            live_results.append(
                GoogleNotificationResult(
                    url,
                    normalized_type,
                    normalized_eligible_type or "",
                    False,
                    None,
                    0,
                    error=preflight_failures[url],
                )
            )
        else:
            live_results.append(
                _publish_one(
                    active_session,
                    request_errors,
                    url,
                    normalized_type,
                    eligibility[url],
                    timeout=timeout,
                    max_retries=max_retries,
                    sleeper=sleeper,
                )
            )
    return GooglePublishResult(live_results, False)


def get_metadata(
    url: str,
    *,
    credentials_path: str | Path | None = None,
    timeout: float = 15.0,
    session: Any | None = None,
) -> GoogleMetadataResult:
    normalized_url = _validate_url(url)
    request_errors: tuple[type[BaseException], ...] = ()
    active_session = session
    if active_session is None:
        active_session, request_errors = _authorized_session(credentials_path)
    logger.debug("Fetching Google notification metadata: host=%s", urlsplit(normalized_url).netloc)
    try:
        response = active_session.get(METADATA_ENDPOINT, params={"url": normalized_url}, timeout=timeout)
    except request_errors as exc:
        logger.error("Google metadata request failed: error_type=%s", type(exc).__name__)
        raise GoogleIndexingError(f"Google metadata request failed ({type(exc).__name__})") from exc
    status_code = int(response.status_code)
    if status_code not in {200, 404}:
        logger.error("Google metadata request rejected: status_code=%d", status_code)
        raise GoogleIndexingError(f"Google Indexing metadata endpoint returned HTTP {status_code}")
    found = status_code == 200
    logger.info("Google metadata request completed: host=%s found=%s", urlsplit(normalized_url).netloc, found)
    return GoogleMetadataResult(normalized_url, status_code, found, _response_payload(response) if found else None)
