"""Shared application entry point for bounded v2 audits."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from . import __version__
from .audit_core import AuditRunContext, CollectedPage, FactView, RunSnapshot, RunState
from .crawl_profiles import HARD_CAPS, resolve_profile
from .crawler import AsyncCrawler, CrawlResult, CrawlScope
from .discovery import (
    RobotsSitemapSource,
    SingleUrlSource,
    SitemapSource,
    UrlListSource,
    discovery_plan_hash,
)
from .egress import EgressPolicy, TrustedLocalCredentialContext
from .fetcher import Fetcher, FetchTransport
from .http import CachedHttpTransport, HttpClient
from .report_v2 import (
    AuditReport,
    Coverage,
    Finding,
    FindingEvidence,
    FindingStatus,
)
from .target import parse_target
from .workflows import (
    InventoryRequest,
    InventoryResponse,
    InventoryWorkflow,
    workflow_capabilities,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuditRequest:
    """Transport-independent v2 audit configuration."""

    target: str
    preset: str = "all"
    profile: str = "standard"
    max_pages: int = 25
    timeout: float = 5.0
    limits: Mapping[str, Any] = field(default_factory=dict)
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    selected_urls: tuple[str, ...] = ()
    discovery_kind: str = "single"
    discovery_urls: tuple[str, ...] = ()
    discovery_sitemap_xml: str | None = None
    discovery_sitemap_urls: tuple[str, ...] = ()
    discovery_limit: int = 1000
    render: bool = False
    provider: str | None = None
    ga_property: str | None = None
    gsc_site: str | None = None
    language: str = "en"
    parent_run_id: str | None = None
    allow_private: bool = False
    transport: FetchTransport | None = None
    store: Any | None = None
    run_rules: bool = True
    crawl: bool = False
    recommendation_limit: int = 10
    mode: str = "readiness"
    verify: bool = True
    max_redirects: int = 5
    max_bytes: int = 5 * 1024 * 1024
    progress_callback: Callable[[dict[str, int | str]], None] | None = field(default=None, compare=False, repr=False)
    trusted_origin: str | None = None
    credential_ref: str | None = None
    credential_headers: Mapping[str, str] = field(default_factory=dict, compare=False, repr=False)
    security_context: TrustedLocalCredentialContext | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.target.strip():
            raise ValueError("audit target is required")
        if self.max_pages < 0:
            raise ValueError("max_pages must not be negative")
        if self.max_pages == 0:
            object.__setattr__(self, "max_pages", HARD_CAPS.max_pages)
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.mode not in {"readiness", "seo", "mobile"}:
            raise ValueError("mode must be readiness, seo, or mobile")
        if self.recommendation_limit < 0:
            raise ValueError("recommendation_limit must not be negative")
        if self.max_redirects < 0:
            raise ValueError("max_redirects must not be negative")
        if self.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if self.discovery_kind not in {"single", "list", "sitemap", "robots-sitemap", "crawl"}:
            raise ValueError("discovery_kind must be single, list, sitemap, robots-sitemap, or crawl")
        if self.discovery_limit <= 0 or self.discovery_limit > 100_000:
            raise ValueError("discovery_limit must be between 1 and 100000")
        if self.discovery_kind == "sitemap" and not self.discovery_sitemap_xml:
            raise ValueError("discovery_sitemap_xml is required for sitemap discovery")
        if bool(self.trusted_origin) != bool(self.security_context):
            raise ValueError("trusted_origin and security_context must be provided together")
        if self.security_context and not self.credential_headers:
            raise ValueError("trusted authenticated audits require resolved credential headers")
        if self.security_context and self.render:
            raise ValueError("trusted authenticated audits cannot enable rendered browser collection")
        if self.security_context and self.mode != "readiness":
            raise ValueError("trusted authenticated audits are limited to readiness mode")

    def configuration(self) -> dict[str, Any]:
        """Return the non-secret configuration used for run identity."""
        return {
            "target": self.target,
            "mode": self.mode,
            "preset": self.preset,
            "profile": self.profile,
            "max_pages": self.max_pages,
            "timeout": self.timeout,
            "limits": dict(self.limits),
            "include": list(self.include),
            "exclude": list(self.exclude),
            "selected_urls": list(self.selected_urls),
            "discovery_kind": self.discovery_kind,
            "discovery_urls": list(self.discovery_urls),
            "discovery_sitemap_hash": hashlib.sha256(self.discovery_sitemap_xml.encode("utf-8")).hexdigest() if self.discovery_sitemap_xml else None,
            "discovery_sitemap_urls": list(self.discovery_sitemap_urls),
            "discovery_limit": self.discovery_limit,
            "render": self.render,
            "provider": self.provider,
            "ga_property": self.ga_property,
            "gsc_site": self.gsc_site,
            "language": self.language,
            "parent_run_id": self.parent_run_id,
            "run_rules": self.run_rules,
            "crawl": self.crawl,
            "recommendation_limit": self.recommendation_limit,
            "verify": self.verify,
            "max_redirects": self.max_redirects,
            "max_bytes": self.max_bytes,
            "trusted_origin": self.trusted_origin,
            "credential_ref": self.credential_ref,
            "trusted_auth": bool(self.security_context),
        }


@dataclass(frozen=True, slots=True)
class AuditResult:
    request: AuditRequest
    run: RunSnapshot
    crawl: CrawlResult
    report: AuditReport
    lineage_id: str
    seo_report: Any | None = None
    fact_views: tuple[FactView, ...] = ()
    mobile_report: Any | None = None
    discovery_plan_hash: str | None = None
    robots_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        projection = self.mobile_report or self.seo_report or self.report
        payload = projection.to_dict()
        payload["run"] = {
            "id": self.run.context.run_id,
            "state": self.run.state.value,
            "config_hash": self.run.context.config_hash,
            "parent_run_id": self.request.parent_run_id,
            "lineage_id": self.lineage_id,
        }
        payload["request"] = {
            "preset": self.request.preset,
            "profile": self.request.profile,
            "max_pages": self.request.max_pages,
            "timeout": self.request.timeout,
            "limits": dict(self.request.limits),
            "include": list(self.request.include),
            "exclude": list(self.request.exclude),
            "selected_urls": list(self.request.selected_urls),
            "render": self.request.render,
            "provider": self.request.provider,
            "language": self.request.language,
            "run_rules": self.request.run_rules,
        }
        if self.request.mode != "readiness":
            payload["request"]["mode"] = self.request.mode
        if self.request.crawl:
            payload["request"]["crawl"] = True
        if self.request.discovery_kind != "single" or self.request.discovery_limit != 1000:
            payload["request"]["discovery_kind"] = self.request.discovery_kind
            payload["request"]["discovery_limit"] = self.request.discovery_limit
        if self.discovery_plan_hash is not None and (self.request.discovery_kind != "single" or self.request.discovery_limit != 1000):
            payload["request"]["discovery_plan_hash"] = self.discovery_plan_hash
        if self.request.recommendation_limit != 10:
            payload["request"]["recommendation_limit"] = self.request.recommendation_limit
        return payload


class AuditService:
    """Run every v2 audit through one bounded application boundary."""

    @staticmethod
    def workflow_capabilities() -> dict[str, Any]:
        """Describe reusable v2 product workflows and their bounded contracts."""
        return workflow_capabilities(__version__)

    @staticmethod
    def query_inventory(request: InventoryRequest, *, store: Any) -> InventoryResponse:
        """Execute an inventory workflow through QueryService, never transport SQL."""
        response = InventoryWorkflow(store).execute(request)
        logger.info(
            "v2 inventory workflow run_id=%s kind=%s limit=%d rows=%d",
            request.run_id,
            request.kind,
            request.limit,
            len(response.items),
        )
        return response

    @staticmethod
    def _apply_check_limit(checks: list[Any], limits: Mapping[str, Any]) -> list[Any]:
        """Bound checks deterministically while keeping the catalog order."""
        limit = int(limits.get("check_limit", 0) or 0)
        if limit < 0 or limit > 500:
            raise ValueError("check_limit must be between 0 and 500")
        if limit and len(checks) > limit:
            logger.info("[FIX:audit-check-limit] checks=%d limit=%d", len(checks), limit)
            return checks[:limit]
        return checks

    @staticmethod
    def _fact_views(crawl: CrawlResult) -> tuple[FactView, ...]:
        """Project crawler output once for all downstream analyzers."""
        views = tuple(
            FactView(
                CollectedPage(
                    page.url,
                    page.depth,
                    page.status_code,
                    page.parsed.representation if page.parsed is not None else None,
                    page.parsed.facts if page.parsed is not None else None,
                    page.error,
                    page.headers,
                    page.body,
                    page.requested_url,
                )
            )
            for page in crawl.pages
        )
        logger.debug("collection fact views built pages=%d", len(views))
        return views

    @staticmethod
    def _discovery_seeds(target: str, request: AuditRequest) -> tuple[tuple[str, ...], str]:
        if request.discovery_kind == "single":
            source = SingleUrlSource(target)
            return (), discovery_plan_hash(source, limit=request.discovery_limit)
        elif request.discovery_kind == "list":
            source = UrlListSource(tuple(request.discovery_urls) or (target,))
        elif request.discovery_kind == "sitemap":
            source = SitemapSource(request.discovery_sitemap_xml or "", target)
        elif request.discovery_kind == "robots-sitemap":
            source = RobotsSitemapSource(target, tuple(request.discovery_sitemap_urls))
            return (), discovery_plan_hash(source, limit=request.discovery_limit)
        else:
            source = SingleUrlSource(target)
        urls = tuple(dict.fromkeys(source.discover(limit=request.discovery_limit)))
        return urls, discovery_plan_hash(source, limit=request.discovery_limit)

    def run(self, request: AuditRequest) -> AuditResult:
        if request.mode == "mobile":
            return self._run_mobile(request)
        if request.mode == "seo":
            return self._run_seo(request)
        from .plan_compiler import PlanCompiler
        from .registry import BY_ID

        target = parse_target(request.target).url
        execution_plan = PlanCompiler().compile(request)
        configuration = request.configuration()
        configuration["target"] = target
        context = AuditRunContext.create(
            target,
            configuration,
            tool_version=__version__,
            rule_catalog_version="v2",
            run_id=None,
        )
        logger.info(
            "audit request accepted run_id=%s config_hash=%s profile=%s max_pages=%d render=%s provider=%s",
            context.run_id,
            context.config_hash[:12],
            request.profile,
            request.max_pages,
            request.render,
            request.provider or "none",
        )
        logger.info(
            "audit execution plan run_id=%s plan_hash=%s capabilities=%s",
            context.run_id,
            execution_plan.config_hash[:12],
            ",".join(execution_plan.capabilities),
        )

        profile_overrides = {key: value for key, value in request.limits.items() if key != "check_limit"}
        profile_overrides["max_pages"] = request.max_pages
        profile_overrides["timeout"] = request.timeout
        profile = resolve_profile(request.profile, overrides=profile_overrides, hard_caps=HARD_CAPS)
        config = profile.config
        origin = parse_target(target).origin
        if request.security_context is not None:
            if request.trusted_origin != origin or not request.security_context.permits(target):
                raise ValueError("trusted authenticated audit target is outside the explicit trusted origin")
            logger.info(
                "trusted-local collection boundary run_id=%s origin=%s credential_ref=%s headers=%s",
                context.run_id,
                origin,
                request.credential_ref or "none",
                ",".join(sorted(request.credential_headers)),
            )
        policy = EgressPolicy(
            block_private=not request.allow_private and request.security_context is None,
            max_redirects=request.max_redirects,
            max_response_bytes=request.max_bytes,
            allowed_origins=frozenset({origin}),
        )
        discovered_seeds, discovery_hash = self._discovery_seeds(target, request)
        seeds = tuple(dict.fromkeys(self._validate_selected_urls(target, request.selected_urls or discovered_seeds)))
        if request.discovery_kind == "robots-sitemap":
            source = RobotsSitemapSource(target, tuple(request.discovery_sitemap_urls))

            async def discover_robots() -> tuple[str, ...]:
                async with Fetcher(policy=policy, timeout=request.timeout, transport=request.transport) as fetcher:
                    return await source.discover_from_fetcher(fetcher, limit=request.discovery_limit)

            seeds = tuple(dict.fromkeys(self._validate_selected_urls(target, asyncio.run(discover_robots()))))
        logger.info(
            "discovery plan run_id=%s kind=%s plan_hash=%s count=%d limit=%d",
            context.run_id,
            request.discovery_kind,
            discovery_hash[:12],
            len(seeds),
            request.discovery_limit,
        )
        check_include, scope_include = self._partition_filters(request.include, BY_ID)
        check_exclude, scope_exclude = self._partition_filters(request.exclude, BY_ID)
        logger.info(
            "[FIX:filter-contract] run_id=%s check_include=%s check_exclude=%s scope_include=%s scope_exclude=%s",
            context.run_id,
            check_include,
            check_exclude,
            scope_include,
            scope_exclude,
        )
        follow_links = request.discovery_kind in {"single", "crawl"} and not bool(request.selected_urls)
        scope = CrawlScope(
            seeds or (target,),
            allowed_origins=(origin,),
            include_rules=scope_include,
            exclude_rules=scope_exclude,
            follow_links=follow_links,
        )
        check_report = None
        robots_text = None
        rule_client = None
        crawler_transport = request.transport
        # The v2 service is the sole public readiness boundary.  The existing
        # rule implementations remain an internal adapter, but share the
        # collection client's cache with the crawler so a URL is fetched once.
        if request.run_rules and request.security_context is None and request.transport is None and request.preset in {"all", "content", "api", "ai-search"}:
            rule_client = HttpClient(timeout=request.timeout, allow_private=request.allow_private)
            crawler_transport = CachedHttpTransport(rule_client)
        try:
            crawler_kwargs = {
                "config": config,
                "policy": policy,
                "transport": crawler_transport,
                "store": request.store,
                "run_context": context,
                "render": request.render,
                "verify": request.verify,
            }
            if request.security_context is not None:
                crawler_kwargs["request_headers"] = dict(request.credential_headers)
                crawler_kwargs["security_context"] = request.security_context
            if request.progress_callback is not None:
                crawler_kwargs["progress_callback"] = request.progress_callback
            crawl = asyncio.run(
                AsyncCrawler(
                    scope,
                    **crawler_kwargs,
                ).crawl()
            )
            fact_views = self._fact_views(crawl)
            if rule_client is not None:
                from .report_v2 import report_from_checks
                from .scanner import scan

                logger.info("[FIX:collection-cache] running v2 readiness analyzers from shared collection cache run_id=%s preset=%s", context.run_id, request.preset)
                rule_engine_report = scan(
                    target,
                    preset=request.preset,
                    include=check_include,
                    exclude=check_exclude,
                    timeout=request.timeout,
                    allow_private=request.allow_private,
                    workers=max(1, int(config.concurrency)),
                    language=request.language,
                    client=rule_client,
                    fact_views=fact_views,
                )
                check_report = report_from_checks(target, self._apply_check_limit(list(rule_engine_report.checks), request.limits))
                cached_robots = rule_client.cached(f"{origin}/robots.txt")
                if cached_robots is not None and cached_robots.status_code == 200:
                    robots_text = cached_robots.text
                    logger.info(
                        "[FIX:robots-session] captured discovered robots policy run_id=%s bytes=%d",
                        context.run_id,
                        len(robots_text),
                    )
        finally:
            if rule_client is not None:
                rule_client.close()
        report = self._report(target, crawl, run_id=context.run_id, check_report=check_report)
        state = (
            RunState.PARTIAL
            if crawl.coverage.classification.value != "complete_within_scope"
            else RunState.COMPLETED
        )
        run = crawl.run or RunSnapshot(
            context,
            state,
            None,
            "crawl-partial" if state is RunState.PARTIAL else None,
        )
        lineage_id = request.parent_run_id or context.run_id
        logger.info(
            "audit run complete run_id=%s state=%s discovered=%d fetched=%d classification=%s",
            context.run_id,
            state.value,
            crawl.coverage.discovered,
            crawl.coverage.fetched,
            crawl.coverage.classification.value,
        )
        return AuditResult(request, run, crawl, report, lineage_id, fact_views=fact_views, discovery_plan_hash=discovery_hash, robots_text=robots_text)

    def _run_mobile(self, request: AuditRequest) -> AuditResult:
        """Collect one page once, then project static and rendered mobile facts."""
        from .browser_pool import BrowserPool, CapabilityUnavailableError
        from .http import CollectedHttpClient
        from .mobile_models import MobileReport
        from .mobile_scanner import MOBILE_SCHEMA, _audit_page
        from .mobile_scoring import rank_mobile_recommendations, score_mobile_checks
        from .models import utc_now_iso

        target = parse_target(request.target).url
        configuration = request.configuration()
        configuration["target"] = target
        context = AuditRunContext.create(
            target,
            configuration,
            tool_version=__version__,
            rule_catalog_version="mobile-v2",
            run_id=None,
        )
        profile = resolve_profile(
            request.profile,
            overrides={"max_pages": 1, "timeout": request.timeout},
            hard_caps=HARD_CAPS,
        )
        origin = parse_target(target).origin
        policy = EgressPolicy(
            block_private=not request.allow_private,
            max_redirects=request.max_redirects,
            max_response_bytes=request.max_bytes,
            allowed_origins=frozenset({origin}),
        )
        crawl = asyncio.run(
            AsyncCrawler(
                CrawlScope((target,), allowed_origins=(origin,), follow_links=False),
                config=profile.config,
                policy=policy,
                transport=request.transport,
                store=request.store,
                run_context=context,
                render=False,
                verify=request.verify,
            ).crawl()
        )
        fact_views = self._fact_views(crawl)
        replay_client = CollectedHttpClient(None, fact_views)

        async def analyze_page() -> Any:
            pool = None
            render_status = None
            if request.render:
                pool = BrowserPool(policy)
                try:
                    await pool.start()
                except CapabilityUnavailableError as exc:
                    render_status = (
                        "playwright not installed"
                        if exc.capability == "Playwright browser support"
                        else str(exc)
                    )
                    await pool.close()
                    pool = None
            try:
                return await _audit_page(
                    target,
                    render=request.render,
                    allow_private=request.allow_private,
                    recommendation_limit=request.recommendation_limit,
                    browser_pool=pool,
                    render_status=render_status,
                    client=replay_client,
                )
            finally:
                if pool is not None:
                    await pool.close()

        started_at = utc_now_iso()
        page = asyncio.run(analyze_page())
        score, categories = score_mobile_checks(page.checks)
        recommendations = rank_mobile_recommendations(
            page.checks,
            limit=request.recommendation_limit,
        )
        mobile_report = MobileReport(
            schema=MOBILE_SCHEMA,
            targets=[target],
            pages=[page],
            score=score,
            categories=categories,
            recommendations=recommendations,
            started_at=started_at,
            finished_at=utc_now_iso(),
            language=request.language,
        )
        report = self._report(target, crawl, run_id=context.run_id)
        state = (
            RunState.PARTIAL
            if crawl.coverage.classification.value != "complete_within_scope"
            else RunState.COMPLETED
        )
        run = crawl.run or RunSnapshot(
            context,
            state,
            None,
            "crawl-partial" if state is RunState.PARTIAL else None,
        )
        logger.info(
            "[FIX:mobile-collection] canonical mobile projection complete run_id=%s facts=%d checks=%d",
            context.run_id,
            len(fact_views),
            len(page.checks),
        )
        return AuditResult(
            request,
            run,
            crawl,
            report,
            request.parent_run_id or context.run_id,
            fact_views=fact_views,
            mobile_report=mobile_report,
        )

    def _run_seo(self, request: AuditRequest) -> AuditResult:
        """Run the canonical SEO path over one bounded crawler result."""
        from .models import Evidence, Remediation, utc_now_iso
        from .plan_compiler import PlanCompiler
        from .seo.engine import run_atomic_rules
        from .seo.evidence import evidence_from_parsed_page
        from .seo.site_rules import evaluate_site_rules
        from .seo_models import SeoCheckResult, SeoReport
        from .seo_recommendations import rank_recommendations
        from .seo_scoring import score_checks

        target = parse_target(request.target).url
        execution_plan = PlanCompiler().compile(request)
        configuration = request.configuration()
        configuration["target"] = target
        context = AuditRunContext.create(
            target,
            configuration,
            tool_version=__version__,
            rule_catalog_version="seo-v2-atomic",
            run_id=None,
        )
        profile_overrides = {key: value for key, value in request.limits.items() if key != "check_limit"}
        profile_overrides["max_pages"] = request.max_pages if request.crawl else 1
        profile_overrides["timeout"] = request.timeout
        profile = resolve_profile(request.profile, overrides=profile_overrides, hard_caps=HARD_CAPS)
        origin = parse_target(target).origin
        policy = EgressPolicy(
            block_private=not request.allow_private,
            max_redirects=request.max_redirects,
            max_response_bytes=request.max_bytes,
            allowed_origins=frozenset({origin}),
        )
        seeds = tuple(dict.fromkeys(self._validate_selected_urls(target, request.selected_urls)))
        scope = CrawlScope(
            seeds or (target,),
            allowed_origins=(origin,),
            follow_links=request.crawl and not bool(seeds),
        )
        logger.info(
            "SEO canonical execution run_id=%s plan_hash=%s crawl=%s",
            context.run_id,
            execution_plan.config_hash[:12],
            request.crawl,
        )
        crawler_kwargs = {
            "config": profile.config,
            "policy": policy,
            "transport": request.transport,
            "store": request.store,
            "run_context": context,
            "render": request.render,
            "verify": request.verify,
        }
        if request.progress_callback is not None:
            crawler_kwargs["progress_callback"] = request.progress_callback
        crawl = asyncio.run(
            AsyncCrawler(
                scope,
                **crawler_kwargs,
            ).crawl()
        )
        checks: list[SeoCheckResult] = []
        aliases = {
            "page-metadata": "metadata", "page-indexability": "indexability",
            "duplicate-metadata": "duplicate-metadata-site", "broken-links": "link-architecture-site",
            "redirect-chains": "redirect-inventory-site", "internal-nofollow": "link-architecture-site",
            "link-counts": "link-depth-site", "insecure-links-pages": "link-architecture-site",
        }
        requested_ids = {aliases.get(value, value) for value in request.include}
        atomic_catalog = {"page-available", "metadata", "indexability", "canonical", "hreflang", "jsonld", "title-length"}
        atomic_ids = {value for value in requested_ids if value in atomic_catalog}
        excluded_ids = set(request.exclude)
        fact_views = self._fact_views(crawl)
        for view in fact_views:
            if view.facts is None:
                continue
            representation = view.representation
            content_type = representation.content_type.split(";", 1)[0].strip().lower() if representation is not None else ""
            if representation is not None and representation.content_type != content_type:
                logger.info("[FIX:seo-content-type] normalized content type url=%s raw=%s normalized=%s", view.url, representation.content_type, content_type)
            evidence = evidence_from_parsed_page(
                view,
                url=view.url,
                final_url=view.url,
                status_code=view.page.status_code or 0,
                content_type=content_type,
            )
            for finding in run_atomic_rules(evidence):
                if atomic_ids and finding.rule.id not in atomic_ids:
                    continue
                if finding.rule.id in excluded_ids:
                    continue
                checks.append(
                    SeoCheckResult(
                        id=finding.rule.id,
                        title=finding.rule.title,
                        category=finding.rule.category,
                        status=finding.status,
                        scored=finding.scored,
                        details=finding.details,
                        evidence=[Evidence(action=finding.details, url=view.url, finding=finding.reason)],
                    )
                )
        stored_links = None
        if request.store is not None:
            stored_links = tuple(request.store.iter_link_occurrences(context.run_id))
        checks.extend(
            evaluate_site_rules(
                crawl.pages,
                link_occurrences=stored_links,
                origin=origin,
                coverage_complete=crawl.coverage.classification.value == "complete_within_scope",
                sitemap_urls=tuple(value for value in request.limits.get("sitemap_urls", ()) if isinstance(value, str)),
                robots_policy=request.limits.get("robots_policy"),
            )
        )
        if request.ga_property or request.gsc_site:
            from .seo_analytics import ANALYTICS_CHECKS, AnalyticsContext

            analytics_context = AnalyticsContext(request.ga_property, request.gsc_site)
            for check in ANALYTICS_CHECKS:
                try:
                    checks.append(check(target, analytics_context))
                except Exception as exc:  # noqa: BLE001 - provider boundary is typed into the report.
                    logger.error("[FIX:seo-provider] analytics check failed check=%s error=%s", check.__name__, exc)
                    checks.append(SeoCheckResult(
                        id=check.__name__.replace("check_", "").replace("_", "-"),
                        title=check.__name__.replace("check_", "").replace("_", " ").title(),
                        category="analytics", status="error", scored=True, details=str(exc),
                    ))
        if requested_ids:
            checks = [item for item in checks if item.id in requested_ids or item.category == "analytics"]
        checks = self._apply_check_limit(checks, request.limits)
        coverage_status = "pass" if crawl.coverage.classification.value == "complete_within_scope" else "warn"
        checks.append(
            SeoCheckResult(
                id="crawl-coverage",
                title="Crawl coverage",
                category="crawlability",
                status=coverage_status,
                scored=False,
                details=(
                    f"Crawl classified as {crawl.coverage.classification.value}; "
                    f"fetched {crawl.coverage.fetched} URL(s)."
                ),
                evidence=[Evidence(
                    action="inspect bounded crawl coverage",
                    url=target,
                    finding=f"discovered={crawl.coverage.discovered}, fetched={crawl.coverage.fetched}",
                )],
            )
        )
        # Keep SEO reports actionable: atomic/site rules share the canonical
        # check model, but their remediation is produced at this boundary so
        # every fail/warn/error can feed both recommendations and instructions.
        for check in checks:
            if check.status in {"fail", "warn", "error"} and check.remediation is None:
                check.remediation = Remediation(
                    summary=check.details,
                    rerun_command=f"agentready audit --mode seo {target!r} --include {check.id}",
                    references=[],
                    agent_prompt=(
                        f"Fix the SEO finding `{check.id}` for {target!r}: {check.details}. "
                        f"Rerun the SEO audit with --include {check.id}."
                    ),
                )
        logger.info(
            "[FIX:seo-remediation] actionable checks=%d",
            sum(check.remediation is not None for check in checks if check.status in {"fail", "warn", "error"}),
        )
        score, categories = score_checks(checks)
        started_at = utc_now_iso()
        seo_report = SeoReport(
            schema="agentready.seo.v2",
            target=target,
            origin=origin,
            checks=checks,
            score=score,
            categories=categories,
            recommendations=rank_recommendations(checks, limit=request.recommendation_limit),
            started_at=started_at,
            finished_at=utc_now_iso(),
            language=request.language,
            run_id=context.run_id,
            config_hash=context.config_hash,
            coverage={
                "classification": crawl.coverage.classification.value,
                "discovered": crawl.coverage.discovered,
                "fetched": crawl.coverage.fetched,
                "max_pages_hit": crawl.coverage.max_pages_hit,
            },
            inventory={
                "pages": len(crawl.pages),
                "links": sum(len(page.parsed.facts.links) for page in crawl.pages if page.parsed and page.parsed.facts),
                "resources": sum(len(page.parsed.facts.resources) for page in crawl.pages if page.parsed and page.parsed.facts),
                "images": sum(len(page.parsed.facts.images) for page in crawl.pages if page.parsed and page.parsed.facts),
                "checks": len(checks),
            },
        )
        report = self._report(target, crawl, run_id=context.run_id)
        state = RunState.PARTIAL if crawl.coverage.classification.value != "complete_within_scope" else RunState.COMPLETED
        run = crawl.run or RunSnapshot(context, state, None, "crawl-partial" if state is RunState.PARTIAL else None)
        lineage_id = request.parent_run_id or context.run_id
        logger.info(
            "SEO canonical execution complete run_id=%s checks=%d score=%d",
            context.run_id,
            len(checks),
            score,
        )
        return AuditResult(request, run, crawl, report, lineage_id, seo_report, self._fact_views(crawl))

    @staticmethod
    def _validate_selected_urls(target: str, selected_urls: tuple[str, ...]) -> tuple[str, ...]:
        if not selected_urls:
            return ()
        origin = parse_target(target).origin
        validated: list[str] = []
        for url in selected_urls:
            candidate = parse_target(url).url
            if parse_target(candidate).origin != origin:
                raise ValueError("selected rescan URLs must remain within the target origin")
            validated.append(candidate)
        return tuple(validated)

    @staticmethod
    def _report(
        target: str,
        crawl: CrawlResult,
        *,
        run_id: str | None = None,
        check_report: AuditReport | None = None,
    ) -> AuditReport:
        coverage = Coverage(
            total_rules=1,
            evaluated_rules=1,
            applicable_rules=1,
            complete_rules=1 if crawl.coverage.classification.value == "complete_within_scope" else 0,
            urls_discovered=crawl.coverage.discovered,
            urls_fetched=crawl.coverage.fetched,
            max_pages_hit=crawl.coverage.max_pages_hit,
            classification=crawl.coverage.classification.value,
        )
        status = (
            FindingStatus.PASS
            if crawl.coverage.classification.value == "complete_within_scope"
            else FindingStatus.WARN
        )
        finding = Finding(
            "crawl-coverage",
            "Crawl coverage",
            status,
            f"Crawl classified as {crawl.coverage.classification.value}; fetched {crawl.coverage.fetched} URL(s).",
            (
                FindingEvidence(
                    "crawl-coverage",
                    f"discovered={crawl.coverage.discovered}, fetched={crawl.coverage.fetched}, "
                    f"max_pages_hit={crawl.coverage.max_pages_hit}",
                    target,
                ),
            ),
        )
        findings = ((check_report.findings if check_report else ()) + (finding,))
        if check_report:
            coverage = Coverage(
                total_rules=check_report.coverage.total_rules + 1,
                evaluated_rules=check_report.coverage.evaluated_rules + 1,
                applicable_rules=check_report.coverage.applicable_rules + 1,
                complete_rules=check_report.coverage.complete_rules + (1 if status is FindingStatus.PASS else 0),
                urls_discovered=crawl.coverage.discovered,
                urls_fetched=crawl.coverage.fetched,
                max_pages_hit=crawl.coverage.max_pages_hit,
                classification=crawl.coverage.classification.value,
            )
        evidence = check_report.evidence if check_report else ()
        report = AuditReport(target, findings, coverage, evidence=evidence, run_id=run_id)
        logger.info("[FIX:v2-report] target=%s findings=%d score=%d", target, len(report.findings), report.score)
        return report

    @staticmethod
    def _partition_filters(
        values: tuple[str, ...],
        check_catalog: Mapping[str, Any],
    ) -> tuple[list[str], tuple[str, ...]]:
        """Separate check IDs from URL scope rules at the v2 boundary."""
        checks: list[str] = []
        scope: list[str] = []
        for value in values:
            if value in check_catalog:
                checks.append(value)
            elif "://" in value or value.startswith(("/", "*")):
                scope.append(value)
            else:
                raise ValueError(f"Unknown v2 check or scope rule: {value}")
        return checks, tuple(scope)
