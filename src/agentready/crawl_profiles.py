"""Bounded operational crawl profiles with explicit server hard caps."""
from __future__ import annotations

from dataclasses import replace
from dataclasses import dataclass
from typing import Any

from .crawler import CrawlConfig


@dataclass(frozen=True, slots=True)
class CrawlProfile:
    name: str
    config: CrawlConfig
    normative_limits: tuple[str, ...] = ()


PROFILES = {
    "quick": CrawlProfile("quick", CrawlConfig(max_pages=100, max_depth=4, concurrency=4, per_origin_concurrency=2, min_request_interval_ms=150, timeout=15, max_duration=120)),
    "standard": CrawlProfile("standard", CrawlConfig(), normative_limits=()),
    "deep": CrawlProfile("deep", CrawlConfig(max_pages=25000, max_depth=32, concurrency=16, per_origin_concurrency=8, min_request_interval_ms=50, timeout=30, max_duration=10800)),
}


def resolve_profile(name: str = "standard", *, overrides: dict[str, Any] | None = None, hard_caps: CrawlConfig | None = None) -> CrawlProfile:
    if name == "custom":
        if not overrides:
            raise ValueError("custom profile requires overrides")
        config = replace(PROFILES["standard"].config, **overrides)
        profile = CrawlProfile("custom", config)
    elif name in PROFILES:
        profile = PROFILES[name]
    else:
        raise ValueError(f"unknown crawl profile: {name}")
    if hard_caps is None:
        return profile
    config = replace(
        profile.config,
        max_pages=min(profile.config.max_pages, hard_caps.max_pages),
        max_depth=min(profile.config.max_depth, hard_caps.max_depth),
        concurrency=min(profile.config.concurrency, hard_caps.concurrency),
        per_origin_concurrency=min(profile.config.per_origin_concurrency, hard_caps.per_origin_concurrency),
        timeout=min(profile.config.timeout, hard_caps.timeout),
        max_duration=min(profile.config.max_duration, hard_caps.max_duration),
    )
    return CrawlProfile(profile.name, config, profile.normative_limits)
