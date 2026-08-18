from agentready.audit_core.store import LinkOccurrenceRecord
from agentready.link_graph import bounded_n_hop, build_link_graph, diagnose_graph, project_link_graph


def test_link_graph_aggregates_repeated_anchors_and_bounded_authority():
    occurrences = [
        LinkOccurrenceRecord("run", "https://example.test/", 0, "/a", target_key="https://example.test/a", anchor_text="A"),
        LinkOccurrenceRecord("run", "https://example.test/", 1, "/a", target_key="https://example.test/a", anchor_text="A"),
        LinkOccurrenceRecord("run", "https://example.test/a", 0, "/b", target_key="https://example.test/b", anchor_text="B"),
    ]
    graph = build_link_graph(occurrences, origin="https://example.test")
    assert graph.edges[0].occurrences == 2
    assert graph.edges[0].anchors == (("A", 2),)
    assert dict(graph.authority)["https://example.test/a"] > dict(graph.authority)["https://example.test/"]
    assert graph.algorithm_version == "internal-authority-v1"
    assert bounded_n_hop(graph, "https://example.test/", hops=2) == (
        "https://example.test/",
        "https://example.test/a",
        "https://example.test/b",
    )
    diagnostics = diagnose_graph(
        graph,
        known_pages=("https://example.test/", "https://example.test/a", "https://example.test/orphan"),
    )
    assert diagnostics.dangling_targets == ("https://example.test/b",)
    assert diagnostics.disconnected_pages == ("https://example.test/orphan",)
    assert diagnostics.repeated_anchor_edges == (("https://example.test/", "https://example.test/a"),)


def test_link_graph_aggregates_large_occurrence_inventory():
    occurrences = [
        LinkOccurrenceRecord(
            "run",
            "https://example.test/",
            index,
            "/target",
            target_key="https://example.test/target",
            anchor_text="Target",
        )
        for index in range(100_000)
    ]

    graph = build_link_graph(occurrences, origin="https://example.test")

    assert len(graph.edges) == 1
    assert graph.edges[0].occurrences == 100_000
    assert graph.edges[0].anchors == (("Target", 100_000),)


def test_link_graph_projection_exposes_nodes_filters_and_normalized_authority():
    occurrences = [
        LinkOccurrenceRecord("run", "https://example.test/", 0, "/b", target_key="https://example.test/b"),
        LinkOccurrenceRecord("run", "https://example.test/", 1, "/b", target_key="https://example.test/b", rel="nofollow"),
        LinkOccurrenceRecord("run", "https://example.test/b", 0, "/c", target_key="https://example.test/c"),
    ]
    projection = project_link_graph(
        occurrences,
        run_id="run",
        origin="https://example.test",
        known_pages=("https://example.test/", "https://example.test/b", "https://example.test/c", "https://example.test/isolated"),
        page_depths={"https://example.test/b": 1},
    )
    nodes = {node.url: node for node in projection.nodes}
    assert nodes["https://example.test/b"].inlinks == 2
    assert nodes["https://example.test/b"].nofollow_inlinks == 1
    assert nodes["https://example.test/c"].dead_end is True
    assert nodes["https://example.test/isolated"].disconnected is True
    assert abs(sum(value for _, value in projection.graph.authority) - 1.0) < 1e-9


def test_link_graph_projection_treats_missing_rel_flags_as_zero():
    occurrence = LinkOccurrenceRecord(
        "run",
        "https://example.test/",
        0,
        "/a",
        target_key="https://example.test/a",
        rel_flags=None,
    )

    projection = project_link_graph(
        [occurrence], run_id="run", origin="https://example.test"
    )

    assert projection.nodes[0].nofollow_inlinks == 0
