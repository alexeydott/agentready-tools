"""Bounded duplicate and near-duplicate content signatures."""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass


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
