"""Versioned run-level fact projections for robots.txt and sitemap outcomes."""
from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from urllib.parse import urljoin

from .fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS
from .store import RunFactRecord, SiteStore
from ..robots import (
    RobotsFetchState,
    RobotsInterpretation,
    evaluate_robots,
    parse_robots,
    robots_fetch_state,
)
from ..sitemap import classify_sitemap_scope, parse_sitemap_collection

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
    user_agents: tuple[str, ...] = ("*",),
    interpretation: RobotsInterpretation = RobotsInterpretation.RFC9309,
) -> None:
    """Persist reusable origin-scoped robots facts without fetching."""
    observed_at = datetime.now(UTC).isoformat()
    source = source_url or urljoin(origin.rstrip("/") + "/", "robots.txt")
    fetch_status = robots_fetch_state(status_code)
    logger.info(
        "run facts robots projection run_id=%s origin=%s status=%s fetch_status=%s",
        run_id,
        origin,
        status_code,
        fetch_status.value,
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
                "http_status": status_code,
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


def persist_sitemap_run_facts(
    store: SiteStore,
    run_id: str,
    *,
    origin: str,
    documents: Iterable[bytes | str],
    source_urls: tuple[str, ...] = (),
) -> None:
    """Persist reusable sitemap discovery, parse and URL inventory facts."""
    observed_at = datetime.now(UTC).isoformat()
    payloads = tuple(document.encode("utf-8") if isinstance(document, str) else document for document in documents)
    sources = source_urls or tuple(f"inline:{index}" for index in range(len(payloads)))
    logger.info("run facts sitemap projection run_id=%s origin=%s sources=%d", run_id, origin, len(payloads))
    store.put_run_fact(
        RunFactRecord(
            run_id,
            "sitemap.discovery",
            DEFAULT_FACT_SCHEMA_VERSIONS["sitemap.discovery"],
            "origin",
            origin,
            {
                "state": "present" if payloads else "missing",
                "sources": list(sources),
                "source_count": len(payloads),
            },
            observed_at,
        )
    )
    parsed = parse_sitemap_collection(payloads)
    for index, result in enumerate(parsed):
        subject = sources[index] if index < len(sources) else f"inline:{index}"
        store.put_run_fact(
            RunFactRecord(
                run_id,
                "sitemap.fetch",
                DEFAULT_FACT_SCHEMA_VERSIONS["sitemap.fetch"],
                "document",
                subject,
                {
                    "state": "present",
                    "source_url": subject,
                    "compressed_bytes": result.compressed_bytes,
                    "uncompressed_bytes": result.uncompressed_bytes,
                },
                observed_at,
            )
        )
        store.put_run_fact(
            RunFactRecord(
                run_id,
                "sitemap.parsed",
                DEFAULT_FACT_SCHEMA_VERSIONS["sitemap.parsed"],
                "document",
                subject,
                {
                    "state": "parse-error" if result.errors else "present",
                    "parser_version": SITEMAP_PARSER_VERSION,
                    "kind": result.kind,
                    "evaluation": result.evaluation.value,
                    "warnings": list(result.warnings),
                    "errors": list(result.errors),
                    "url_count": len(result.urls),
                    "child_sitemap_count": len(result.child_sitemaps),
                },
                observed_at,
            )
        )
    urls = tuple(url for result in parsed for url in result.urls)
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
                "warnings": list(scoped.warnings),
            },
            observed_at,
        )
    )
