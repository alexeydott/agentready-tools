"""Optional MCP facade exposing canonical v2 audit tools.

Requires: pip install 'agentready-tools[mcp]'
The tool blocks private/loopback targets because remote MCP servers must not be
usable as arbitrary SSRF proxies.
"""
from __future__ import annotations

try:
    from mcp.server import MCPServer
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "MCP dependency is missing. Activate the project virtual environment and run "
        "`python -m pip install -e \".[mcp]\"`; verify with "
        "`python -c \"import mcp; print(mcp.__file__)\"`."
    ) from exc

import logging
import hashlib
from dataclasses import asdict

from .agentfindings import build_findings, build_remediation_plan
from .audit_service import AuditRequest, AuditService
from .exports import export_query
from .metrics import ExternalMetric, ProviderConfig, ProviderStatus
from .provider_service import ProviderService
from .mobile_scanner import audit_mobile
from .query_service import QueryService
from .report_storage import save_report
from .robots import RobotsInterpretation, parse_robots, simulate_robots
from .seo_scanner import audit_seo
from .workflows import InventoryRequest

logger = logging.getLogger(__name__)

mcp = MCPServer(
    "AgentReady Scanner",
    instructions=(
        "Read-only website audit for AI-agent discovery, content, auth, capability and commerce protocols. "
        "For coding agents: use audit_findings to get only the failed/warned checks with fix instructions, "
        "and remediation_plan to get a prioritized step-by-step fix plan with ready-to-use prompts."
    ),
)


@mcp.tool()
def audit_v2(
    url: str,
    preset: str = "all",
    profile: str = "standard",
    max_pages: int = 25,
    timeout: float = 5.0,
    limits: dict[str, int | float] | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    render: bool = False,
    provider: str | None = None,
    language: str = "en",
    discovery_kind: str = "single",
    discovery_urls: list[str] | None = None,
    discovery_sitemap_xml: str | None = None,
    discovery_sitemap_urls: list[str] | None = None,
    discovery_limit: int = 1000,
    rescan_of: str | None = None,
    selected_urls: list[str] | None = None,
) -> dict:
    """Run the shared bounded v2 audit application service.

    Set ``discovery_kind="crawl"`` to follow all discovered same-origin pages
    within the configured bounds. Use ``max_pages=0`` for the server hard cap.
    """
    effective_limits = limits or {}
    effective_max_pages = (
        int(effective_limits["max_pages"])
        if max_pages == 25 and "max_pages" in effective_limits
        else max_pages
    )
    result = AuditService().run(
        AuditRequest(
            target=url,
            preset=preset,
            profile=profile,
            max_pages=effective_max_pages,
            timeout=timeout,
            limits=effective_limits,
            include=tuple(include or ()),
            exclude=tuple(exclude or ()),
            render=render,
            provider=provider,
            language=language,
            discovery_kind=discovery_kind,
            discovery_urls=tuple(discovery_urls or ()),
            discovery_sitemap_xml=discovery_sitemap_xml,
            discovery_sitemap_urls=tuple(discovery_sitemap_urls or ()),
            discovery_limit=discovery_limit,
            parent_run_id=rescan_of,
            selected_urls=tuple(selected_urls or ()),
            allow_private=False,
        )
    )
    payload = result.to_dict()
    saved_path = save_report(payload, target=url, surface="mcp-v2", fmt="json")
    logger.info("MCP report saved path=%s", saved_path)
    return payload


@mcp.tool()
def robots_simulate_v2(
    live_robots: str,
    proposed_robots: str,
    observed_pages: list[str] | None = None,
    user_agents: list[str] | None = None,
    origin: str = "https://example.com",
    interpretation: str = "rfc9309",
) -> dict:
    """Compare current and proposed robots.txt policies without publishing changes.

    This is the MCP equivalent of the dashboard and CLI Virtual Robots tool;
    callers provide the bounded audit inventory URLs in ``observed_pages``.
    """
    try:
        mode = RobotsInterpretation(interpretation)
    except ValueError as exc:
        raise ValueError("interpretation must be rfc9309 or google") from exc
    live = parse_robots(live_robots, origin)
    proposed = parse_robots(proposed_robots, origin)
    urls = list(dict.fromkeys(observed_pages or []))
    per_bot = {
        user_agent: (lambda diff: {
            "newly_allowed": list(diff.newly_allowed_urls),
            "newly_blocked": list(diff.newly_blocked_urls),
            "sitemap_conflicts": list(diff.sitemap_urls_affected),
            "important_page_conflicts": list(diff.observed_search_pages_affected),
            "label": diff.label,
            "user_agent": diff.user_agent,
        })(simulate_robots(
            live,
            proposed,
            urls,
            user_agent=user_agent,
            observed_search_pages=urls,
            interpretation=mode,
        ))
        for user_agent in (user_agents or ["*"])
    }
    logger.info("MCP robots simulation bots=%d urls=%d interpretation=%s", len(per_bot), len(urls), mode.value)
    return {
        "schema": "agentready.robots-simulation.v2",
        "interpretation": mode.value,
        "live_policy_hash": hashlib.sha256(live_robots.encode("utf-8")).hexdigest(),
        "proposed_policy_hash": hashlib.sha256(proposed_robots.encode("utf-8")).hexdigest(),
        "per_bot_diff": per_bot,
        "label": "SIMULATION - site not changed",
    }


@mcp.tool()
def seo_audit_v2(
    url: str,
    language: str = "en",
    recommendation_limit: int = 10,
    crawl: bool = False,
    max_pages: int = 25,
    timeout: float = 5.0,
    render: bool = False,
    ga_property: str | None = None,
    gsc_site: str | None = None,
) -> dict:
    """Audit one public page for SEO best-practice gaps without mutation or credentials.

    With ``crawl=True`` a bounded same-origin crawl adds cross-page checks
    (broken links, duplicate metadata, redirect chains, internal nofollow,
    and insecure HTTP links with affected page URLs).
    ``render=True`` uses a headless browser for JS-driven pages.
    ``ga_property`` / ``gsc_site`` enable GA4/Search Console analytics checks
    using the service account stored via `agentready credentials set`.
    ``timeout`` is the maximum wait for each website network request.
    """
    report = audit_seo(
        url,
        allow_private=False,
        recommendation_limit=recommendation_limit,
        language=language,
        crawl=crawl,
        max_pages=max_pages,
        timeout=timeout,
        render=render,
        ga_property=ga_property,
        gsc_site=gsc_site,
    )
    payload = report.to_dict()
    saved_path = save_report(payload, target=url, surface="mcp-seo", fmt="json")
    logger.info("MCP report saved path=%s", saved_path)
    return payload


@mcp.tool()
def provider_enrichment_v2(
    provider: str,
    cached_metrics: list[dict] | None = None,
    scope: str | None = None,
) -> dict:
    """Normalize a bounded cached provider fixture without accepting credentials.

    Live provider calls belong to the trusted local HTTP/CLI workflow. MCP can
    safely inspect deterministic cached PageSpeed, GA4, GSC, or URL Inspection
    observations and keeps them explicitly outside core scoring.
    """
    supported = {"pagespeed", "ga4", "gsc", "url-inspection"}
    if provider not in supported:
        raise ValueError("unsupported provider")
    normalized_scope = ProviderService.validate_scope(provider, scope) if provider in {"ga4", "gsc", "url-inspection"} else scope
    metrics = tuple(
        ExternalMetric(
            provider,
            str(item["name"]),
            item.get("value"),
            item.get("unit"),
            str(item.get("source", "cached-fixture")),
            str(item.get("version", "unknown")),
            str(item["observed_at"]),
        )
        for item in (cached_metrics or [])[:500]
        if isinstance(item, dict) and item.get("name") and item.get("observed_at")
    )
    if not metrics:
        return {
            "provider": provider,
            "status": ProviderStatus.NOT_REQUESTED.value,
            "detail": "no cached observations supplied; credentials remain in the local OS vault",
            "metrics": [],
            "from_cache": False,
        }
    # Route fixture normalization through the same service used by the trusted
    # local CLI/API.  The temporary in-memory run keeps MCP read-only and does
    # not expose credentials or write project data.
    from .audit_core.store import MemorySiteStore, RunRecord
    fixture_run = "mcp-provider-" + hashlib.sha256(
        (provider + (normalized_scope or "")).encode("utf-8")
    ).hexdigest()[:24]
    store = MemorySiteStore()
    store.begin_run(RunRecord(fixture_run, "mcp-provider", "mcp", "provider-fixture"))
    service_result = ProviderService(store).enrich(
        fixture_run,
        provider,
        config=ProviderConfig(enabled=False, explicit_operation=True),
        cached=metrics,
        scope=normalized_scope,
    )
    result = service_result.to_dict()
    if normalized_scope:
        result["scope"] = normalized_scope
    logger.info("MCP provider fixture normalized provider=%s metrics=%d", provider, len(metrics))
    return result


@mcp.tool()
def sitemap_reconcile_v2(
    run_id: str,
    documents: list[str],
    origin: str,
    category: str = "sitemap_only",
    cursor: str | None = None,
    limit: int = 100,
    export_format: str | None = None,
) -> dict:
    """Reconcile caller-supplied sitemap XML with a stored run, without fetching."""
    from . import server as server_module
    request = server_module.SitemapReconciliationRequest(
        documents=documents[:32], origin=origin, category=category,
        cursor=cursor, limit=limit, format=export_format or "json",
    )
    return server_module.sitemap_reconcile_endpoint(run_id, request)


@mcp.tool()
def custom_rules_debug_v2(
    run_id: str,
    rules: str | dict,
    url: str = "",
    url_key: str | None = None,
) -> dict:
    """Debug declarative rules against a saved representation; never refetches a page."""
    from . import server as server_module
    request = server_module.CustomRulesRequest(
        rules=rules, url=url, url_key=url_key or url, run_id=run_id,
    )
    return server_module.custom_rules_debug_endpoint(request)


@mcp.tool()
def link_graph_v2(
    run_id: str,
    origin: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
    dead_end: bool | None = None,
    disconnected: bool | None = None,
) -> dict:
    """Read a bounded link-graph projection from an existing v2 run."""
    from . import server as server_module
    return server_module.audit_v2_graph_endpoint(
        run_id, origin=origin, cursor=cursor, limit=max(1, min(limit, 1000)),
        dead_end=dead_end, disconnected=disconnected,
    )


@mcp.tool()
def duplicate_clusters_v2(
    run_id: str,
    kind: str = "all",
    limit: int = 100,
    cursor: str | None = None,
    threshold: int = 3,
) -> dict:
    """Read bounded exact/near duplicate clusters from an existing v2 run."""
    from . import server as server_module
    if kind not in {"all", "exact", "near"}:
        raise ValueError("kind must be all, exact, or near")
    return server_module.audit_v2_duplicates_endpoint(
        run_id, cursor=cursor, limit=max(1, min(limit, 1000)),
        kind=kind, threshold=max(0, min(threshold, 64)),
    )


@mcp.tool()
def priority_v2(
    run_id: str,
    origin: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
) -> dict:
    """Read bounded page priorities and factor breakdown from an existing run."""
    from . import server as server_module
    return server_module.audit_v2_priority_endpoint(
        run_id, cursor=cursor, limit=max(1, min(limit, 1000)), origin=origin,
    )


@mcp.tool()
def projects_v2(project_id: str | None = None, include_history: bool = False, limit: int = 100) -> dict:
    """Read local project metadata and optional bounded run history; no mutations."""
    from . import server as server_module
    from .projects import ProjectService, project_run_to_dict, project_to_dict
    service = ProjectService(server_module._project_store())
    projects = [service.get(project_id)] if project_id else list(service.list())
    result = {"items": []}
    for project in projects[: max(1, min(limit, 1000))]:
        item = project_to_dict(project)
        if include_history:
            item["runs"] = [project_run_to_dict(run) for run in service.history(project.project_id, limit=max(1, min(limit, 1000)))]
        result["items"].append(item)
    return result


@mcp.tool()
def schedules_v2(project_id: str | None = None, schedule_id: str | None = None, include_executions: bool = False, limit: int = 100) -> dict:
    """Read local schedules, leases and execution history without starting the worker."""
    from . import server as server_module
    from .schedules import ScheduleService
    service = ScheduleService(server_module._project_store())
    schedules = [service.get(schedule_id)] if schedule_id else list(service.list(project_id))
    result = {"items": []}
    for schedule in schedules[: max(1, min(limit, 1000))]:
        item = asdict(schedule)
        if include_executions:
            item["executions"] = [asdict(execution) for execution in list(server_module._project_store().iter_schedule_executions(schedule.schedule_id))[: max(1, min(limit, 1000))]]
        result["items"].append(item)
    return result


@mcp.tool()
def run_inventory_v2(
    run_id: str,
    kind: str = "pages",
    limit: int = 100,
    cursor: str | None = None,
    search: str | None = None,
    sort_by: str | None = None,
    descending: bool = False,
    export_format: str | None = None,
) -> dict:
    """Query or export one bounded typed inventory projection for a v2 run."""
    from . import server as server_module

    store = server_module._V2_RUNS.get(run_id)
    response = AuditService().query_inventory(
        InventoryRequest(run_id, kind=kind, limit=limit, cursor=cursor, search=search, sort_by=sort_by, descending=descending),
        store=store,
    )
    payload = {"run_id": response.run_id, "kind": response.kind, "items": [server_module._inventory_item(item) for item in response.items], "next_cursor": response.next_cursor, "total": response.total}
    if export_format:
        from .workflows import inventory_query
        payload["export"] = export_query(QueryService(store), inventory_query(InventoryRequest(run_id, kind=kind, limit=limit, cursor=cursor, search=search, sort_by=sort_by, descending=descending)), format=export_format, limit=1000)
        payload["export_format"] = export_format
    logger.debug("MCP inventory query run_id=%s kind=%s limit=%d", run_id, kind, limit)
    return payload


@mcp.tool()
def audit_findings(
    url: str,
    mode: str = "readiness",
    preset: str = "all",
    language: str = "en",
    recommendation_limit: int = 10,
) -> dict:
    """Return only optimization gaps for a coding agent.

    Runs a canonical readiness audit (mode="readiness") or a single-page SEO audit
    (mode="seo") and returns each failed/warned check with a localized
    explanation of why it matters, observed evidence, and fix instructions.
    """
    logger.debug("audit_findings: url=%s mode=%s lang=%s", url, mode, language)
    if mode == "seo":
        report = audit_seo(
            url,
            allow_private=False,
            recommendation_limit=recommendation_limit,
            language=language,
        )
        return build_findings(report, language)
    if mode != "readiness":
        raise ValueError("unsupported mode: expected 'readiness' or 'seo'")
    report = audit_v2(url, preset=preset, language=language)
    return build_findings(report, language)


@mcp.tool()
def remediation_plan(
    url: str,
    mode: str = "readiness",
    preset: str = "all",
    language: str = "en",
    recommendation_limit: int = 10,
) -> dict:
    """Return a prioritized step-by-step fix plan for a coding agent.

    Each step contains fix instructions, a ready-to-use agent prompt, a
    verification command and reference links, ordered by impact/effort.
    """
    logger.debug("remediation_plan: url=%s mode=%s lang=%s", url, mode, language)
    if mode == "seo":
        report = audit_seo(
            url,
            allow_private=False,
            recommendation_limit=recommendation_limit,
            language=language,
        )
        return build_remediation_plan(report, language)
    if mode != "readiness":
        raise ValueError("unsupported mode: expected 'readiness' or 'seo'")
    report = audit_v2(url, preset=preset, language=language)
    return build_remediation_plan(report, language)


@mcp.tool()
def mobile_audit_v2(
    urls: list[str],
    render: bool = False,
    language: str = "en",
    recommendation_limit: int = 10,
    timeout: float = 5.0,
) -> dict:
    """Audit one or more public pages for mobile-friendliness (Google Mobile-Friendly signals).

    Returns per-page and aggregate scores with static HTML/CSS checks and,
    when ``render=True``, Playwright-rendered viewport/tap-target/font metrics.
    ``timeout`` is the maximum wait for each website network request.
    """
    logger.debug("mobile_audit: urls=%d render=%s lang=%s", len(urls), render, language)
    report = audit_mobile(
        urls,
        render=render,
        allow_private=False,
        recommendation_limit=recommendation_limit,
        timeout=timeout,
        language=language,
    )
    return report.to_dict()


@mcp.tool()
def mobile_findings(
    url: str,
    render: bool = False,
    language: str = "en",
    recommendation_limit: int = 10,
    timeout: float = 5.0,
) -> dict:
    """Return only the mobile-friendliness gaps for a coding agent (single page)."""
    logger.debug("mobile_findings: url=%s render=%s lang=%s", url, render, language)
    report = audit_mobile(
        [url],
        render=render,
        allow_private=False,
        recommendation_limit=recommendation_limit,
        timeout=timeout,
        language=language,
    )
    return build_findings(report.pages[0], language)


@mcp.tool()
def mobile_remediation_plan(
    url: str,
    render: bool = False,
    language: str = "en",
    recommendation_limit: int = 10,
    timeout: float = 5.0,
) -> dict:
    """Return a prioritized mobile-friendliness fix plan for a coding agent (single page)."""
    logger.debug("mobile_remediation_plan: url=%s render=%s lang=%s", url, render, language)
    report = audit_mobile(
        [url],
        render=render,
        allow_private=False,
        recommendation_limit=recommendation_limit,
        timeout=timeout,
        language=language,
    )
    return build_remediation_plan(report.pages[0], language)


def _run_ai(
    *,
    operation: str,
    target: str | None,
    report: dict | None,
    mode: str,
    language: str,
    model: str | None = None,
    message: str | None = None,
    history: list[dict[str, str]] | None = None,
    provider_timeout: float | None = None,
    provider_max_retries: int | None = None,
) -> dict:
    import asyncio

    from .ai_assistant import AIAssistant
    from .ai_models import AssistantRequest, ConversationMessage
    from .ai_provider import OpenAICompatibleProvider
    from .config import active_ai_provider, load_config

    cfg, _ = load_config()
    ai_cfg = cfg["ai"]
    selected_provider = active_ai_provider(ai_cfg)
    if not ai_cfg["enabled"] or not ai_cfg["transport_enabled"]:
        raise ValueError("AI assistant transport is disabled")
    if report is None:
        if not target:
            raise ValueError("target or report is required")
        report = audit_seo(target, allow_private=False, language=language).to_dict()
    messages = tuple(ConversationMessage(item["role"], item["content"]) for item in (history or [])[:ai_cfg["history_limit"]])
    request = AssistantRequest(
        operation=operation,
        mode=mode,
        language=language,
        target=target,
        report=report,
        message=message,
        history=messages,
    )
    provider = OpenAICompatibleProvider(
        base_url=selected_provider["base_url"],
        credential_id=selected_provider["credential_id"],
        timeout=provider_timeout if provider_timeout is not None else ai_cfg["timeout"],
        max_retries=provider_max_retries if provider_max_retries is not None else ai_cfg["max_retries"],
        allow_loopback_http=ai_cfg["allow_loopback_http"],
    )
    return asyncio.run(AIAssistant(provider, context_limit=ai_cfg["context_limit"], max_concurrent=ai_cfg["max_concurrent"]).run(request, model=model or selected_provider.get("model") or ai_cfg["model"])).to_dict()


@mcp.tool()
def ai_recommend(
    target: str | None = None,
    report: dict | None = None,
    mode: str = "both",
    language: str = "en",
    model: str | None = None,
    provider_timeout: float | None = None,
    provider_max_retries: int | None = None,
) -> dict:
    """Generate recommendations; timeout is per provider attempt and retries are extra attempts."""
    return _run_ai(operation="recommend", target=target, report=report, mode=mode, language=language, model=model, provider_timeout=provider_timeout, provider_max_retries=provider_max_retries)


@mcp.tool()
def ai_chat(
    message: str,
    target: str | None = None,
    report: dict | None = None,
    mode: str = "both",
    language: str = "en",
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
    provider_timeout: float | None = None,
    provider_max_retries: int | None = None,
) -> dict:
    """Run one chat turn; timeout is per provider attempt and retries are extra attempts."""
    return _run_ai(operation="chat", target=target, report=report, mode=mode, language=language, model=model, message=message, history=history, provider_timeout=provider_timeout, provider_max_retries=provider_max_retries)


def main(host: str = "127.0.0.1", port: int = 8766) -> None:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        logger.error("MCP server must bind to loopback for the unauthenticated local transport")
        raise ValueError("MCP server is loopback-only")
    logger.info("Starting MCP server: host=%s port=%s", host, port)
    mcp.run(transport="streamable-http", host=host, port=port, streamable_http_path="/mcp", json_response=True)


if __name__ == "__main__":
    main()
