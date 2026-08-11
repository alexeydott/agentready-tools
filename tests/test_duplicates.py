import pytest

from agentready.duplicates import cluster_signatures, signature


def test_duplicate_signatures_cluster_exact_content_without_quadratic_comparison():
    first = signature("https://example.test/a", "Hello   World")
    second = signature("https://example.test/b", "hello world")
    third = signature("https://example.test/c", "different content")
    clusters = cluster_signatures([first, second, third])
    assert len(clusters) == 1
    assert clusters[0].urls == (first.url, second.url)


def test_duplicate_signature_removes_known_boilerplate_and_preserves_metadata_mode():
    first = signature("https://example.test/a", "Header Main Footer", boilerplate=("Header", "Footer"))
    second = signature("https://example.test/b", "Main")
    metadata = signature("https://example.test/meta", "title: Main", metadata_only=True)
    assert first.exact_hash == second.exact_hash
    assert metadata.metadata_only is True
    assert metadata.version == "content-v1"


def test_near_duplicate_clustering_does_not_merge_false_positive_content():
    first = signature("https://example.test/a", "alpha beta gamma delta")
    near = signature("https://example.test/b", "alpha beta gamma delta epsilon zeta")
    unrelated = signature("https://example.test/c", "pricing terms support contact")

    clusters = cluster_signatures([first, near, unrelated], max_hamming_distance=10)

    assert any(cluster.near_duplicate and cluster.urls == (first.url, near.url) for cluster in clusters)
    assert all(unrelated.url not in cluster.urls for cluster in clusters)


def test_duplicate_clusters_are_stable_across_fixture_order_and_bounded_by_limit():
    first = signature("https://example.test/a", "shared page body")
    second = signature("https://example.test/b", "shared page body")
    near = signature("https://example.test/c", "shared page body with one addition")
    unrelated = signature("https://example.test/d", "completely different pricing content")

    forward = cluster_signatures([first, second, near, unrelated], max_hamming_distance=10)
    reverse = cluster_signatures([unrelated, near, second, first], max_hamming_distance=10)

    assert forward == reverse
    assert forward[0].urls == (first.url, second.url)
    assert len(forward[0].urls) == 2
    assert all(len(cluster.urls) <= 2 for cluster in forward)
    assert cluster_signatures(
        [first, second, near, unrelated],
        max_hamming_distance=10,
        limit=2,
    ) == (forward[0],)


def test_duplicate_clustering_rejects_unbounded_distance_and_input_limits():
    item = signature("https://example.test/a", "content")
    with pytest.raises(ValueError, match="hamming"):
        cluster_signatures([item], max_hamming_distance=65)
    with pytest.raises(ValueError, match="duplicate limit"):
        cluster_signatures([item], limit=0)
