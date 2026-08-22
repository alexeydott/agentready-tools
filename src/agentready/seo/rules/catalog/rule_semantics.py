"""Typed loader for the accepted Stage E rule-semantics artifact (#52–#55).

The artifact ``agentready.rule-semantics.v2.yaml`` is the normative source of
executable evaluator decisions for the first Stage E wave. It is pinned to an
exact frozen catalog version+digest and ships as package data; loading it is
pure and offline.
"""

from __future__ import annotations

import hashlib
import importlib.resources
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:  # pragma: no cover
    from agentready.audit_core.rule_catalog import RuleCatalogSnapshot

SEMANTICS_SCHEMA_ID = "agentready.rule-semantics.v2"
SEMANTICS_RESOURCE_NAME = "agentready.rule-semantics.v2.yaml"


@dataclass(frozen=True, slots=True)
class AcceptedCondition:
    rule_id: str
    version: str
    source_issue: str
    verdicts: dict[str, str]
    evidence_fields: tuple[str, ...]
    intent: str | None = None


@dataclass(frozen=True, slots=True)
class RequirementAmendment:
    rule_id: str
    families: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleSemanticsDocument:
    schema: str
    semantics_version: str
    catalog_version: str
    catalog_digest: str
    governance: dict[str, str]
    conditions: tuple[AcceptedCondition, ...]
    amendments: tuple[RequirementAmendment, ...]
    digest: str

    def condition(self, rule_id: str) -> AcceptedCondition | None:
        for item in self.conditions:
            if item.rule_id == rule_id:
                return item
        return None

    def amendment(self, rule_id: str) -> RequirementAmendment | None:
        for item in self.amendments:
            if item.rule_id == rule_id:
                return item
        return None


def semantics_yaml_bytes() -> bytes:
    return (
        importlib.resources.files("agentready.seo.rules.catalog")
        .joinpath(SEMANTICS_RESOURCE_NAME)
        .read_bytes()
    )


def compute_semantics_digest() -> str:
    return hashlib.sha256(semantics_yaml_bytes()).hexdigest()


def load_rule_semantics(
    snapshot: "RuleCatalogSnapshot | None" = None,
) -> RuleSemanticsDocument:
    """Load and validate the packaged semantics document.

    When a catalog snapshot is supplied, the pinned catalog version/digest and
    every rule id/version are cross-checked against it; mismatches raise
    :class:`RuleSemanticsError` so a drifted artifact cannot ship silently.
    """
    raw = yaml.safe_load(semantics_yaml_bytes())
    if not isinstance(raw, dict):
        raise RuleSemanticsError("semantics document must be a mapping")
    if raw.get("schema") != SEMANTICS_SCHEMA_ID:
        raise RuleSemanticsError(f"unexpected schema id: {raw.get('schema')!r}")
    pin = raw["catalog_pin"]
    conditions = tuple(
        AcceptedCondition(
            rule_id=str(item["rule_id"]),
            version=str(item["version"]),
            source_issue=str(item["source_issue"]),
            verdicts={str(k): str(v) for k, v in (item.get("verdicts") or {}).items()},
            evidence_fields=tuple(str(f) for f in item.get("evidence_fields", ())),
            intent=item.get("intent"),
        )
        for item in raw["accepted_conditions"]
    )
    amendments = tuple(
        RequirementAmendment(
            rule_id=str(item["rule_id"]),
            families=tuple(str(f) for f in item["families"]),
        )
        for item in raw["requirement_amendments"]
    )
    document = RuleSemanticsDocument(
        schema=str(raw["schema"]),
        semantics_version=str(raw["semantics_version"]),
        catalog_version=str(pin["version"]),
        catalog_digest=str(pin["digest"]),
        governance={str(k): str(v) for k, v in raw["governance"].items()},
        conditions=conditions,
        amendments=amendments,
        digest=compute_semantics_digest(),
    )
    if snapshot is not None:
        _validate_against_snapshot(document, snapshot)
    return document


def _validate_against_snapshot(
    document: RuleSemanticsDocument, snapshot: "RuleCatalogSnapshot"
) -> None:
    if document.catalog_version != snapshot.catalog_version:
        raise RuleSemanticsError(
            f"catalog version drift: artifact pins {document.catalog_version!r}, "
            f"snapshot is {snapshot.catalog_version!r}"
        )
    if document.catalog_digest != snapshot.rule_catalog_digest:
        raise RuleSemanticsError("catalog digest drift between semantics artifact and snapshot")
    entries = {entry.rule_id: entry for entry in snapshot.entries}
    for condition in document.conditions:
        entry = entries.get(condition.rule_id)
        if entry is None:
            raise RuleSemanticsError(f"unknown rule id in semantics artifact: {condition.rule_id}")
        if condition.version != entry.version:
            raise RuleSemanticsError(
                f"{condition.rule_id}: semantics version {condition.version} != catalog {entry.version}"
            )
    for amendment in document.amendments:
        if amendment.rule_id not in entries:
            raise RuleSemanticsError(f"unknown rule id in amendments: {amendment.rule_id}")


class RuleSemanticsError(ValueError):
    """Raised when the semantics artifact is missing, malformed, or drifted."""
