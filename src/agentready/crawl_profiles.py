"""Bounded operational crawl profiles with explicit server hard caps."""
from __future__ import annotations

from dataclasses import dataclass, replace
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
HARD_CAPS = CrawlConfig(
    max_pages=25_000,
    max_depth=32,
    concurrency=16,
    per_origin_concurrency=8,
    timeout=30,
    max_duration=10_800,
)


def resolve_profile(name: str = "standard", *, overrides: dict[str, Any] | None = None, hard_caps: CrawlConfig | None = None) -> CrawlProfile:
    if name == "custom":
        if not overrides:
            raise ValueError("custom profile requires overrides")
        config = replace(PROFILES["standard"].config, **overrides)
        profile = CrawlProfile("custom", config)
    elif name in PROFILES:
        profile = PROFILES[name]
        if overrides:
            profile = CrawlProfile(profile.name, replace(profile.config, **overrides), profile.normative_limits)
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


def resolve_request_profile(
    name: str,
    *,
    max_pages: int,
    timeout: float,
    limits: dict[str, Any],
    full_discovered: bool,
    hard_caps: CrawlConfig = HARD_CAPS,
) -> CrawlProfile:
    """Resolve one bounded profile contract for every v2 audit mode."""
    overrides = {key: value for key, value in limits.items() if key != "check_limit"}
    overrides["max_pages"] = hard_caps.max_pages if full_discovered else max_pages
    overrides["timeout"] = timeout
    if full_discovered:
        overrides["max_depth"] = hard_caps.max_depth
        overrides["max_duration"] = hard_caps.max_duration
    return resolve_profile(name, overrides=overrides, hard_caps=hard_caps)
