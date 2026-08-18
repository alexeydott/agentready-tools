"""Bounded internal link graph and deterministic authority metrics."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import logging
from urllib.parse import urlsplit

from .audit_core.store import LinkOccurrenceRecord

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True, slots=True)
class LinkNode:
    url: str
    inlinks: int
    outlinks: int
    unique_inlinks: int
    unique_outlinks: int
    depth: int | None
    dead_end: bool
    disconnected: bool
    nofollow_inlinks: int
    redirect_inlinks: int
    authority: float


@dataclass(frozen=True, slots=True)
class LinkGraphProjection:
    run_id: str
    nodes: tuple[LinkNode, ...]
    graph: LinkGraph
    version: str = "link-graph-v1"

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256("\n".join(node.url for node in self.nodes).encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "algorithm_version": self.graph.algorithm_version,
            "nodes": [{key: value for key, value in node.__dict__.items()} if hasattr(node, "__dict__") else {
                "url": node.url, "inlinks": node.inlinks, "outlinks": node.outlinks,
                "unique_inlinks": node.unique_inlinks, "unique_outlinks": node.unique_outlinks,
                "depth": node.depth, "dead_end": node.dead_end, "disconnected": node.disconnected,
                "nofollow_inlinks": node.nofollow_inlinks, "redirect_inlinks": node.redirect_inlinks,
                "authority": node.authority,
            } for node in self.nodes],
        }

    def node(self, url: str) -> LinkNode:
        for item in self.nodes:
            if item.url == url:
                return item
        raise KeyError(url)


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
    total = sum(scores.values()) or 1.0
    normalized = {node: score / total for node, score in scores.items()}
    return LinkGraph(edges, tuple(sorted(normalized.items())))


def project_link_graph(
    occurrences: tuple[LinkOccurrenceRecord, ...] | list[LinkOccurrenceRecord],
    *,
    run_id: str,
    origin: str,
    known_pages: tuple[str, ...] | list[str] = (),
    page_depths: dict[str, int] | None = None,
    redirect_sources: tuple[str, ...] | list[str] = (),
    limit: int = 100_000,
) -> LinkGraphProjection:
    """Build one bounded node projection from canonical link occurrences."""
    if limit <= 0 or limit > 100_000:
        raise ValueError("graph projection limit must be between 1 and 100000")
    selected = tuple(occurrences[:limit])
    graph = build_link_graph(selected, origin=origin)
    known = set(known_pages[:limit])
    known.update(edge.source for edge in graph.edges)
    known.update(edge.target for edge in graph.edges)
    in_sources: dict[str, set[str]] = defaultdict(set)
    out_targets: dict[str, set[str]] = defaultdict(set)
    nofollow: Counter[str] = Counter()
    redirect_targets = set(redirect_sources)
    for item in selected:
        if not item.target_key or item.source_key not in known:
            continue
        if _origin(item.target_key) != origin or _origin(item.source_key) != origin:
            continue
        in_sources[item.target_key].add(item.source_key)
        out_targets[item.source_key].add(item.target_key)
        if (item.rel and "nofollow" in item.rel.lower()) or (item.rel_flags or 0) & 1:
            nofollow[item.target_key] += 1
    authority = dict(graph.authority)
    nodes = tuple(
        LinkNode(
            url=url,
            inlinks=sum(1 for item in selected if item.target_key == url),
            outlinks=sum(1 for item in selected if item.source_key == url and item.target_key),
            unique_inlinks=len(in_sources.get(url, set())),
            unique_outlinks=len(out_targets.get(url, set())),
            depth=(page_depths or {}).get(url),
            dead_end=not out_targets.get(url),
            disconnected=not in_sources.get(url) and not out_targets.get(url),
            nofollow_inlinks=nofollow.get(url, 0),
            redirect_inlinks=sum(1 for item in selected if item.target_key == url and item.source_key in redirect_targets),
            authority=authority.get(url, 0.0),
        )
        for url in sorted(known)
    )
    logger.info("link graph projected run_id=%s nodes=%d edges=%d algorithm=%s", run_id, len(nodes), len(graph.edges), graph.algorithm_version)
    return LinkGraphProjection(run_id, nodes, graph)


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
