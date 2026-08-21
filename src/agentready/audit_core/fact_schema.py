"""Versioned contracts for shared fact families."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping


class FactCompatibility(StrEnum):
    COMPATIBLE = "compatible"
    MISSING = "missing"
    UNKNOWN = "unknown"
    TOO_OLD = "too_old"
    INCOMPATIBLE = "incompatible"


@dataclass(frozen=True, slots=True)
class FactSchemaRequirement:
    family: str
    min_schema_version: str


@dataclass(frozen=True, slots=True)
class FactSchemaResult:
    family: str
    required: str
    observed: str | None
    compatibility: FactCompatibility

    @property
    def usable(self) -> bool:
        return self.compatibility is FactCompatibility.COMPATIBLE


@dataclass(frozen=True, slots=True)
class FactSchemaRegistry:
    versions: Mapping[str, str]
    incompatible: frozenset[tuple[str, str]] = frozenset()

    @classmethod
    def from_envelopes(cls, envelopes: Iterable[object]) -> FactSchemaRegistry:
        versions: dict[str, str] = {}
        for envelope in envelopes:
            family = getattr(envelope, "schema_family", None)
            version = getattr(envelope, "schema_version", None)
            if not isinstance(family, str) or not family:
                family = getattr(envelope, "kind", None)
            if not isinstance(family, str) or not family:
                continue
            if not isinstance(version, str) or not version:
                versions[family] = "unknown"
                continue
            if family in versions and versions[family] != version:
                versions[family] = "unknown"
            else:
                versions[family] = version
        return cls(versions)

    def resolve(
        self,
        requirements: tuple[FactSchemaRequirement, ...],
    ) -> tuple[FactSchemaResult, ...]:
        """Resolve catalog requirements without consulting collector modules."""
        return tuple(self.check(requirement) for requirement in requirements)

    def check(self, requirement: FactSchemaRequirement) -> FactSchemaResult:
        observed = self.versions.get(requirement.family)
        if observed is None:
            return FactSchemaResult(
                requirement.family,
                requirement.min_schema_version,
                None,
                FactCompatibility.MISSING,
            )
        try:
            required = _version_number(requirement.min_schema_version)
            actual = _version_number(observed)
        except ValueError:
            return FactSchemaResult(
                requirement.family,
                requirement.min_schema_version,
                observed,
                FactCompatibility.UNKNOWN,
            )
        if (requirement.family, observed) in self.incompatible:
            compatibility = FactCompatibility.INCOMPATIBLE
        elif actual < required:
            compatibility = FactCompatibility.TOO_OLD
        else:
            compatibility = FactCompatibility.COMPATIBLE
        return FactSchemaResult(requirement.family, requirement.min_schema_version, observed, compatibility)

    def satisfies(self, requirements: tuple[FactSchemaRequirement, ...]) -> bool:
        return all(self.check(requirement).usable for requirement in requirements)


DEFAULT_FACT_SCHEMA_VERSIONS: dict[str, str] = {
    "transport": "1",
    "representation": "1",
    "page": "1",
    "links": "1",
    "resources": "1",
    "structured-data": "1",
    "robots.fetch": "1",
    "robots.parsed": "1",
    "robots.policy": "1",
    "sitemap.discovery": "1",
    "sitemap.fetch": "1",
    "sitemap.parsed": "1",
    "sitemap.urls": "1",
}


def _version_number(value: str) -> int:
    normalized = value.strip()
    if not normalized.isdigit():
        raise ValueError("fact schema version must be an integer string")
    return int(normalized)
