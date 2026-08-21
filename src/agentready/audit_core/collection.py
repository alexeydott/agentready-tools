"""Immutable collected-page and fact-view contracts for v2 analyzers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ..page_parser import ParsedFacts, ParsedPage, Representation, parse_page
from .fact_schema import FactSchemaRegistry, FactSchemaResult, FactSchemaRequirement


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
    redirects = tuple(store.iter_redirects(run_id))  # type: ignore[attr-defined]
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
                redirects,
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
    parsed = parse_page(record.body, representation=representation) if record.body is not None else None
    return RepresentationObservation(record.source, parsed, record.body, record.error)


def _values(facts: ParsedFacts | None, attr: str) -> tuple[object, ...]:
    return tuple(getattr(facts, attr)) if facts is not None else ()


def _link_set(facts: ParsedFacts | None) -> set[str]:
    return {link.resolved_url or link.raw_href for link in facts.links} if facts is not None else set()


def _resource_set(facts: ParsedFacts | None) -> set[str]:
    return {resource.resolved_url or resource.url for resource in facts.resources} if facts is not None else set()
