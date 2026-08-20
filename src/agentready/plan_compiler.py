"""Deterministic, network-free compilation of an audit execution plan."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .audit_service import AuditRequest
from .crawl_profiles import resolve_request_profile


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Bounded execution inputs shared by all transport adapters."""

    target: str
    mode: str
    profile: str
    max_pages: int
    timeout: float
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    render: bool
    provider: str | None
    language: str
    capabilities: tuple[str, ...]
    config_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "mode": self.mode,
            "profile": self.profile,
            "max_pages": self.max_pages,
            "timeout": self.timeout,
            "include": list(self.include),
            "exclude": list(self.exclude),
            "render": self.render,
            "provider": self.provider,
            "language": self.language,
            "capabilities": list(self.capabilities),
            "config_hash": self.config_hash,
        }


class PlanCompiler:
    """Compile requests without touching the network or optional providers."""

    def compile(self, request: AuditRequest) -> ExecutionPlan:
        profile = resolve_request_profile(
            request.profile,
            max_pages=request.max_pages if request.mode != "seo" or request.crawl else 1,
            timeout=request.timeout,
            limits=dict(request.limits),
            full_discovered=request.full_discovered,
        )
        capabilities = ["crawl", "static-facts", "coverage"]
        if request.mode == "seo":
            capabilities.extend(("seo", "parsed-facts", "atomic-seo-rules"))
        elif request.mode == "mobile":
            capabilities.extend(("mobile", "mobile-static-rules"))
        if request.render:
            capabilities.append("rendered-dom")
        if request.provider:
            capabilities.append(f"provider:{request.provider}")
        payload = {
            "target": request.target,
            "mode": request.mode,
            "preset": request.preset,
            "profile": profile.name,
            "config": profile.config.__dict__ if hasattr(profile.config, "__dict__") else repr(profile.config),
            "max_pages": request.max_pages,
            "timeout": request.timeout,
            "include": list(request.include),
            "exclude": list(request.exclude),
            "render": request.render,
            "provider": request.provider,
            "crawl": request.crawl,
            "language": request.language,
            "capabilities": capabilities,
        }
        config_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        return ExecutionPlan(
            request.target,
            request.mode,
            profile.name,
            request.max_pages,
            request.timeout,
            request.include,
            request.exclude,
            request.render,
            request.provider,
            request.language,
            tuple(capabilities),
            config_hash,
        )
