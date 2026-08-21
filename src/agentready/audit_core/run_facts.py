"""Versioned run-level fact projections for robots.txt and sitemap outcomes."""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable, Mapping
from dataclasses import asdict, replace
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

from .fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS
from .store import RunFactRecord, SiteStore
from ..robots import (
    RobotsFetchState,
    RobotsFetchStatus,
    RobotsInterpretation,
    RobotsPolicy,
    evaluate_robots,
    parse_robots,
    robots_fetch_state,
)
from ..sitemap import SitemapResult, classify_sitemap_scope, parse_sitemap, parse_sitemap_collection
from ..sitemap_reconciliation import SitemapReconciliationReport, build_reconciliation_report

logger = logging.getLogger(__name__)
ROBOTS_PARSER_VERSION = "agentready.robots.rfc9309.v1"
SITEMAP_PARSER_VERSION = "agentready.sitemap.v1"


def persist_robots_run_facts(
    store: SiteStore,
    run_id: str,
    *,
    origin: str,
    robots_text: str | None,
    status_code: int | None,
    source_url: str | None = None,
    final_url: str | None = None,
    error_kind: str | None = None,
    user_agents: tuple[str, ...] = ("*",),
    interpretation: RobotsInterpretation = RobotsInterpretation.RFC9309,
) -> None:
    """Persist reusable origin-scoped robots facts without fetching."""
    observed_at = datetime.now(UTC).isoformat()
    source = source_url or urljoin(origin.rstrip("/") + "/", "robots.txt")
    fetch_status = robots_fetch_state(status_code) if error_kind is None else RobotsFetchStatus.UNREACHABLE
    logger.info(
        "run facts robots projection run_id=%s origin=%s status=%s fetch_status=%s error_kind=%s",
        run_id,
        origin,
        status_code,
        fetch_status.value,
        error_kind,
    )
    store.put_run_fact(
        RunFactRecord(
            run_id,
            "robots.fetch",
            DEFAULT_FACT_SCHEMA_VERSIONS["robots.fetch"],
            "origin",
            origin,
            {
                "state": fetch_status.value,
                "source_url": source,
                "final_url": final_url,
                "http_status": status_code,
                "error_kind": error_kind,
                "fetched_at": observed_at,
            },
            observed_at,
        )
    )
    if robots_text is None or fetch_status.value != "available":
        store.put_run_fact(
            RunFactRecord(
                run_id,
                "robots.parsed",
                DEFAULT_FACT_SCHEMA_VERSIONS["robots.parsed"],
                "origin",
                origin,
                {
                    "state": fetch_status.value,
                    "parser_version": ROBOTS_PARSER_VERSION,
                    "groups": [],
                    "sitemaps": [],
                    "warnings": [],
                },
                observed_at,
            )
        )
        return
    fetch = RobotsFetchState(fetch_status, http_status=status_code)
    policy = parse_robots(robots_text, origin, fetch=fetch)
    groups = [
        {
            "user_agents": list(group.user_agents),
            "rules": [asdict(rule) for rule in group.rules],
        }
        for group in policy.groups
    ]
    store.put_run_fact(
        RunFactRecord(
            run_id,
            "robots.parsed",
            DEFAULT_FACT_SCHEMA_VERSIONS["robots.parsed"],
            "origin",
            origin,
            {
                "state": "present",
                "parser_version": ROBOTS_PARSER_VERSION,
                "content_sha256": hashlib.sha256(robots_text.encode("utf-8")).hexdigest(),
                "groups": groups,
                "sitemaps": list(policy.sitemaps),
                "warnings": list(policy.parse_warnings),
            },
            observed_at,
        )
    )
    for user_agent in user_agents:
        decision = evaluate_robots(policy, user_agent, origin.rstrip("/") + "/", interpretation=interpretation)
        store.put_run_fact(
            RunFactRecord(
                run_id,
                "robots.policy",
                DEFAULT_FACT_SCHEMA_VERSIONS["robots.policy"],
                "crawler-profile",
                f"{origin}|{interpretation.value}|{user_agent}",
                {
                    "origin": origin,
                    "interpretation": interpretation.value,
                    "user_agent": user_agent,
                    "root_allowed": decision.allowed,
                    "reason": decision.reason,
                    "matched_rule": asdict(decision.matched_rule) if decision.matched_rule is not None else None,
                },
                observed_at,
            )
        )


def persist_robots_observation_run_facts(
    store: SiteStore,
    run_id: str,
    *,
    origin: str,
    observation: object,
    user_agents: tuple[str, ...] = ("*",),
    interpretation: RobotsInterpretation = RobotsInterpretation.RFC9309,
) -> None:
    body = getattr(observation, "body", None)
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else None
    status_code = getattr(observation, "status_code", None)
    source_url = getattr(observation, "source_url", None)
    final_url = getattr(observation, "final_url", None)
    error_kind = getattr(observation, "error_kind", None)
    persist_robots_run_facts(
        store,
        run_id,
        origin=origin,
        robots_text=text,
        status_code=status_code if isinstance(status_code, int) else None,
        source_url=source_url if isinstance(source_url, str) else None,
        final_url=final_url if isinstance(final_url, str) else None,
        error_kind=error_kind if isinstance(error_kind, str) else None,
        user_agents=user_agents,
        interpretation=interpretation,
    )


def persist_sitemap_run_facts(
    store: SiteStore,
    run_id: str,
    *,
    origin: str,
    documents: Iterable[bytes | str | object],
    source_urls: tuple[str, ...] = (),
    source_kind: str = "supplied",
) -> None:
    """Persist reusable sitemap discovery, parse and URL inventory facts."""
    observed_at = datetime.now(UTC).isoformat()
    observations = tuple(_coerce_sitemap_observation(document, index, source_urls, source_kind) for index, document in enumerate(documents))
    logger.info("run facts sitemap projection run_id=%s origin=%s sources=%d", run_id, origin, len(observations))
    store.put_run_fact(
        RunFactRecord(
            run_id,
            "sitemap.discovery",
            DEFAULT_FACT_SCHEMA_VERSIONS["sitemap.discovery"],
            "origin",
            origin,
            {
                "state": "present" if observations else "missing",
                "sources": [item["source_url"] for item in observations],
                "source_count": len(observations),
            },
            observed_at,
        )
    )
    parsed_results: list[SitemapResult] = []
    relative_urls_by_document: dict[str, tuple[str, ...]] = {}
    for item in observations:
        subject = str(item["source_url"])
        body = item["body"]
        compressed = bool(item["compressed"])
        result = (
            parse_sitemap(body, compressed=compressed)
            if isinstance(body, bytes) and item["fetch_state"] in {"available", "supplied"}
            else None
        )
        relative_urls: tuple[str, ...] = ()
        if result is not None:
            resolved_urls, relative_urls = _resolve_sitemap_locs(subject, result.urls)
            result = replace(
                result,
                urls=resolved_urls,
                child_sitemaps=tuple(urljoin(subject, url) for url in result.child_sitemaps),
            )
        if result is not None:
            parsed_results.append(result)
            relative_urls_by_document[subject] = relative_urls
        store.put_run_fact(
            RunFactRecord(
                run_id,
                "sitemap.fetch",
                DEFAULT_FACT_SCHEMA_VERSIONS["sitemap.fetch"],
                "document",
                subject,
                {
                    "state": item["fetch_state"],
                    "source_url": subject,
                    "source_kind": item["source_kind"],
                    "final_url": item["final_url"],
                    "http_status": item["status_code"],
                    "error_kind": item["error_kind"],
                    "compressed_bytes": result.compressed_bytes if result is not None else None,
                    "uncompressed_bytes": result.uncompressed_bytes if result is not None else None,
                },
                observed_at,
            )
        )
        if result is None:
            parse_payload = {
                "state": item["fetch_state"],
                "parser_version": SITEMAP_PARSER_VERSION,
                "kind": None,
                "evaluation": None,
                "warnings": [],
                "errors": [item["error_kind"]] if item["error_kind"] else [],
                "url_count": 0,
                "child_sitemap_count": 0,
                "relative_loc_count": 0,
            }
        else:
            parse_payload = {
                "state": "parse-error" if result.errors else "present",
                "parser_version": SITEMAP_PARSER_VERSION,
                "kind": result.kind,
                "evaluation": result.evaluation.value,
                "warnings": list(result.warnings),
                "errors": list(result.errors),
                "url_count": len(result.urls),
                "child_sitemap_count": len(result.child_sitemaps),
                "relative_loc_count": len(relative_urls_by_document.get(subject, ())),
            }
        store.put_run_fact(
            RunFactRecord(
                run_id,
                "sitemap.parsed",
                DEFAULT_FACT_SCHEMA_VERSIONS["sitemap.parsed"],
                "document",
                subject,
                parse_payload,
                observed_at,
            )
        )
    urls = tuple(url for result in parsed_results for url in result.urls)
    relative_or_invalid = tuple(sorted({url for urls_tuple in relative_urls_by_document.values() for url in urls_tuple}))
    scoped = classify_sitemap_scope(urls, origin)
    store.put_run_fact(
        RunFactRecord(
            run_id,
            "sitemap.urls",
            DEFAULT_FACT_SCHEMA_VERSIONS["sitemap.urls"],
            "origin",
            origin,
            {
                "state": "present" if urls else "missing",
                "same_origin": list(scoped.same_origin),
                "cross_origin_unknown": list(scoped.cross_origin_unknown),
                "cross_origin_verified": list(scoped.cross_origin_verified),
                "relative_or_invalid_loc": list(relative_or_invalid),
                "warnings": list(scoped.warnings),
            },
            observed_at,
        )
    )


def robots_policy_from_run_facts(store: SiteStore, run_id: str, *, origin: str) -> RobotsPolicy:
    parsed = next(
        (fact for fact in store.iter_run_facts(run_id, "robots.parsed") if fact.subject == origin),
        None,
    )
    if parsed is None:
        raise KeyError("robots.parsed fact was not found")
    payload = parsed.payload
    lines: list[str] = []
    for group in payload.get("groups", ()):
        if not isinstance(group, Mapping):
            continue
        for user_agent in group.get("user_agents", ()):
            lines.append(f"User-agent: {user_agent}")
        for rule in group.get("rules", ()):
            if isinstance(rule, Mapping):
                directive = "Allow" if rule.get("allow") else "Disallow"
                lines.append(f"{directive}: {rule.get('path', '')}")
    for sitemap in payload.get("sitemaps", ()):
        lines.append(f"Sitemap: {sitemap}")
    fetch_fact = next(
        (fact for fact in store.iter_run_facts(run_id, "robots.fetch") if fact.subject == origin),
        None,
    )
    fetch: RobotsFetchState | None = None
    if fetch_fact is not None:
        fetch_payload = fetch_fact.payload
        state_value = fetch_payload.get("state")
        try:
            fetch_status = RobotsFetchStatus(state_value)
        except ValueError:
            fetch_status = None
        if fetch_status is not None:
            fetch = RobotsFetchState(
                fetch_status,
                http_status=fetch_payload.get("http_status"),
            )
    return parse_robots("\n".join(lines), origin, fetch=fetch)


def sitemap_reconciliation_from_run_facts(
    store: SiteStore,
    run_id: str,
    *,
    origin: str,
    records: Mapping[str, Mapping[str, object]],
) -> SitemapReconciliationReport:
    urls_fact = next(
        (fact for fact in store.iter_run_facts(run_id, "sitemap.urls") if fact.subject == origin),
        None,
    )
    if urls_fact is None:
        raise KeyError("sitemap.urls fact was not found")
    urls = tuple(str(item) for item in urls_fact.payload.get("same_origin", ()))
    document = "\n".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return build_reconciliation_report((f"<urlset>{document}</urlset>",), records, origin=origin)


def _coerce_sitemap_observation(document: bytes | str | object, index: int, source_urls: tuple[str, ...], source_kind: str) -> dict[str, object]:
    if isinstance(document, bytes):
        source_url = source_urls[index] if index < len(source_urls) else f"inline:{index}"
        return {"source_url": source_url, "source_kind": source_kind, "fetch_state": "supplied", "body": document, "final_url": None, "status_code": None, "error_kind": None, "compressed": False}
    if isinstance(document, str):
        source_url = source_urls[index] if index < len(source_urls) else f"inline:{index}"
        return {"source_url": source_url, "source_kind": source_kind, "fetch_state": "supplied", "body": document.encode("utf-8"), "final_url": None, "status_code": None, "error_kind": None, "compressed": False}
    return {
        "source_url": str(getattr(document, "source_url")),
        "source_kind": str(getattr(document, "source_kind", source_kind)),
        "fetch_state": str(getattr(document, "fetch_state")),
        "body": getattr(document, "body", None),
        "final_url": getattr(document, "final_url", None),
        "status_code": getattr(document, "status_code", None),
        "error_kind": getattr(document, "error_kind", None),
        "compressed": bool(getattr(document, "compressed", False)),
    }


def _resolve_sitemap_locs(subject: str, urls: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve <loc> values against the document URL, tracking which were relative/invalid.

    Per the sitemap protocol, <loc> values must be absolute URLs. Values that
    are relative (or otherwise not already absolute) are still resolved so
    downstream reconciliation can use them, but they are also returned
    separately so callers can classify them as relative/invalid rather than
    silently treating them as valid absolute same-origin URLs.
    """
    resolved: list[str] = []
    relative: list[str] = []
    for url in urls:
        parsed = urlsplit(url)
        if not parsed.scheme or not parsed.netloc:
            relative.append(url)
        resolved.append(urljoin(subject, url))
    return tuple(resolved), tuple(relative)
