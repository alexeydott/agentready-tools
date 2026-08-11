from agentready.crawl_profiles import HARD_CAPS, resolve_profile


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
