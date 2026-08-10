from __future__ import annotations

import gzip

import pytest

from agentready.robots import (
    RobotsFetchState,
    RobotsFetchStatus,
    RobotsInterpretation,
    evaluate_robots,
    parse_robots,
    robots_fetch_state,
    sensitive_path_diagnostic,
    simulate_robots,
)
from agentready.sitemap import (
    SitemapEvaluation,
    SitemapLimits,
    classify_sitemap_scope,
    parse_sitemap,
    parse_sitemap_collection,
)


def test_rfc_robots_longest_match_and_vendor_interpretation_are_distinct() -> None:
    policy = parse_robots(
        "User-agent: *\nDisallow: /private\nAllow: /private/public$\nSitemap: https://example.test/sitemap.xml",
        "https://example.test",
        fetch=RobotsFetchState(RobotsFetchStatus.AVAILABLE),
    )
    blocked = evaluate_robots(policy, "ExampleBot", "https://example.test/private/file")
    allowed = evaluate_robots(policy, "ExampleBot", "https://example.test/private/public", interpretation=RobotsInterpretation.GOOGLE)
    assert not blocked.allowed
    assert allowed.allowed
    assert allowed.interpretation == RobotsInterpretation.GOOGLE
    assert policy.sitemaps == ("https://example.test/sitemap.xml",)


def test_robots_fetch_failures_follow_rfc_baseline() -> None:
    assert robots_fetch_state(404) == RobotsFetchStatus.UNAVAILABLE
    assert robots_fetch_state(503) == RobotsFetchStatus.UNREACHABLE
    unavailable = parse_robots("", "https://example.test", fetch=RobotsFetchState(RobotsFetchStatus.UNAVAILABLE))
    unreachable = parse_robots("", "https://example.test", fetch=RobotsFetchState(RobotsFetchStatus.UNREACHABLE))
    assert evaluate_robots(unavailable, "*", "https://example.test/private").allowed
    assert not evaluate_robots(unreachable, "*", "https://example.test/private").allowed


def test_virtual_robots_diff_is_explicit_and_non_mutating() -> None:
    live = parse_robots("User-agent: *\nDisallow: /private", "https://example.test")
    simulated = parse_robots("User-agent: *\nAllow: /private", "https://example.test")
    diff = simulate_robots(live, simulated, ["https://example.test/private"])
    assert diff.newly_allowed_urls == ("https://example.test/private",)
    assert diff.label.startswith("SIMULATION")
    assert sensitive_path_diagnostic(live)


def test_robots_size_limit_is_bounded() -> None:
    with pytest.raises(ValueError, match="500"):
        parse_robots("User-agent: *\n" + ("Disallow: /x\n" * 100000), "https://example.test")


def test_sitemap_namespaces_and_index_are_parsed_without_network() -> None:
    urlset = b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.test/a</loc></url></urlset>"""
    index = b"""<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://example.test/a.xml</loc></sitemap></sitemapindex>"""
    parsed = parse_sitemap(urlset)
    indexed = parse_sitemap(index)
    assert parsed.kind == "urlset" and parsed.urls == ("https://example.test/a",)
    assert indexed.kind == "sitemapindex" and indexed.child_sitemaps == ("https://example.test/a.xml",)


def test_sitemap_rejects_dtd_and_malformed_xml() -> None:
    xxe = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///secret">]><urlset/>'
    malformed = b"<urlset><url><loc>https://example.test"
    assert parse_sitemap(xxe).evaluation == SitemapEvaluation.MALFORMED
    assert parse_sitemap(malformed).evaluation == SitemapEvaluation.MALFORMED


def test_sitemap_gzip_and_safety_limit_are_bounded() -> None:
    payload = b"<urlset><url><loc>https://example.test/a</loc></url></urlset>"
    compressed = gzip.compress(payload)
    parsed = parse_sitemap(compressed, compressed=True)
    assert parsed.urls == ("https://example.test/a",)
    limited = parse_sitemap(payload, limits=SitemapLimits(max_uncompressed_bytes=10))
    assert limited.evaluation == SitemapEvaluation.PARTIAL_SAFETY_LIMIT


def test_sitemap_collection_enforces_file_cap() -> None:
    document = b"<urlset><url><loc>https://example.test/a</loc></url></urlset>"
    results = parse_sitemap_collection([document, document], limits=SitemapLimits(max_files=1))
    assert len(results) == 2
    assert results[-1].evaluation == SitemapEvaluation.PARTIAL_SAFETY_LIMIT


def test_sitemap_scope_requires_ownership_for_cross_origin_urls() -> None:
    result = classify_sitemap_scope(
        ["https://example.test/a", "https://cdn.test/b", "https://verified.test/c"],
        "https://example.test",
        verified_origins={"https://verified.test"},
    )
    assert result.same_origin == ("https://example.test/a",)
    assert result.cross_origin_unknown == ("https://cdn.test/b",)
    assert result.cross_origin_verified == ("https://verified.test/c",)
    assert result.warnings
