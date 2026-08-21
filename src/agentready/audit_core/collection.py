"""Immutable collected-page and fact-view contracts for v2 analyzers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..page_parser import ParsedFacts, ParsedPage, Representation
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
