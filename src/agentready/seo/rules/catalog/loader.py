"""Validating loader for the frozen v2.1.0-draft.1 rule catalog (#17).

This module intentionally does not register, bind, or execute any catalog
rule. It only proves the packaged YAML catalog is present, schema-valid,
internally consistent, and produces a deterministic digest from its exact
packaged bytes.
"""
from __future__ import annotations

import hashlib
import importlib.resources
import re
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from typing import Mapping

import yaml

CATALOG_SCHEMA_ID = "agentready.rule-catalog.v2"

_CATALOG_YAML_NAME = "agentready.rule-catalog.v2.yaml"
_CATALOG_SCHEMA_NAME = "agentready.rule-catalog.v2.schema.json"

_VALID_SCORE_ROLES = frozenset({"scored", "diagnostic", "observation_only"})
_VALID_FAILURE_POLICIES = frozenset({"block_on_missing_facts", "unknown_on_missing_facts"})
_VALID_MECHANISMS = frozenset({"atomic_check", "composite_check"})
_VALID_RULE_KINDS = frozenset({"scored_rule", "diagnostic_rule", "observation_rule"})
_VALID_AUTOMATION_MODES = frozenset({"automated", "manual", "hybrid"})

# Mirrors the `rule_id`/`version` `pattern` constraints published in
# agentready.rule-catalog.v2.schema.json. Kept in sync deliberately (see #21
# integrity gate) rather than parsing the JSON Schema at runtime.
_RULE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)+$")
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class RuleCatalogValidationError(ValueError):
    """Raised when the packaged rule-catalog document fails validation."""

    def __init__(self, errors: list[str]):
        self.errors = tuple(errors)
        super().__init__("invalid rule catalog document:\n- " + "\n- ".join(errors))


@dataclass(frozen=True, slots=True)
class RuleCatalogFactRequirement:
    family: str
    min_schema_version: str


@dataclass(frozen=True, slots=True)
class RuleCatalogRule:
    rule_id: str
    version: str
    title: str
    module: str
    applies_to: str
    condition: str
    fact_requirements: tuple[RuleCatalogFactRequirement, ...]
    source_ids: tuple[str, ...]
    score_role: str
    failure_policy: str
    summary: str
    mechanism: str
    rule_kind: str
    automation_mode: str
    profiles: tuple[str, ...]
    comparison_dimensions: tuple[str, ...]
    verification_plan: str


@dataclass(frozen=True, slots=True)
class RuleCatalogArtifact:
    schema: str
    catalog_version: str
    generated_at: str
    rule_count: int
    module_counts: Mapping[str, int]
    source_registry: Mapping[str, Mapping[str, str]]
    rules: tuple[RuleCatalogRule, ...]
    digest: str


def _package() -> Traversable:
    return importlib.resources.files(__package__)


def catalog_yaml_path() -> Traversable:
    return _package().joinpath(_CATALOG_YAML_NAME)


def catalog_schema_path() -> Traversable:
    return _package().joinpath(_CATALOG_SCHEMA_NAME)


def catalog_yaml_bytes() -> bytes:
    return catalog_yaml_path().read_bytes()


def catalog_schema_bytes() -> bytes:
    return catalog_schema_path().read_bytes()


def compute_catalog_digest(data: bytes) -> str:
    """Deterministic sha256 digest of the exact packaged catalog bytes."""
    return hashlib.sha256(data).hexdigest()


def _is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def validate_catalog_document(doc: Mapping[str, object]) -> None:
    """Validate a parsed catalog document, raising with every problem found."""
    errors: list[str] = []

    if not isinstance(doc, Mapping):
        raise RuleCatalogValidationError(["catalog document must be a mapping"])

    required_top_level = (
        "schema",
        "catalog_version",
        "generated_at",
        "rule_count",
        "modules",
        "source_registry",
        "rules",
    )
    for key in required_top_level:
        if key not in doc:
            errors.append(f"missing required top-level key: {key}")
    if errors:
        # Structural prerequisites are missing; further checks would just add noise.
        raise RuleCatalogValidationError(errors)

    if doc.get("schema") != CATALOG_SCHEMA_ID:
        errors.append(f"schema must equal {CATALOG_SCHEMA_ID!r}, got {doc.get('schema')!r}")
    if not _is_nonempty_str(doc.get("catalog_version")):
        errors.append("catalog_version must be a non-empty string")
    if not _is_nonempty_str(doc.get("generated_at")):
        errors.append("generated_at must be a non-empty string")

    rule_count = doc.get("rule_count")
    if not isinstance(rule_count, int) or isinstance(rule_count, bool) or rule_count < 1:
        errors.append("rule_count must be a positive integer")

    modules = doc.get("modules")
    module_counts: dict[str, int] = {}
    if not isinstance(modules, list) or not modules:
        errors.append("modules must be a non-empty list")
        modules = []
    for entry in modules:
        if not isinstance(entry, Mapping) or not _is_nonempty_str(entry.get("id")) or not isinstance(
            entry.get("count"), int
        ) or isinstance(entry.get("count"), bool) or entry.get("count") < 0:
            errors.append(f"invalid module entry: {entry!r}")
            continue
        module_id = str(entry["id"])
        if module_id in module_counts:
            errors.append(f"duplicate module id: {module_id}")
        module_counts[module_id] = int(entry["count"])

    source_registry = doc.get("source_registry")
    if not isinstance(source_registry, Mapping) or not source_registry:
        errors.append("source_registry must be a non-empty mapping")
        source_registry = {}
    for source_id, entry in source_registry.items():
        if not isinstance(entry, Mapping) or not _is_nonempty_str(entry.get("title")) or not _is_nonempty_str(
            entry.get("url")
        ):
            errors.append(f"invalid source_registry entry: {source_id!r}")
        elif not str(entry["url"]).startswith(("http://", "https://")):
            errors.append(f"source_registry entry {source_id!r} has a non-http(s) url")

    rules = doc.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append("rules must be a non-empty list")
        rules = []

    seen_rule_ids: set[str] = set()
    modules_used: set[str] = set()
    for index, rule in enumerate(rules):
        prefix = f"rules[{index}]"
        if not isinstance(rule, Mapping):
            errors.append(f"{prefix}: rule entry must be a mapping")
            continue

        rule_id = rule.get("rule_id")
        if not _is_nonempty_str(rule_id):
            errors.append(f"{prefix}: rule_id must be a non-empty string")
        elif not _RULE_ID_PATTERN.match(str(rule_id)):
            errors.append(
                f"{prefix}: rule_id {rule_id!r} does not match required pattern "
                f"{_RULE_ID_PATTERN.pattern!r}"
            )
        else:
            if rule_id in seen_rule_ids:
                errors.append(f"duplicate rule_id: {rule_id}")
            seen_rule_ids.add(str(rule_id))

        version = rule.get("version")
        if not _is_nonempty_str(version):
            errors.append(f"{prefix} ({rule_id}): version must be a non-empty string")
        elif not _SEMVER_PATTERN.match(str(version)):
            errors.append(
                f"{prefix} ({rule_id}): version {version!r} does not match required "
                f"pattern {_SEMVER_PATTERN.pattern!r} (x.y.z)"
            )

        if not _is_nonempty_str(rule.get("title")):
            errors.append(f"{prefix} ({rule_id}): title must be a non-empty string")

        module = rule.get("module")
        if not _is_nonempty_str(module):
            errors.append(f"{prefix} ({rule_id}): module must be a non-empty string")
        else:
            modules_used.add(str(module))
            if module not in module_counts:
                errors.append(f"{prefix} ({rule_id}): module {module!r} is not declared in modules")

        applicability = rule.get("applicability")
        if not isinstance(applicability, Mapping) or not _is_nonempty_str(
            applicability.get("applies_to")
        ) or not _is_nonempty_str(applicability.get("condition")):
            errors.append(f"{prefix} ({rule_id}): applicability requires applies_to and condition")

        fact_requirements = rule.get("fact_requirements")
        if not isinstance(fact_requirements, list) or not fact_requirements:
            errors.append(f"{prefix} ({rule_id}): fact_requirements must be a non-empty list")
        else:
            for req in fact_requirements:
                if not isinstance(req, Mapping) or not _is_nonempty_str(
                    req.get("family")
                ) or not _is_nonempty_str(req.get("min_schema_version")):
                    errors.append(
                        f"{prefix} ({rule_id}): fact_requirements item must have family and min_schema_version"
                    )

        source_ids = rule.get("source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            errors.append(f"{prefix} ({rule_id}): source_ids must be a non-empty list")
        else:
            for source_id in source_ids:
                if source_id not in source_registry:
                    errors.append(f"{prefix} ({rule_id}): unknown source_id {source_id!r}")

        score_role = rule.get("score_role")
        if score_role not in _VALID_SCORE_ROLES:
            errors.append(f"{prefix} ({rule_id}): score_role must be one of {sorted(_VALID_SCORE_ROLES)}")

        failure_policy = rule.get("failure_policy")
        if failure_policy not in _VALID_FAILURE_POLICIES:
            errors.append(
                f"{prefix} ({rule_id}): failure_policy must be one of {sorted(_VALID_FAILURE_POLICIES)}"
            )

        if not _is_nonempty_str(rule.get("summary")):
            errors.append(f"{prefix} ({rule_id}): summary must be a non-empty string")

        mechanism = rule.get("mechanism")
        if mechanism not in _VALID_MECHANISMS:
            errors.append(f"{prefix} ({rule_id}): mechanism must be one of {sorted(_VALID_MECHANISMS)}")

        rule_kind = rule.get("rule_kind")
        if rule_kind not in _VALID_RULE_KINDS:
            errors.append(f"{prefix} ({rule_id}): rule_kind must be one of {sorted(_VALID_RULE_KINDS)}")

        automation_mode = rule.get("automation_mode")
        if automation_mode not in _VALID_AUTOMATION_MODES:
            errors.append(
                f"{prefix} ({rule_id}): automation_mode must be one of {sorted(_VALID_AUTOMATION_MODES)}"
            )

        profiles = rule.get("profiles")
        if not isinstance(profiles, list) or not all(_is_nonempty_str(item) for item in profiles):
            errors.append(f"{prefix} ({rule_id}): profiles must be a list of non-empty strings")

        comparison_dimensions = rule.get("comparison_dimensions")
        if not isinstance(comparison_dimensions, list) or not all(
            _is_nonempty_str(item) for item in comparison_dimensions
        ):
            errors.append(f"{prefix} ({rule_id}): comparison_dimensions must be a list of non-empty strings")

        if not _is_nonempty_str(rule.get("verification_plan")):
            errors.append(f"{prefix} ({rule_id}): verification_plan must be a non-empty string")

    if isinstance(rule_count, int) and not isinstance(rule_count, bool) and rule_count != len(rules):
        errors.append(f"rule_count {rule_count} does not match number of rules {len(rules)}")

    if module_counts:
        declared_total = sum(module_counts.values())
        if isinstance(rule_count, int) and not isinstance(rule_count, bool) and declared_total != rule_count:
            errors.append(
                f"sum of module counts {declared_total} does not match rule_count {rule_count}"
            )
        for module_id, declared_count in module_counts.items():
            actual_count = sum(1 for rule in rules if isinstance(rule, Mapping) and rule.get("module") == module_id)
            if actual_count != declared_count:
                errors.append(
                    f"module {module_id!r} declares count {declared_count} but {actual_count} rules reference it"
                )
        undeclared = modules_used - set(module_counts)
        for module_id in sorted(undeclared):
            errors.append(f"module {module_id!r} is used by rules but not declared in modules")

    if errors:
        raise RuleCatalogValidationError(errors)


def _build_rule(entry: Mapping[str, object]) -> RuleCatalogRule:
    applicability = entry["applicability"]
    assert isinstance(applicability, Mapping)
    fact_requirements = tuple(
        RuleCatalogFactRequirement(family=str(item["family"]), min_schema_version=str(item["min_schema_version"]))
        for item in entry["fact_requirements"]  # type: ignore[union-attr]
    )
    return RuleCatalogRule(
        rule_id=str(entry["rule_id"]),
        version=str(entry["version"]),
        title=str(entry["title"]),
        module=str(entry["module"]),
        applies_to=str(applicability["applies_to"]),
        condition=str(applicability["condition"]),
        fact_requirements=fact_requirements,
        source_ids=tuple(str(item) for item in entry["source_ids"]),  # type: ignore[union-attr]
        score_role=str(entry["score_role"]),
        failure_policy=str(entry["failure_policy"]),
        summary=str(entry["summary"]),
        mechanism=str(entry["mechanism"]),
        rule_kind=str(entry["rule_kind"]),
        automation_mode=str(entry["automation_mode"]),
        profiles=tuple(str(item) for item in entry["profiles"]),  # type: ignore[union-attr]
        comparison_dimensions=tuple(str(item) for item in entry["comparison_dimensions"]),  # type: ignore[union-attr]
        verification_plan=str(entry["verification_plan"]),
    )


def parse_catalog_document(data: bytes) -> Mapping[str, object]:
    return yaml.safe_load(data)


def load_frozen_rule_catalog() -> RuleCatalogArtifact:
    """Load, validate, and return the packaged frozen rule catalog.

    Raises :class:`RuleCatalogValidationError` if the packaged artifact is
    missing required structure, has duplicate rule IDs, references unknown
    source IDs, or is otherwise inconsistent. Does not register or execute
    any rule.
    """
    data = catalog_yaml_bytes()
    document = parse_catalog_document(data)
    validate_catalog_document(document)

    module_counts = {str(item["id"]): int(item["count"]) for item in document["modules"]}  # type: ignore[index]
    rules = tuple(_build_rule(entry) for entry in document["rules"])  # type: ignore[index]

    return RuleCatalogArtifact(
        schema=str(document["schema"]),
        catalog_version=str(document["catalog_version"]),
        generated_at=str(document["generated_at"]),
        rule_count=int(document["rule_count"]),  # type: ignore[arg-type]
        module_counts=module_counts,
        source_registry=document["source_registry"],  # type: ignore[assignment]
        rules=rules,
        digest=compute_catalog_digest(data),
    )
