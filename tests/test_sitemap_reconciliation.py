import pytest

from agentready.audit_core.store import MemorySiteStore, RunUrlRecord, RunUrlState
from agentready.query_service import QueryService, RunUrlQuery
from agentready.sitemap_reconciliation import (
    chunk_sitemap_urls,
    classify_sitemap_records,
    generate_sitemap_documents,
    generate_sitemap_from_query,
    reconcile_sitemap_urls,
)
from agentready.sitemap import SitemapEvaluation, SitemapLimits, parse_sitemap


def test_sitemap_reconciliation_is_sorted_and_bounded():
    result = reconcile_sitemap_urls(
        ["https://example.test/a", "https://example.test/shared"],
        ["https://example.test/shared", "https://example.test/b"],
    )
    assert result.sitemap_only == ("https://example.test/a",)
    assert result.crawl_only == ("https://example.test/b",)
    assert result.common == ("https://example.test/shared",)


def test_sitemap_exports_are_deduplicated_and_chunked():
    assert chunk_sitemap_urls(["a", "b", "a"], chunk_size=2) == (("a", "b"),)
    with pytest.raises(ValueError):
        chunk_sitemap_urls(["a"], chunk_size=0)


def test_sitemap_chunk_boundaries_preserve_order_and_exact_limits():
    urls = ["https://example.test/1", "https://example.test/2", "https://example.test/2", "https://example.test/3"]
    assert chunk_sitemap_urls(urls, chunk_size=2) == (
        ("https://example.test/1", "https://example.test/2"),
        ("https://example.test/3",),
    )
    documents = generate_sitemap_documents(urls, chunk_size=2)
    assert len(documents) == 2
    assert documents[0].count("<loc>") == 2
    assert documents[1].count("<loc>") == 1


def test_generate_sitemap_documents_emits_bounded_xml_chunks():
    documents = generate_sitemap_documents(
        ["https://example.test/a", "https://example.test/b"],
        chunk_size=1,
    )
    assert len(documents) == 2
    assert "<loc>https://example.test/a</loc>" in documents[0]


def test_generate_sitemap_from_query_uses_bounded_query_projection():
    store = MemorySiteStore()
    store.put_run_url(RunUrlRecord("run", "https://example.test/a", RunUrlState.PARSED))
    store.put_run_url(RunUrlRecord("run", "https://example.test/b", RunUrlState.PARSED))
    documents = generate_sitemap_from_query(
        QueryService(store),
        RunUrlQuery("run", limit=1),
        chunk_size=2,
    )
    assert len(documents) == 1
    assert "https://example.test/a" in documents[0]
    assert "https://example.test/b" in documents[0]


def test_sitemap_classification_uses_crawl_facts_without_network_access():
    result = classify_sitemap_records(
        ["https://example.test/a", "https://example.test/missing"],
        {
            "https://example.test/a": {
                "status_code": 200,
                "canonical": "https://example.test/other",
                "noindex": True,
            },
            "https://example.test/crawl-only": {"status_code": 200},
        },
    )

    assert result.sitemap_only == ("https://example.test/missing",)
    assert result.crawl_only == ("https://example.test/crawl-only",)
    assert result.noindex == ("https://example.test/a",)
    assert result.noncanonical == ("https://example.test/a",)


def test_sitemap_classification_covers_status_policy_flags_and_bounded_input():
    result = classify_sitemap_records(
        [
            "https://example.test/broken",
            "https://example.test/redirect",
            "https://example.test/blocked",
            "https://example.test/canonical/",
            "https://example.test/ignored",
        ],
        {
            "https://example.test/broken": {"status_code": 404},
            "https://example.test/redirect": {"status_code": 301},
            "https://example.test/blocked": {"status_code": 200, "blocked": True},
            "https://example.test/canonical/": {
                "status_code": 200,
                "canonical": "https://example.test/canonical",
            },
            "https://example.test/crawl-only": {"status_code": 200},
        },
        limit=4,
    )

    assert result.broken == ("https://example.test/broken",)
    assert result.redirects == ("https://example.test/redirect",)
    assert result.blocked == ("https://example.test/blocked",)
    assert result.noncanonical == ()
    assert result.sitemap_only == ()
    assert result.crawl_only == ("https://example.test/crawl-only",)


def test_sitemap_reconciliation_and_parser_reject_invalid_limits_and_xxe():
    with pytest.raises(ValueError, match="between 1 and 100000"):
        reconcile_sitemap_urls(["https://example.test/a"], [], limit=0)
    with pytest.raises(ValueError, match="between 1 and 100000"):
        classify_sitemap_records([], {}, limit=100001)
    with pytest.raises(ValueError, match="between 1 and 50000"):
        generate_sitemap_documents(["https://example.test/a"], chunk_size=50001)

    xxe = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///secret">]><urlset/>'
    assert parse_sitemap(xxe).evaluation == SitemapEvaluation.MALFORMED
    limited = parse_sitemap(
        b"<urlset><url><loc>https://example.test/a</loc></url></urlset>",
        limits=SitemapLimits(max_uncompressed_bytes=10),
    )
    assert limited.evaluation == SitemapEvaluation.PARTIAL_SAFETY_LIMIT
