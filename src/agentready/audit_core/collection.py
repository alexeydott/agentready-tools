"""Immutable collected-page and fact-view contracts for v2 analyzers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass

from ..page_parser import (
    FormFact,
    HeadingFact,
    HreflangFact,
    ImageFact,
    LinkOccurrence,
    ParsedFacts,
    ParsedPage,
    Representation,
    ResourceOccurrence,
    StructuredDataMarker,
    parse_page,
)
from .contracts import FactEnvelope
from .fact_schema import FactSchemaRegistry, FactSchemaResult, FactSchemaRequirement
from .urls import UrlIdentity


@dataclass(frozen=True, slots=True)
class RepresentationObservation:
    source: str
    parsed: ParsedPage | None
    body: bytes | None = None
    error: str | None = None

    @property
    def representation(self) -> Representation | None:
        return self.parsed.representation if self.parsed is not None else None


@dataclass(frozen=True, slots=True)
class RepresentationComparison:
    static_representation_id: str | None
    rendered_representation_id: str | None
    title_changed: bool
    description_changed: bool
    canonical_changed: bool
    robots_changed: bool
    visible_text_changed: bool
    added_links: tuple[str, ...]
    removed_links: tuple[str, ...]
    added_resources: tuple[str, ...]
    removed_resources: tuple[str, ...]
    rendered_error: str | None = None


@dataclass(frozen=True, slots=True)
class CollectedPage:
    """One bounded collection result; it contains no network behavior."""

    url: str
    depth: int
    status_code: int | None
    representation: Representation | None
    facts: ParsedFacts | None
    error: str | None = None
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None
    requested_url: str | None = None
    fetch_error_kind: str | None = None
    redirect_records: tuple[object, ...] = ()
    rendered: RepresentationObservation | None = None
    parsed: ParsedPage | None = None
    fact_schema_versions: tuple[tuple[str, str], ...] = ()

    @property
    def available(self) -> bool:
        return self.error is None and self.status_code is not None


@dataclass(frozen=True, slots=True)
class FactView:
    """Read-only analyzer input derived from one ``CollectedPage``."""

    page: CollectedPage

    @property
    def url(self) -> str:
        return self.page.url

    @property
    def facts(self) -> ParsedFacts | None:
        return self.page.facts

    @property
    def representation(self) -> Representation | None:
        return self.page.representation

    @property
    def headers(self) -> Mapping[str, str]:
        return dict(self.page.headers)

    def header_values(self, name: str) -> tuple[str, ...]:
        """Return all values for a response header using case-insensitive names."""
        wanted = name.casefold()
        return tuple(value for key, value in self.page.headers if key.casefold() == wanted)

    @property
    def x_robots(self) -> str:
        return ", ".join(self.header_values("x-robots-tag"))

    @property
    def transport(self) -> dict[str, object]:
        return {
            "requested_url": self.page.requested_url or self.page.url,
            "final_url": self.page.url,
            "status_code": self.page.status_code,
            "error_kind": self.page.fetch_error_kind,
            "redirects": self.page.redirect_records,
        }

    @property
    def representations(self) -> tuple[RepresentationObservation, ...]:
        static = RepresentationObservation(
            self.page.representation.source if self.page.representation is not None else "static-html",
            self.page.parsed,
            self.page.body,
        )
        return (static, self.page.rendered) if self.page.rendered is not None else (static,)

    @property
    def representation_comparison(self) -> RepresentationComparison | None:
        if self.page.rendered is None:
            return None
        return compare_representations(self.representations)

    @property
    def body(self) -> bytes | None:
        return self.page.body

    @property
    def fact_schema_registry(self) -> FactSchemaRegistry:
        return FactSchemaRegistry(dict(self.page.fact_schema_versions))

    def check_fact_requirements(
        self,
        requirements: tuple[FactSchemaRequirement, ...],
    ) -> tuple[FactSchemaResult, ...]:
        registry = self.fact_schema_registry
        return tuple(registry.check(requirement) for requirement in requirements)


def compare_representations(observations: Iterable[RepresentationObservation]) -> RepresentationComparison | None:
    by_source = {item.source: item for item in observations}
    static = by_source.get("static-html")
    rendered = by_source.get("rendered-dom")
    if static is None or rendered is None:
        return None
    static_facts = static.parsed.facts if static.parsed is not None else None
    rendered_facts = rendered.parsed.facts if rendered.parsed is not None else None
    static_links = _link_set(static_facts)
    rendered_links = _link_set(rendered_facts)
    static_resources = _resource_set(static_facts)
    rendered_resources = _resource_set(rendered_facts)
    return RepresentationComparison(
        static_representation_id=static.representation.representation_id if static.representation is not None else None,
        rendered_representation_id=rendered.representation.representation_id if rendered.representation is not None else None,
        title_changed=_values(static_facts, "titles") != _values(rendered_facts, "titles"),
        description_changed=_values(static_facts, "descriptions") != _values(rendered_facts, "descriptions"),
        canonical_changed=_values(static_facts, "canonicals") != _values(rendered_facts, "canonicals"),
        robots_changed=_values(static_facts, "meta_robots") != _values(rendered_facts, "meta_robots"),
        visible_text_changed=(static_facts.visible_text if static_facts is not None else "") != (rendered_facts.visible_text if rendered_facts is not None else ""),
        added_links=tuple(sorted(rendered_links - static_links)),
        removed_links=tuple(sorted(static_links - rendered_links)),
        added_resources=tuple(sorted(rendered_resources - static_resources)),
        removed_resources=tuple(sorted(static_resources - rendered_resources)),
        rendered_error=rendered.error,
    )


def replay_collected_pages(store: object, run_id: str) -> tuple[CollectedPage, ...]:
    """Rebuild analyzer fact views from durable store records without network/browser access."""
    from .store import FetchFact, PageRecord, RepresentationRecord

    run = store.get_run(run_id)  # type: ignore[attr-defined]
    pages_by_key: dict[str, PageRecord] = {
        page.url_key: page for page in store.iter_pages(run_id)  # type: ignore[attr-defined]
    }
    fetches_by_url: dict[str, FetchFact] = {
        fetch.request_url: fetch for fetch in store.iter_fetches(run_id)  # type: ignore[attr-defined]
    }
    fetches_by_final: dict[str, FetchFact] = {
        fetch.final_url: fetch for fetch in fetches_by_url.values() if fetch.final_url
    }
    run_urls = {
        item.url_key: item for item in store.iter_run_urls(run_id)  # type: ignore[attr-defined]
    }
    redirects_by_request: dict[str, tuple[object, ...]] = {}
    for redirect in store.iter_redirects(run_id):  # type: ignore[attr-defined]
        request_url = getattr(redirect, "request_url", "") or getattr(redirect, "from_url", "")
        redirects_by_request.setdefault(request_url, ())
        redirects_by_request[request_url] = (*redirects_by_request[request_url], redirect)
    keys = sorted(set(pages_by_key) | set(fetches_by_url))
    replayed: list[CollectedPage] = []
    for key in keys:
        page = pages_by_key.get(key)
        fetch = fetches_by_url.get(key) or (fetches_by_final.get(page.final_url) if page is not None and page.final_url else None)
        observations = tuple(store.iter_representations(run_id, key))  # type: ignore[attr-defined]
        static = _observation_from_record(_pick_representation(observations, "static-html"))
        rendered_record = _pick_representation(observations, "rendered-dom")
        rendered = _observation_from_record(rendered_record) if rendered_record is not None else None
        run_url = run_urls.get(key)
        replayed.append(
            CollectedPage(
                page.final_url or page.url_key if page is not None else (fetch.final_url or key if fetch is not None else key),
                page.depth if page is not None else (run_url.depth if run_url is not None else 0),
                page.status_code if page is not None else (fetch.status_code if fetch is not None else None),
                static.representation if static is not None else None,
                static.parsed.facts if static is not None and static.parsed is not None else None,
                fetch.error_kind if fetch is not None and fetch.error_kind else None,
                (),
                static.body if static is not None else None,
                page.requested_url if page is not None else key,
                fetch.error_kind if fetch is not None else (run_url.error_kind if run_url is not None else None),
                redirects_by_request.get(key, ()),
                rendered,
                static.parsed if static is not None else None,
                run.fact_schema_versions,
            )
        )
    return tuple(replayed)


def _pick_representation(records: tuple[object, ...], source: str) -> object | None:
    for record in records:
        if getattr(record, "source", None) == source:
            return record
    return None


def _observation_from_record(record: object | None) -> RepresentationObservation | None:
    if record is None:
        return None
    representation = Representation(
        representation_id=record.representation_id,
        run_id=record.run_id,
        url_key=record.url_key,
        source=record.source,
        content_type=record.content_type,
        body_hash=record.body_hash,
        byte_size=record.byte_size,
        observed_at=record.observed_at,
    )
    facts = parsed_facts_from_dict(record.facts) if record.facts is not None else None
    parsed = _page_from_persisted_facts(facts, representation, record.parser_backend) if facts is not None else None
    if parsed is None and record.body is not None:
        parsed = parse_page(record.body, representation=representation)
    return RepresentationObservation(record.source, parsed, record.body, record.error)


def parsed_facts_to_dict(facts: ParsedFacts) -> dict[str, object]:
    return asdict(facts)


def parsed_facts_from_dict(payload: Mapping[str, object]) -> ParsedFacts:
    return ParsedFacts(
        titles=tuple(str(item) for item in payload.get("titles", ())),
        descriptions=tuple(str(item) for item in payload.get("descriptions", ())),
        headings=tuple(HeadingFact(int(item["level"]), str(item["text"])) for item in _items(payload, "headings")),
        meta_robots=tuple(str(item) for item in payload.get("meta_robots", ())),
        canonicals=tuple(str(item) for item in payload.get("canonicals", ())),
        hreflang=tuple(HreflangFact(str(item["lang"]), str(item["href"])) for item in _items(payload, "hreflang")),
        base_href=payload.get("base_href") if isinstance(payload.get("base_href"), str) else None,
        lang=payload.get("lang") if isinstance(payload.get("lang"), str) else None,
        links=tuple(
            LinkOccurrence(
                str(item["source_representation_id"]),
                int(item["ordinal"]),
                str(item["raw_href"]),
                item.get("resolved_url") if isinstance(item.get("resolved_url"), str) else None,
                str(item.get("anchor_text", "")),
                str(item.get("rel", "")),
                str(item.get("element", "a")),
                item.get("dom_path") if isinstance(item.get("dom_path"), str) else None,
            )
            for item in _items(payload, "links")
        ),
        images=tuple(
            ImageFact(
                str(item["src"]),
                item.get("alt") if isinstance(item.get("alt"), str) else None,
                item.get("title") if isinstance(item.get("title"), str) else None,
                item.get("srcset") if isinstance(item.get("srcset"), str) else None,
                item.get("loading") if isinstance(item.get("loading"), str) else None,
                _optional_int(item.get("width")),
                _optional_int(item.get("height")),
                _optional_int(item.get("status_code")),
                _optional_int(item.get("content_length")),
                item.get("content_type") if isinstance(item.get("content_type"), str) else None,
            )
            for item in _items(payload, "images")
        ),
        resources=tuple(
            ResourceOccurrence(
                str(item["source_representation_id"]),
                int(item["ordinal"]),
                str(item["url"]),
                str(item["resource_type"]),
                item.get("resolved_url") if isinstance(item.get("resolved_url"), str) else None,
                str(item.get("element", "")),
                item.get("dom_path") if isinstance(item.get("dom_path"), str) else None,
            )
            for item in _items(payload, "resources")
        ),
        forms=tuple(
            FormFact(
                item.get("action") if isinstance(item.get("action"), str) else None,
                item.get("method") if isinstance(item.get("method"), str) else None,
            )
            for item in _items(payload, "forms")
        ),
        jsonld_markers=tuple(StructuredDataMarker(str(item["kind"]), int(item["ordinal"])) for item in _items(payload, "jsonld_markers")),
        jsonld_nodes=tuple(dict(item) for item in _items(payload, "jsonld_nodes")),
        jsonld_errors=tuple(str(item) for item in payload.get("jsonld_errors", ())),
        jsonld_block_count=int(payload.get("jsonld_block_count", 0) or 0),
        microdata_markers=tuple(StructuredDataMarker(str(item["kind"]), int(item["ordinal"])) for item in _items(payload, "microdata_markers")),
        visible_text=str(payload.get("visible_text", "")),
        raw_text_signature_inputs=tuple(str(item) for item in payload.get("raw_text_signature_inputs", ())),
    )


def page_fact_envelope(
    *,
    subject_url: str,
    facts: ParsedFacts,
    observed_at: str,
    representation_id: str | None = None,
    envelope_id: str | None = None,
) -> FactEnvelope:
    """Build the sanctioned ``page@1`` evaluation envelope from parsed facts.

    This is the single production adaptation point between collected page
    payloads (``ParsedFacts``) and the frozen-rule evaluation surface
    (:class:`FactEnvelope`). Envelope identity is deterministic over the
    subject URL, observation timestamp, representation id, and canonical
    payload, so replayed evaluations are reproducible offline.
    """
    from .fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS

    if not subject_url or not subject_url.strip():
        raise ValueError("page fact envelope requires a non-empty subject URL")
    if not observed_at or not observed_at.strip():
        raise ValueError("page fact envelope requires a non-empty observed_at")
    identity = UrlIdentity.parse(subject_url)
    payload = parsed_facts_to_dict(facts)
    version = DEFAULT_FACT_SCHEMA_VERSIONS["page"]
    resolved_id = envelope_id or _page_envelope_id(
        identity.normalized(), observed_at, representation_id, payload
    )
    return FactEnvelope(
        id=resolved_id,
        kind="page",
        target=identity,
        value=payload,
        observed_at=observed_at,
        representation_id=representation_id,
        schema_family="page",
        schema_version=version,
    )


def _page_envelope_id(
    normalized_url: str,
    observed_at: str,
    representation_id: str | None,
    payload: Mapping[str, object],
) -> str:
    digest_input = json.dumps(
        [normalized_url, observed_at, representation_id or "", _canonical_payload(payload)],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return "page-fact:" + hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def _canonical_payload(payload: Mapping[str, object]) -> object:
    return json.loads(json.dumps(asdict(_payload_as_parsed_facts(payload)), sort_keys=True, default=str))


def _payload_as_parsed_facts(payload: Mapping[str, object]) -> ParsedFacts:
    return parsed_facts_from_dict(payload)


def load_page_fact_envelopes(
    store: object,
    run_id: str,
    *,
    observed_at: str | None = None,
) -> tuple[FactEnvelope, ...]:
    """Adapt replayed collected pages into sanctioned ``page@1`` envelopes.

    Reads only durable store records via :func:`replay_collected_pages` — no
    network or browser access. Provenance is taken from the actual persisted
    representation: ``representation_id`` and the default ``observed_at``
    come from the ``Representation`` record itself. ``observed_at`` falls
    back to the run's recorded ``started_at`` only when a representation
    carries no observation timestamp (legacy records), keeping repeated
    replays of one run deterministic.
    """
    run = store.get_run(run_id)  # type: ignore[attr-defined]
    envelopes: list[FactEnvelope] = []
    for page in replay_collected_pages(store, run_id):
        if page.facts is None or not page.available:
            continue
        representation_id = getattr(page.representation, "representation_id", None)
        rep_observed_at = getattr(page.representation, "observed_at", "") or ""
        timestamp = (
            observed_at
            if observed_at is not None
            else (rep_observed_at or (getattr(run, "started_at", "") or ""))
        )
        envelopes.append(
            page_fact_envelope(
                subject_url=page.url,
                facts=page.facts,
                observed_at=timestamp,
                representation_id=str(representation_id) if representation_id else None,
            )
        )
    return tuple(envelopes)


def _fact_envelope_id(prefix: str, parts: list[object]) -> str:
    digest_input = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return prefix + hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def _redirect_chain_from_records(records: tuple[object, ...]) -> tuple[str, ...]:
    hops = sorted(records, key=lambda r: getattr(r, "hop_index", 0))
    chain: list[str] = []
    for hop in hops:
        target = getattr(hop, "to_url", None) or getattr(hop, "location_raw", "")
        if target and (not chain or chain[-1] != target):
            chain.append(str(target))
    return tuple(chain)


def transport_fact_envelope(
    *,
    subject_url: str,
    final_url: str | None,
    redirect_chain: tuple[str, ...] = (),
    observed_at: str,
    representation_id: str | None = None,
    envelope_id: str | None = None,
) -> FactEnvelope:
    """Build the sanctioned ``transport@1`` evaluation envelope.

    Payload records the request origin, the post-redirect final URL, and the
    persisted redirect chain. Envelope identity is deterministic over the
    subject URL, observation timestamp, representation id, and payload.
    """
    identity = UrlIdentity.parse(subject_url)
    if not observed_at or not observed_at.strip():
        raise ValueError("transport fact envelope requires a non-empty observed_at")
    payload: dict[str, object] = {
        "origin": identity.origin.to_string(),
        "final_url": final_url or identity.normalized(),
        "redirect_chain": [str(hop) for hop in redirect_chain],
    }
    resolved_id = envelope_id or _fact_envelope_id(
        "transport-fact:",
        [identity.normalized(), observed_at, representation_id or "", payload],
    )
    from .fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS

    return FactEnvelope(
        id=resolved_id,
        kind="transport",
        target=identity,
        value=payload,
        observed_at=observed_at,
        representation_id=representation_id,
        schema_family="transport",
        schema_version=DEFAULT_FACT_SCHEMA_VERSIONS["transport"],
    )


def load_transport_fact_envelopes(
    store: object,
    run_id: str,
    *,
    observed_at: str | None = None,
) -> tuple[FactEnvelope, ...]:
    """Adapt replayed collected pages into ``transport@1`` envelopes.

    Same provenance rules as :func:`load_page_fact_envelopes`.
    """
    run = store.get_run(run_id)  # type: ignore[attr-defined]
    envelopes: list[FactEnvelope] = []
    for page in replay_collected_pages(store, run_id):
        if not page.available:
            continue
        representation_id = getattr(page.representation, "representation_id", None)
        rep_observed_at = getattr(page.representation, "observed_at", "") or ""
        timestamp = (
            observed_at
            if observed_at is not None
            else (rep_observed_at or (getattr(run, "started_at", "") or ""))
        )
        envelopes.append(
            transport_fact_envelope(
                subject_url=page.requested_url or page.url,
                final_url=page.url,
                redirect_chain=_redirect_chain_from_records(page.redirect_records),
                observed_at=timestamp,
                representation_id=str(representation_id) if representation_id else None,
            )
        )
    return tuple(envelopes)


def resource_fact_envelope(
    *,
    subject_url: str,
    resources: tuple[Mapping[str, Any], ...] = (),
    observed_at: str,
    representation_id: str | None = None,
    envelope_id: str | None = None,
) -> FactEnvelope:
    """Build the sanctioned ``resources@1`` evaluation envelope.

    ``resources`` are declared-resource rows (url / resolved_url /
    resource_type) as collected for the subject. Envelope identity is
    deterministic over subject URL, observation timestamp, representation id
    and the canonical resource rows.
    """
    identity = UrlIdentity.parse(subject_url)
    if not observed_at or not observed_at.strip():
        raise ValueError("resource fact envelope requires a non-empty observed_at")
    normalized_rows = sorted(
        (
            str(row.get("url", "")),
            str(row.get("resolved_url") or ""),
            str(row.get("resource_type", "")),
        )
        for row in resources
        if isinstance(row, Mapping)
    )
    payload: dict[str, object] = {"resources": [
        {"url": u, "resolved_url": ru, "resource_type": rt}
        for (u, ru, rt) in normalized_rows
    ]}
    digest_input = json.dumps(
        [identity.normalized(), observed_at, representation_id or "", payload],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    from .fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS

    resolved_id = envelope_id or (
        "resources-fact:"
        + hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    )
    return FactEnvelope(
        id=resolved_id,
        kind="resources",
        target=identity,
        value=payload,
        observed_at=observed_at,
        representation_id=representation_id,
        schema_family="resources",
        schema_version=DEFAULT_FACT_SCHEMA_VERSIONS["resources"],
    )


def run_projection_fact_envelope(
    *,
    anchor_url: str,
    parameter_variants: tuple[str, ...],
    cross_domain_targets: tuple[str, ...],
    observed_at: str,
    representation_id: str | None = None,
    envelope_id: str | None = None,
) -> FactEnvelope:
    """Build the sanctioned run-scoped ``run-projection@1`` envelope.

    Carries the canonical-duplicate variant inventory and the off-origin
    canonical target set computed by the shared projection layer over one
    run's collected inventory. Pure function of its inputs.
    """
    anchor_identity = UrlIdentity.parse(anchor_url)
    if not observed_at or not observed_at.strip():
        raise ValueError("run projection envelope requires a non-empty observed_at")
    payload: dict[str, object] = {
        "parameter_variants": sorted(set(parameter_variants)),
        "cross_domain_targets": sorted(set(cross_domain_targets)),
    }
    resolved_id = envelope_id or _fact_envelope_id(
        "run-projection:",
        [anchor_identity.normalized(), observed_at, representation_id or "", payload],
    )
    from .fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS

    return FactEnvelope(
        id=resolved_id,
        kind="run-projection",
        target=anchor_identity,
        value=payload,
        observed_at=observed_at,
        representation_id=representation_id,
        schema_family="run-projection",
        schema_version=DEFAULT_FACT_SCHEMA_VERSIONS["run-projection"],
    )


def canonical_projection_fact_envelopes(
    store: object,
    run_id: str,
    *,
    observed_at: str | None = None,
) -> tuple[FactEnvelope, ...]:
    """Project canonical duplicate variants and cross-domain targets for a run.

    Pure projection over replayed collected pages: a URL is a
    ``parameter_variants`` entry when it shares scheme/host/path with some
    declared canonical and carries a non-empty query; a canonical is a
    ``cross_domain_targets`` entry when its host differs from the declaring
    subject's host.
    """
    pages = [
        page
        for page in replay_collected_pages(store, run_id)
        if page.facts is not None and page.available and page.facts.canonicals
    ]
    if not pages:
        return ()
    variants: set[str] = set()
    cross_domain: set[str] = set()
    for page in pages:
        page_identity = UrlIdentity.parse(page.url)
        canonical = UrlIdentity.parse(page.facts.canonicals[0])
        if canonical.host != page_identity.host:
            cross_domain.add(canonical.normalized())
        for candidate in pages:
            candidate_identity = UrlIdentity.parse(candidate.url)
            if (
                candidate_identity.origin == canonical.origin
                and candidate_identity.path == canonical.path
                and candidate_identity.query
                and candidate_identity.normalized() != canonical.normalized()
            ):
                variants.add(candidate_identity.normalized())
    anchor = pages[0]
    representation_id = getattr(anchor.representation, "representation_id", None)
    rep_observed_at = getattr(anchor.representation, "observed_at", "") or ""
    run = store.get_run(run_id)  # type: ignore[attr-defined]
    timestamp = (
        observed_at
        if observed_at is not None
        else (rep_observed_at or (getattr(run, "started_at", "") or ""))
    )
    anchor_url = f"{UrlIdentity.parse(anchor.url).origin.to_string()}/"
    return (
        run_projection_fact_envelope(
            anchor_url=anchor_url,
            parameter_variants=tuple(variants),
            cross_domain_targets=tuple(cross_domain),
            observed_at=timestamp,
            representation_id=str(representation_id) if representation_id else None,
        ),
    )


def _page_from_persisted_facts(facts: ParsedFacts, representation: Representation, parser_backend: str | None) -> ParsedPage:
    titles = tuple(dict.fromkeys(facts.titles))
    return ParsedPage(
        titles[0] if titles else "",
        tuple(dict.fromkeys(link.raw_href for link in facts.links)),
        tuple(dict.fromkeys(resource.url for resource in facts.resources)),
        facts.visible_text,
        parser_backend or "persisted-facts",
        representation,
        facts,
    )


def _items(payload: Mapping[str, object], key: str) -> tuple[Mapping[str, object], ...]:
    values = payload.get(key, ())
    return tuple(item for item in values if isinstance(item, Mapping)) if isinstance(values, Iterable) and not isinstance(values, (str, bytes)) else ()


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) else None


def _values(facts: ParsedFacts | None, attr: str) -> tuple[object, ...]:
    return tuple(getattr(facts, attr)) if facts is not None else ()


def _link_set(facts: ParsedFacts | None) -> set[str]:
    return {link.resolved_url or link.raw_href for link in facts.links} if facts is not None else set()


def _resource_set(facts: ParsedFacts | None) -> set[str]:
    return {resource.resolved_url or resource.url for resource in facts.resources} if facts is not None else set()
