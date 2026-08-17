"""Immutable collected-page and fact-view contracts for v2 analyzers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..page_parser import ParsedFacts, Representation


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

    @property
    def body(self) -> bytes | None:
        return self.page.body
