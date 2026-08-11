"""Shared application entry point for bounded v2 audits."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from . import __version__
from .audit_core import AuditRunContext, RunSnapshot, RunState
from .crawl_profiles import HARD_CAPS, resolve_profile
from .crawler import AsyncCrawler, CrawlResult, CrawlScope
from .egress import EgressPolicy
from .fetcher import FetchTransport
from .report_v2 import (
    AuditReport,
    Coverage,
    Finding,
    FindingEvidence,
    FindingStatus,
)
from .target import parse_target

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
    render: bool = False
    provider: str | None = None
    language: str = "en"
    parent_run_id: str | None = None
    allow_private: bool = False
    transport: FetchTransport | None = None
    store: Any | None = None

    def __post_init__(self) -> None:
        if not self.target.strip():
            raise ValueError("audit target is required")
        if self.max_pages <= 0:
            raise ValueError("max_pages must be positive")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")

    def configuration(self) -> dict[str, Any]:
        """Return the non-secret configuration used for run identity."""
        return {
            "target": self.target,
            "preset": self.preset,
            "profile": self.profile,
            "max_pages": self.max_pages,
            "timeout": self.timeout,
            "limits": dict(self.limits),
            "include": list(self.include),
            "exclude": list(self.exclude),
            "selected_urls": list(self.selected_urls),
            "render": self.render,
            "provider": self.provider,
            "language": self.language,
            "parent_run_id": self.parent_run_id,
        }


@dataclass(frozen=True, slots=True)
class AuditResult:
    request: AuditRequest
    run: RunSnapshot
    crawl: CrawlResult
    report: AuditReport
    lineage_id: str

    def to_dict(self) -> dict[str, Any]:
        payload = self.report.to_dict()
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
        }
        return payload


class AuditService:
    """Run every v2 audit through one bounded application boundary."""

    def run(self, request: AuditRequest) -> AuditResult:
        from .plan_compiler import PlanCompiler

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

        profile_overrides = dict(request.limits)
        profile_overrides["max_pages"] = request.max_pages
        profile_overrides["timeout"] = request.timeout
        profile = resolve_profile(request.profile, overrides=profile_overrides, hard_caps=HARD_CAPS)
        config = profile.config
        origin = parse_target(target).origin
        policy = EgressPolicy(
            block_private=not request.allow_private,
            allowed_origins=frozenset({origin}),
        )
        seeds = tuple(dict.fromkeys(self._validate_selected_urls(target, request.selected_urls)))
        scope = CrawlScope(
            seeds or (target,),
            allowed_origins=(origin,),
            include_rules=request.include,
            exclude_rules=request.exclude,
            follow_links=not bool(seeds),
        )
        crawl = asyncio.run(
            AsyncCrawler(
                scope,
                config=config,
                policy=policy,
                transport=request.transport,
                store=request.store,
                run_context=context,
                render=request.render,
            ).crawl()
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
        lineage_id = request.parent_run_id or context.run_id
        logger.info(
            "audit run complete run_id=%s state=%s discovered=%d fetched=%d classification=%s",
            context.run_id,
            state.value,
            crawl.coverage.discovered,
            crawl.coverage.fetched,
            crawl.coverage.classification.value,
        )
        return AuditResult(request, run, crawl, report, lineage_id)

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
    def _report(target: str, crawl: CrawlResult, *, run_id: str | None = None) -> AuditReport:
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
        return AuditReport(target, (finding,), coverage, run_id=run_id)
