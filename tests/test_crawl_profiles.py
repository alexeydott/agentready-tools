import pytest

from agentready.audit_service import AuditRequest
from agentready.crawl_profiles import HARD_CAPS, resolve_profile, resolve_request_profile


def test_profile_overrides_are_bounded_by_operational_hard_caps():
    profile = resolve_profile(
        "custom",
        overrides={
            "max_pages": 100_000,
            "max_depth": 100,
            "concurrency": 100,
            "per_origin_concurrency": 100,
            "timeout": 100,
            "max_duration": 100_000,
        },
        hard_caps=HARD_CAPS,
    )
    assert profile.config.max_pages == HARD_CAPS.max_pages
    assert profile.config.max_depth == HARD_CAPS.max_depth
    assert profile.config.concurrency == HARD_CAPS.concurrency
    assert profile.config.max_duration == HARD_CAPS.max_duration


def test_full_discovered_uses_hard_caps_for_all_modes():
    readiness = resolve_request_profile(
        "quick",
        max_pages=3,
        timeout=5,
        limits={"max_depth": 1, "max_duration": 2},
        full_discovered=True,
    )
    seo = resolve_request_profile(
        "quick",
        max_pages=3,
        timeout=5,
        limits={"max_depth": 1, "max_duration": 2},
        full_discovered=True,
    )
    assert readiness.config == seo.config
    assert readiness.config.max_pages == HARD_CAPS.max_pages
    assert readiness.config.max_depth == HARD_CAPS.max_depth
    assert readiness.config.max_duration == HARD_CAPS.max_duration


def test_seo_full_discovered_requires_explicit_crawl():
    with pytest.raises(ValueError, match="requires crawl=True"):
        AuditRequest(target="https://example.test/", mode="seo", full_discovered=True)


def test_zero_max_pages_remains_the_hard_cap_default():
    request = AuditRequest(target="https://example.test/", max_pages=0)
    assert request.max_pages == HARD_CAPS.max_pages
