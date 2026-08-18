"""Bounded duplicate and near-duplicate content signatures."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ContentSignature:
    url: str
    exact_hash: str
    simhash: int
    version: str = "content-v1"
    metadata_only: bool = False


@dataclass(frozen=True, slots=True)
class DuplicateCluster:
    signature: int
    urls: tuple[str, ...]
    near_duplicate: bool = False
    version: str = "content-v1"


@dataclass(frozen=True, slots=True)
class DuplicateMember:
    url: str
    kind: str
    similarity: float
    exact_hash: str


@dataclass(frozen=True, slots=True)
class DuplicateClusterRecord:
    cluster_id: str
    members: tuple[DuplicateMember, ...]
    near_duplicate: bool
    algorithm_version: str
    threshold: int


@dataclass(frozen=True, slots=True)
class DuplicateAnalysis:
    clusters: tuple[DuplicateClusterRecord, ...]
    candidate_comparisons: int
    algorithm_version: str
    threshold: int
    fingerprint: str


def analyze_signatures(
    signatures: tuple[ContentSignature, ...] | list[ContentSignature],
    *,
    max_hamming_distance: int = 3,
    limit: int = 100_000,
    max_candidate_comparisons: int = 1_000_000,
) -> DuplicateAnalysis:
    """Return deterministic cluster records and bounded candidate statistics."""
    if max_candidate_comparisons <= 0 or max_candidate_comparisons > 10_000_000:
        raise ValueError("candidate comparison limit must be between 1 and 10000000")
    selected = tuple(signatures[:limit])
    clusters = cluster_signatures(selected, max_hamming_distance=max_hamming_distance, limit=limit)
    by_url = {item.url: item for item in selected}
    records: list[DuplicateClusterRecord] = []
    comparisons = 0
    for cluster in clusters:
        members: list[DuplicateMember] = []
        for url in cluster.urls:
            item = by_url[url]
            similarity = 1.0 if not cluster.near_duplicate else max(0.0, 1.0 - _hamming(item.simhash, by_url[cluster.urls[0]].simhash) / 64.0)
            members.append(DuplicateMember(url, "near" if cluster.near_duplicate else "exact", similarity, item.exact_hash))
        comparisons += max(0, len(cluster.urls) - 1)
        if comparisons > max_candidate_comparisons:
            raise ValueError("duplicate candidate comparison limit exceeded")
        cluster_id = hashlib.sha256((("near" if cluster.near_duplicate else "exact") + "\n" + "\n".join(cluster.urls)).encode("utf-8")).hexdigest()[:16]
        records.append(DuplicateClusterRecord(cluster_id, tuple(sorted(members, key=lambda item: item.url)), cluster.near_duplicate, cluster.version, max_hamming_distance))
    canonical = "\n".join(f"{item.cluster_id}:{','.join(member.url for member in item.members)}" for item in records)
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    logger.info("duplicate analysis clusters=%d candidates=%d threshold=%d", len(records), comparisons, max_hamming_distance)
    return DuplicateAnalysis(tuple(sorted(records, key=lambda item: item.cluster_id)), comparisons, "content-v1", max_hamming_distance, fingerprint)


def signature(
    url: str,
    text: str,
    *,
    boilerplate: tuple[str, ...] | list[str] = (),
    metadata_only: bool = False,
) -> ContentSignature:
    normalized = _normalize(text, boilerplate=boilerplate)
    exact = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return ContentSignature(url, exact, _simhash(normalized), metadata_only=metadata_only)


def cluster_signatures(
    signatures: tuple[ContentSignature, ...] | list[ContentSignature],
    *,
    max_hamming_distance: int = 3,
    limit: int = 100_000,
) -> tuple[DuplicateCluster, ...]:
    if max_hamming_distance < 0 or max_hamming_distance > 64:
        raise ValueError("max_hamming_distance must be between 0 and 64")
    if limit <= 0 or limit > 100_000:
        raise ValueError("duplicate limit must be between 1 and 100000")
    buckets: dict[str, list[str]] = defaultdict(list)
    simhash_buckets: dict[int, list[ContentSignature]] = defaultdict(list)
    for item in signatures[:limit]:
        buckets[item.exact_hash].append(item.url)
        simhash_buckets[item.simhash >> 48].append(item)
    clusters = [
        DuplicateCluster(int(key[:16], 16), tuple(sorted(urls)))
        for key, urls in sorted(buckets.items())
        if len(urls) > 1
    ]
    seen_pairs: set[tuple[str, ...]] = {cluster.urls for cluster in clusters}
    for candidates in simhash_buckets.values():
        for index, item in enumerate(candidates):
            near = tuple(sorted(
                other.url
                for other in candidates[index + 1:]
                if _hamming(item.simhash, other.simhash) <= max_hamming_distance
            ))
            urls = tuple(sorted((item.url, *near)))
            if len(urls) > 1 and urls not in seen_pairs:
                clusters.append(DuplicateCluster(item.simhash, urls, near_duplicate=True))
                seen_pairs.add(urls)
    return tuple(clusters)


def _normalize(text: str, *, boilerplate: tuple[str, ...] | list[str] = ()) -> str:
    value = text
    for fragment in boilerplate:
        if fragment:
            value = value.replace(fragment, " ")
    return re.sub(r"\s+", " ", value).strip().lower()


def _simhash(text: str) -> int:
    bits = [0] * 64
    for token in text.split():
        digest = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big")
        for index in range(64):
            bits[index] += 1 if digest & (1 << index) else -1
    return sum((1 << index) for index, value in enumerate(bits) if value >= 0)


def _hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()
