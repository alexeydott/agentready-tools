"""Bounded site-wide SEO diagnostics over one canonical parsed-page set."""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Sequence
from itertools import pairwise
from urllib.parse import urljoin, urlsplit

from ..audit_core.store import LinkOccurrenceRecord
from ..duplicates import cluster_signatures, signature
from ..link_graph import build_link_graph, diagnose_graph
from ..models import Evidence
from ..robots import RobotsPolicy, evaluate_robots
from ..seo_models import SeoCheckResult
from ..sitemap_reconciliation import classify_sitemap_records

logger = logging.getLogger(__name__)

_EVIDENCE_LIMIT = 20
_CLUSTER_LIMIT = 100_000
_THIN_WORD_LIMIT = 100


def evaluate_site_rules(
    pages: Sequence[object],
    *,
    evidence_limit: int = _EVIDENCE_LIMIT,
    duplicate_limit: int = _CLUSTER_LIMIT,
    thin_word_limit: int = _THIN_WORD_LIMIT,
    link_occurrences: Sequence[LinkOccurrenceRecord] | None = None,
    origin: str | None = None,
    coverage_complete: bool = True,
    sitemap_urls: Sequence[str] = (),
    robots_policy: RobotsPolicy | None = None,
) -> list[SeoCheckResult]:
    """Evaluate deterministic cross-page rules from already parsed facts."""
    if evidence_limit <= 0 or evidence_limit > 100:
        raise ValueError("evidence_limit must be between 1 and 100")
    if duplicate_limit <= 0 or duplicate_limit > _CLUSTER_LIMIT:
        raise ValueError("duplicate_limit must be between 1 and 100000")
    if thin_word_limit < 0:
        raise ValueError("thin_word_limit must not be negative")

    parsed = [
        page
        for page in pages
        if getattr(page, "parsed", None) is not None
        and getattr(page.parsed, "facts", None) is not None
        and (getattr(page, "status_code", None) or 0) == 200
    ]
    logger.debug(
        "site SEO rules started pages=%d evidence_limit=%d duplicate_limit=%d",
        len(parsed), evidence_limit, duplicate_limit,
    )
    results = [
        _duplicate_metadata(parsed, evidence_limit=evidence_limit),
        _duplicate_content(parsed, evidence_limit=evidence_limit, duplicate_limit=duplicate_limit),
        _thin_content(parsed, evidence_limit=evidence_limit, word_limit=thin_word_limit),
        _heading_structure(parsed, evidence_limit=evidence_limit),
        _canonical_consistency(parsed, evidence_limit=evidence_limit),
        _hreflang_reciprocity(parsed, evidence_limit=evidence_limit),
    ]
    results.extend(
        evaluate_link_rules(
            pages,
            link_occurrences=link_occurrences,
            origin=origin,
            evidence_limit=evidence_limit,
            coverage_complete=coverage_complete,
        )
    )
    results.extend(evaluate_wp5_rules(
        pages,
        sitemap_urls=sitemap_urls,
        robots_policy=robots_policy,
        evidence_limit=evidence_limit,
        coverage_complete=coverage_complete,
    ))
    logger.info("site SEO rules finished pages=%d rules=%d", len(parsed), len(results))
    return results


def evaluate_wp5_rules(
    pages: Sequence[object],
    *,
    sitemap_urls: Sequence[str] = (),
    robots_policy: RobotsPolicy | None = None,
    evidence_limit: int = _EVIDENCE_LIMIT,
    coverage_complete: bool = True,
) -> list[SeoCheckResult]:
    """Evaluate reusable robots/sitemap/image projections over parsed pages.

    Network fetching remains the caller's responsibility; this function only
    consumes bounded policy and parsed facts, keeping one canonical inventory.
    """
    parsed = [page for page in pages if getattr(getattr(page, "parsed", None), "facts", None) is not None]
    image_items = []
    for page in parsed:
        for image in page.parsed.facts.images:
            image_items.append((_page_url(page), image))
    missing_alt = [(url, image.src) for url, image in image_items if not (image.alt or "").strip()]
    image_status = "fail" if missing_alt else "pass"
    image_evidence = [Evidence(
        action="add descriptive image alt text", url=url,
        finding=f"image has {'empty' if image_src else 'missing'} alt text",
        metrics={"src": image_src},
    ) for url, image_src in missing_alt[:evidence_limit]]
    image_detail = (
        f"{len(missing_alt)} of {len(image_items)} image(s) lack non-empty alt text"
        if missing_alt else f"all {len(image_items)} observed image(s) have non-empty alt text"
    )
    image_metrics = {
        "images": len(image_items),
        "missing_alt": len(missing_alt),
        "lazy_loaded": sum(1 for _, image in image_items if (image.loading or "").lower() == "lazy"),
        "with_dimensions": sum(1 for _, image in image_items if image.width is not None and image.height is not None),
        "status": "unknown_without_resource_fetch",
        "failed_status": sum(1 for _, image in image_items if (image.status_code or 0) >= 400),
        "content_length_observed": sum(1 for _, image in image_items if image.content_length is not None),
        "format_observed": sum(1 for _, image in image_items if image.content_type or _image_extension(image.src)),
    }
    image_evidence.append(Evidence(action="inspect image inventory", url=_page_url(parsed[0]) if parsed else "", metrics=image_metrics))
    results = [_result("image-inventory-site", "Image inventory and accessibility signals", "content", image_status, image_detail, image_evidence)]

    records = {
        _page_url(page): {
            "status_code": getattr(page, "status_code", 0) or 0,
            "canonical": (page.parsed.facts.canonicals[0] if page.parsed.facts.canonicals else None),
            "noindex": not _indexable(page),
        }
        for page in parsed
    }
    if sitemap_urls:
        classification = classify_sitemap_records(tuple(sitemap_urls), records, limit=100_000)
        affected = sum(len(getattr(classification, field)) for field in ("sitemap_only", "crawl_only", "broken", "redirects", "blocked", "noindex", "noncanonical"))
        detail = f"sitemap={len(sitemap_urls)} crawled={len(records)} affected classifications={affected}"
        evidence = [Evidence(action="reconcile sitemap inventory", url=url, finding=label) for label, urls in (
            ("sitemap-only", classification.sitemap_only), ("broken", classification.broken),
            ("redirect", classification.redirects), ("noindex", classification.noindex),
            ("noncanonical", classification.noncanonical),
        ) for url in urls[:evidence_limit]][:evidence_limit]
        results.append(_result("sitemap-reconciliation-site", "Sitemap and crawl reconciliation", "crawlability", "warn" if affected else "pass", detail, evidence))
    else:
        results.append(_result("sitemap-reconciliation-site", "Sitemap and crawl reconciliation", "crawlability", "skip", "no sitemap URL inventory was supplied", []))

    if robots_policy is None:
        results.append(_result("robots-reconciliation-site", "Robots policy and crawl reconciliation", "crawlability", "skip", "robots policy was not supplied; no network fetch is performed by this projection", []))
    else:
        blocked = [url for url in records if not evaluate_robots(robots_policy, "*", url).allowed]
        status = "warn" if blocked else "pass"
        results.append(_result("robots-reconciliation-site", "Robots policy and crawl reconciliation", "crawlability", status, f"{len(blocked)} observed URL(s) blocked by robots policy", [Evidence(action="inspect robots decision", url=url, finding="blocked by robots.txt") for url in blocked[:evidence_limit]]))
    logger.info("[WP5] robots/sitemap/image rules pages=%d images=%d", len(parsed), len(image_items))
    return results


def _image_extension(src: str) -> str | None:
    suffix = urlsplit(src).path.rsplit("/", 1)[-1].rsplit(".", 1)
    return suffix[-1].lower() if len(suffix) == 2 and suffix[-1] else None


def evaluate_link_rules(
    pages: Sequence[object],
    *,
    link_occurrences: Sequence[LinkOccurrenceRecord] | None = None,
    origin: str | None = None,
    evidence_limit: int = _EVIDENCE_LIMIT,
    coverage_complete: bool = True,
) -> list[SeoCheckResult]:
    """Project link graph diagnostics without creating a second inventory model."""
    known_pages = tuple(sorted({_page_url(page).rstrip("/") for page in pages}))
    if not known_pages:
        return [_result("link-architecture-site", "Internal link architecture", "links", "skip", "no crawled HTML pages", [])]
    graph_origin = origin or _origin(known_pages[0])
    occurrences = tuple(link_occurrences or _occurrences_from_pages(pages))
    graph = build_link_graph(occurrences, origin=graph_origin)
    diagnostics = diagnose_graph(graph, known_pages=known_pages)
    inlinks: dict[str, int] = defaultdict(int)
    outlinks: dict[str, int] = defaultdict(int)
    anchors: Counter[str] = Counter()
    for edge in graph.edges:
        outlinks[edge.source] += edge.occurrences
        inlinks[edge.target] += edge.occurrences
        for anchor, count in edge.anchors:
            if anchor:
                anchors[anchor] += count
    orphaned = tuple(url for url in known_pages if inlinks[url] == 0 and url != known_pages[0])
    link_evidence = [
        Evidence(action="inspect orphan candidate", url=url, finding="no internal inlinks in crawled graph", metrics={"inlinks": 0})
        for url in orphaned[:evidence_limit]
    ]
    orphan_status = "skip" if not coverage_complete and not orphaned else "warn" if orphaned else "pass"
    orphan_detail = (
        "crawl is partial; orphan status is unknown outside observed coverage"
        if not coverage_complete and not orphaned
        else f"{len(orphaned)} orphan candidate(s) without internal inlinks"
        if orphaned
        else "no orphan candidates in observed crawl graph"
    )
    top_anchors = anchors.most_common(evidence_limit)
    architecture_evidence = [
        Evidence(
            action="inspect internal link graph",
            url=known_pages[0],
            finding=f"nodes={len(known_pages)} edges={len(graph.edges)}",
            metrics={"nodes": len(known_pages), "edges": len(graph.edges), "dangling_targets": list(diagnostics.dangling_targets[:evidence_limit])},
        )
    ]
    authority = dict(graph.authority)
    top_authority = sorted(authority.items(), key=lambda item: (-item[1], item[0]))[:evidence_limit]
    page_by_url = {_page_url(page).rstrip("/"): page for page in pages}
    page_metrics = [
        {
            "url": url,
            "depth": int(getattr(page_by_url[url], "depth", 0)),
            "inlinks": inlinks.get(url, 0),
            "outlinks": outlinks.get(url, 0),
        }
        for url in known_pages[:evidence_limit]
    ]
    return [
        _result(
            "link-architecture-site",
            "Internal link architecture",
            "links",
            "warn" if diagnostics.dangling_targets else "pass",
            f"{len(graph.edges)} internal edge(s), {len(diagnostics.dangling_targets)} dangling target(s)",
            architecture_evidence,
            scored=True,
        ),
        _result(
            "orphan-candidates-site",
            "Orphan page candidates",
            "links",
            orphan_status,
            orphan_detail,
            link_evidence,
        ),
        _result(
            "link-depth-site",
            "Internal click depth and link counts",
            "links",
            "pass",
            f"max depth={max((int(getattr(page, 'depth', 0)) for page in pages), default=0)}, tracked {len(inlinks)} inlink target(s) and {len(outlinks)} outlink source(s)",
            [Evidence(action="inspect click depth and link counts", url=known_pages[0], metrics={"pages": page_metrics})],
        ),
        _result(
            "anchor-distribution-site",
            "Internal anchor distribution",
            "links",
            "warn" if top_anchors and top_anchors[0][1] > 10 else "pass",
            f"{len(anchors)} distinct non-empty anchor text value(s)",
            [Evidence(action="inspect repeated internal anchors", url=known_pages[0], metrics={"top_anchors": top_anchors})],
        ),
        _result(
            "internal-link-authority-site",
            "Internal link authority",
            "links",
            "pass",
            "deterministic internal link authority computed; this is not search-engine PageRank",
            [Evidence(action="inspect internal link authority", url=url, finding=f"authority={score:.6f}", metrics={"algorithm_version": graph.algorithm_version}) for url, score in top_authority],
        ),
    ]


def _occurrences_from_pages(pages: Sequence[object]) -> tuple[LinkOccurrenceRecord, ...]:
    records: list[LinkOccurrenceRecord] = []
    for page in pages:
        source = _page_url(page).rstrip("/")
        facts = getattr(page.parsed, "facts", None)
        if facts is None:
            continue
        for item in facts.links:
            target = item.resolved_url.rstrip("/") if item.resolved_url else None
            records.append(LinkOccurrenceRecord(
                "site-rules", source, item.ordinal, item.raw_href,
                target_key=target, resolved_url=target, anchor_text=item.anchor_text, rel=item.rel,
            ))
    return tuple(records)


def _origin(url: str) -> str:
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _result(
    check_id: str,
    title: str,
    category: str,
    status: str,
    details: str,
    evidence: list[Evidence],
    *,
    scored: bool = False,
) -> SeoCheckResult:
    return SeoCheckResult(
        id=check_id,
        title=title,
        category=category,
        status=status,  # type: ignore[arg-type]
        scored=scored,
        details=details,
        evidence=evidence,
    )


def _page_url(page: object) -> str:
    return str(getattr(page, "url", ""))


def _facts(page: object):
    return page.parsed.facts


def _groups(values: dict[str, list[str]]) -> dict[str, list[str]]:
    return {value: urls for value, urls in values.items() if value and len(urls) > 1}


def _duplicate_metadata(pages: Sequence[object], *, evidence_limit: int) -> SeoCheckResult:
    fields: dict[str, dict[str, list[str]]] = {
        "title": defaultdict(list),
        "description": defaultdict(list),
        "h1": defaultdict(list),
    }
    for page in pages:
        facts = _facts(page)
        fields["title"][facts.titles[0].strip().lower() if facts.titles else ""].append(_page_url(page))
        fields["description"][facts.descriptions[0].strip().lower() if facts.descriptions else ""].append(_page_url(page))
        h1 = next((item.text.strip().lower() for item in facts.headings if item.level == 1 and item.text.strip()), "")
        fields["h1"][h1].append(_page_url(page))
    duplicates = {field: _groups(values) for field, values in fields.items()}
    duplicates = {field: groups for field, groups in duplicates.items() if groups}
    evidence = [
        Evidence(
            action=f"inspect duplicate {field} metadata",
            url=urls[0],
            finding=f"{field} shared by {len(urls)} pages",
            metrics={"field": field, "urls": urls[:evidence_limit]},
        )
        for field, groups in sorted(duplicates.items())
        for urls in groups.values()
    ][:evidence_limit]
    details = (
        "title, description and H1 values are unique across crawled pages"
        if not duplicates
        else "; ".join(f"{field}: {len(groups)} duplicate group(s)" for field, groups in sorted(duplicates.items()))
    )
    return _result("duplicate-metadata-site", "Duplicate metadata across the site", "metadata", "fail" if duplicates else "pass", details, evidence, scored=True)


def _duplicate_content(pages: Sequence[object], *, evidence_limit: int, duplicate_limit: int) -> SeoCheckResult:
    signatures = [
        signature(_page_url(page), _facts(page).visible_text)
        for page in pages
    ]
    clusters = cluster_signatures(signatures, limit=duplicate_limit)
    evidence = [
        Evidence(
            action="inspect duplicate content cluster",
            url=cluster.urls[0],
            finding=f"{len(cluster.urls)} {'near-' if cluster.near_duplicate else ''}duplicate pages",
            metrics={"urls": list(cluster.urls[:evidence_limit]), "near_duplicate": cluster.near_duplicate},
        )
        for cluster in clusters[:evidence_limit]
    ]
    exact = sum(not cluster.near_duplicate for cluster in clusters)
    near = sum(cluster.near_duplicate for cluster in clusters)
    details = "no exact or near-duplicate body content clusters" if not clusters else f"{exact} exact and {near} near-duplicate content cluster(s)"
    return _result("duplicate-content-site", "Duplicate and near-duplicate content", "content", "fail" if clusters else "pass", details, evidence, scored=True)


def _thin_content(pages: Sequence[object], *, evidence_limit: int, word_limit: int) -> SeoCheckResult:
    affected = []
    for page in pages:
        words = len(_facts(page).visible_text.split())
        if words < word_limit:
            affected.append((_page_url(page), words))
    evidence = [
        Evidence(action="inspect thin-content signal", url=url, finding=f"{words} visible words", metrics={"word_count": words, "threshold": word_limit})
        for url, words in affected[:evidence_limit]
    ]
    details = f"{len(affected)} page(s) below the {word_limit}-word objective signal" if affected else f"no page is below the {word_limit}-word objective signal"
    return _result("thin-content-site", "Thin content signal", "content", "warn" if affected else "pass", details, evidence)


def _heading_structure(pages: Sequence[object], *, evidence_limit: int) -> SeoCheckResult:
    issues: list[tuple[str, str]] = []
    for page in pages:
        headings = _facts(page).headings
        if any(not heading.text.strip() for heading in headings):
            issues.append((_page_url(page), "empty heading"))
        levels = [heading.level for heading in headings if heading.text.strip()]
        if levels and levels[0] > 1:
            issues.append((_page_url(page), f"heading starts at H{levels[0]}"))
        if sum(level == 1 for level in levels) > 1:
            issues.append((_page_url(page), "multiple H1 headings"))
        if any(current > previous + 1 for previous, current in pairwise(levels)):
            issues.append((_page_url(page), "heading level skipped"))
    evidence = [Evidence(action="inspect heading hierarchy", url=url, finding=reason) for url, reason in issues[:evidence_limit]]
    details = f"{len(issues)} heading structure issue(s)" if issues else "heading hierarchy has no observed structural issues"
    return _result("heading-structure-site", "Heading hierarchy and empty headings", "metadata", "warn" if issues else "pass", details, evidence)


def _indexable(page: object) -> bool:
    directives = " ".join(_facts(page).meta_robots).lower().replace(",", " ").split()
    return "noindex" not in directives and "none" not in directives


def _canonical_consistency(pages: Sequence[object], *, evidence_limit: int) -> SeoCheckResult:
    by_url = {_page_url(page).rstrip("/"): page for page in pages}
    canonical: dict[str, str] = {}
    for page in pages:
        facts = _facts(page)
        if facts.canonicals:
            canonical[_page_url(page).rstrip("/")] = urljoin(_page_url(page), facts.canonicals[0]).rstrip("/")
    issues: list[tuple[str, str]] = []
    for source, target in canonical.items():
        if target not in by_url:
            issues.append((source, "canonical target was not crawled"))
            continue
        if not _indexable(by_url[target]):
            issues.append((source, "canonical target is marked noindex"))
        seen = {source}
        cursor = target
        while cursor in canonical:
            if cursor in seen:
                issues.append((source, "canonical chain contains a loop"))
                break
            seen.add(cursor)
            cursor = canonical[cursor]
    evidence = [Evidence(action="inspect canonical target chain", url=url, finding=reason) for url, reason in issues[:evidence_limit]]
    details = f"{len(issues)} canonical consistency issue(s)" if issues else "canonical targets are crawled, indexable and acyclic"
    return _result("canonical-consistency-site", "Canonical target consistency", "indexability", "fail" if issues else "pass", details, evidence, scored=True)


def _hreflang_reciprocity(pages: Sequence[object], *, evidence_limit: int) -> SeoCheckResult:
    by_url = {_page_url(page).rstrip("/"): page for page in pages}
    annotations: dict[str, set[str]] = {}
    any_annotations = False
    for page in pages:
        source = _page_url(page).rstrip("/")
        annotations[source] = set()
        for item in _facts(page).hreflang:
            any_annotations = True
            annotations[source].add(urljoin(_page_url(page), item.href).rstrip("/"))
    if not any_annotations:
        return _result("hreflang-reciprocity-site", "Reciprocal hreflang clusters", "indexability", "skip", "no hreflang annotations were observed", [])
    issues: list[tuple[str, str]] = []
    for source, targets in annotations.items():
        for target in sorted(targets):
            if target not in by_url:
                issues.append((source, "hreflang target was not crawled"))
            elif source not in annotations.get(target, set()):
                issues.append((source, f"hreflang target does not link back: {target}"))
    evidence = [Evidence(action="inspect reciprocal hreflang links", url=url, finding=reason) for url, reason in issues[:evidence_limit]]
    details = f"{len(issues)} hreflang reciprocity issue(s)" if issues else "hreflang annotations are reciprocal across crawled targets"
    return _result("hreflang-reciprocity-site", "Reciprocal hreflang clusters", "indexability", "warn" if issues else "pass", details, evidence)
