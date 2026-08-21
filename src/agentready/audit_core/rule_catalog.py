"""Single authoritative loader for the packaged frozen rule catalog (#18).

This module is the ONLY place in the runtime that parses the packaged
``agentready.rule-catalog.v2`` artifact (see
:mod:`agentready.seo.rules.catalog.loader`). It converts the validated
catalog document into an immutable :class:`RuleCatalogSnapshot` suitable
for rule discovery, compatibility mapping (#20), and run identity, without
binding, evaluating, or scoring any rule.

Built-in catalog identity (``rule_catalog_version`` / ``rule_catalog_digest``
on :class:`agentready.audit_core.run_context.AuditRunContext`) is kept
strictly separate from caller-supplied custom ruleset identity
(``ruleset_version`` / ``ruleset_hash``). This module only ever produces the
former; it never reads or writes custom ruleset state.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from agentready.seo.rules.catalog import (
    RuleCatalogArtifact,
    RuleCatalogRule,
    RuleCatalogValidationError,
    load_frozen_rule_catalog,
)

__all__ = [
    "RuleCatalogSnapshot",
    "RuleCatalogEntry",
    "RuleCatalogSourceRef",
    "RuleCatalogValidationError",
    "load_rule_catalog_snapshot",
    "catalog_identity",
]


@dataclass(frozen=True, slots=True)
class RuleCatalogSourceRef:
    """Resolved source-registry metadata for one of a rule's ``source_ids``."""

    source_id: str
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class RuleCatalogFactRequirementView:
    family: str
    min_schema_version: str


@dataclass(frozen=True, slots=True)
class RuleCatalogEntry:
    """Immutable runtime view of a single frozen catalog rule.

    All fields map directly onto authored catalog document content (see
    ``agentready.rule-catalog.v2.yaml`` / ``.schema.json``). None of
    ``mechanism``, ``rule_kind``, ``automation_mode``, ``profiles``,
    ``comparison_dimensions``, or ``verification_plan`` are synthesized by
    this module; they are read as-authored from the packaged catalog, which
    now carries them as first-class, schema-validated fields (#17/#18).
    """

    rule_id: str
    version: str
    title: str
    module: str
    scope: str
    condition: str
    fact_requirements: tuple[RuleCatalogFactRequirementView, ...]
    sources: tuple[RuleCatalogSourceRef, ...]
    score_role: str
    failure_policy: str
    summary: str
    mechanism: str
    rule_kind: str
    automation_mode: str
    profiles: tuple[str, ...]
    comparison_dimensions: tuple[str, ...]
    verification_plan: str


def _project_entry(rule: RuleCatalogRule, source_registry: Mapping[str, Mapping[str, str]]) -> RuleCatalogEntry:
    sources = tuple(
        RuleCatalogSourceRef(
            source_id=source_id,
            title=str(source_registry[source_id]["title"]),
            url=str(source_registry[source_id]["url"]),
        )
        for source_id in rule.source_ids
    )
    fact_requirements = tuple(
        RuleCatalogFactRequirementView(family=req.family, min_schema_version=req.min_schema_version)
        for req in rule.fact_requirements
    )
    return RuleCatalogEntry(
        rule_id=rule.rule_id,
        version=rule.version,
        title=rule.title,
        module=rule.module,
        scope=rule.applies_to,
        condition=rule.condition,
        fact_requirements=fact_requirements,
        sources=sources,
        score_role=rule.score_role,
        failure_policy=rule.failure_policy,
        summary=rule.summary,
        mechanism=rule.mechanism,
        rule_kind=rule.rule_kind,
        automation_mode=rule.automation_mode,
        profiles=rule.profiles,
        comparison_dimensions=rule.comparison_dimensions,
        verification_plan=rule.verification_plan,
    )


@dataclass(frozen=True, slots=True)
class RuleCatalogSnapshot:
    """Immutable, validated view of the packaged frozen rule catalog."""

    schema: str
    catalog_version: str
    rule_catalog_digest: str
    rule_count: int
    module_counts: Mapping[str, int]
    entries: tuple[RuleCatalogEntry, ...]

    def entries_by_module(self, module: str) -> tuple[RuleCatalogEntry, ...]:
        return tuple(entry for entry in self.entries if entry.module == module)

    def entry(self, rule_id: str) -> RuleCatalogEntry | None:
        for entry in self.entries:
            if entry.rule_id == rule_id:
                return entry
        return None


def _build_snapshot(artifact: RuleCatalogArtifact) -> RuleCatalogSnapshot:
    entries = tuple(_project_entry(rule, artifact.source_registry) for rule in artifact.rules)
    # MappingProxyType over a private copy: read-only view that cannot be
    # mutated in place by callers, unlike a plain dict (see #18 immutability
    # requirement -- module_counts must not be writable through the
    # otherwise-frozen RuleCatalogSnapshot).
    module_counts: Mapping[str, int] = MappingProxyType(dict(artifact.module_counts))
    return RuleCatalogSnapshot(
        schema=artifact.schema,
        catalog_version=artifact.catalog_version,
        rule_catalog_digest=artifact.digest,
        rule_count=artifact.rule_count,
        module_counts=module_counts,
        entries=entries,
    )


def load_rule_catalog_snapshot() -> RuleCatalogSnapshot:
    """Load, validate, and project the packaged frozen rule catalog.

    This is the single authoritative entry point for runtime code that
    needs catalog data. It performs no network/browser/provider calls and
    fails closed (raises :class:`RuleCatalogValidationError`) on malformed
    catalog data instead of returning a partial snapshot. Each call
    re-validates and re-parses the packaged bytes and returns a fresh,
    independently-immutable snapshot; two loads of the same packaged bytes
    always produce equal catalog identity (``schema``, ``catalog_version``,
    ``rule_catalog_digest``, ``rule_count``) and equal entry data, but
    callers must not assume object identity across calls.
    """
    artifact = load_frozen_rule_catalog()
    return _build_snapshot(artifact)


def catalog_identity(snapshot: RuleCatalogSnapshot | None = None) -> tuple[str, str]:
    """Return ``(rule_catalog_version, rule_catalog_digest)`` for run identity.

    Intended to feed ``AuditRunContext.create(rule_catalog_version=...,
    rule_catalog_digest=...)`` directly. This is strictly the built-in
    catalog identity; it must never be assigned to ``ruleset_version`` /
    ``ruleset_hash``, which are reserved for caller-supplied custom
    rulesets (see #18 acceptance criteria).
    """
    snapshot = snapshot or load_rule_catalog_snapshot()
    return snapshot.catalog_version, snapshot.rule_catalog_digest
