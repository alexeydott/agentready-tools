"""Bounded internal link graph and deterministic authority metrics."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from urllib.parse import urlsplit

from .audit_core.store import LinkOccurrenceRecord


@dataclass(frozen=True, slots=True)
class LinkEdge:
    source: str
    target: str
    occurrences: int
    anchors: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class LinkGraph:
    edges: tuple[LinkEdge, ...]
    authority: tuple[tuple[str, float], ...]
    algorithm_version: str = "internal-authority-v1"


@dataclass(frozen=True, slots=True)
class GraphDiagnostics:
    dangling_targets: tuple[str, ...]
    disconnected_pages: tuple[str, ...]
    repeated_anchor_edges: tuple[tuple[str, str], ...]


def build_link_graph(
    occurrences: tuple[LinkOccurrenceRecord, ...] | list[LinkOccurrenceRecord],
    *,
    origin: str,
    iterations: int = 20,
) -> LinkGraph:
    if iterations <= 0 or iterations > 100:
        raise ValueError("iterations must be between 1 and 100")
    grouped: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for item in occurrences:
        if item.target_key and _origin(item.target_key) == origin and _origin(item.source_key) == origin:
            grouped[(item.source_key, item.target_key)][item.anchor_text or ""] += 1
    edges = tuple(
        LinkEdge(source, target, sum(anchors.values()), tuple(sorted(anchors.items())))
        for (source, target), anchors in sorted(grouped.items())
    )
    nodes = sorted({edge.source for edge in edges} | {edge.target for edge in edges})
    outgoing = Counter()
    for edge in edges:
        outgoing[edge.source] += edge.occurrences
    scores = {node: 1.0 for node in nodes}
    for _ in range(iterations):
        next_scores = {node: 0.15 for node in nodes}
        for edge in edges:
            next_scores[edge.target] += 0.85 * scores[edge.source] * edge.occurrences / (outgoing[edge.source] or 1)
        scores = next_scores
    return LinkGraph(edges, tuple(sorted(scores.items())))


def bounded_n_hop(
    graph: LinkGraph,
    start: str,
    *,
    hops: int = 2,
    max_nodes: int = 1000,
) -> tuple[str, ...]:
    """Return a deterministic bounded forward neighborhood."""
    if hops <= 0 or hops > 20:
        raise ValueError("hops must be between 1 and 20")
    if max_nodes <= 0 or max_nodes > 100_000:
        raise ValueError("max_nodes must be between 1 and 100000")
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        adjacency[edge.source].add(edge.target)
    seen = {start}
    frontier = {start}
    for _ in range(hops):
        next_frontier = {
            target
            for source in frontier
            for target in adjacency.get(source, ())
            if target not in seen
        }
        for target in sorted(next_frontier):
            if len(seen) >= max_nodes:
                return tuple(sorted(seen))
            seen.add(target)
        frontier = next_frontier
        if not frontier:
            break
    return tuple(sorted(seen))


def diagnose_graph(
    graph: LinkGraph,
    *,
    known_pages: tuple[str, ...] | list[str] = (),
    max_items: int = 100_000,
) -> GraphDiagnostics:
    if max_items <= 0 or max_items > 100_000:
        raise ValueError("graph diagnostic limit must be between 1 and 100000")
    known = set(known_pages[:max_items])
    sources = {edge.source for edge in graph.edges}
    targets = {edge.target for edge in graph.edges}
    dangling = tuple(sorted(targets - known)) if known else ()
    connected = sources | targets
    disconnected = tuple(sorted(known - connected))
    repeated = tuple(
        (edge.source, edge.target)
        for edge in graph.edges
        if any(count > 1 for _, count in edge.anchors)
    )
    return GraphDiagnostics(dangling, disconnected, repeated)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
