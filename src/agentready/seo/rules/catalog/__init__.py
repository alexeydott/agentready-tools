"""Immutable frozen rule-catalog package data for Stage D (#17).

This subpackage ships the exact frozen v2.1.0-draft.1 rule catalog as
runtime package data (YAML + JSON Schema), plus a validating loader.

Nothing in this issue registers or executes catalog rules against live
audits. `load_frozen_rule_catalog()` only proves the packaged artifact is
present, well-formed, internally consistent, and byte-deterministic.
"""
from __future__ import annotations

from .loader import (
    CATALOG_SCHEMA_ID,
    RuleCatalogArtifact,
    RuleCatalogRule,
    RuleCatalogValidationError,
    catalog_schema_bytes,
    catalog_schema_path,
    catalog_yaml_bytes,
    catalog_yaml_path,
    compute_catalog_digest,
    load_frozen_rule_catalog,
    validate_catalog_document,
)
from .rule_semantics import (
    SEMANTICS_SCHEMA_ID,
    AcceptedCondition,
    RequirementAmendment,
    RuleSemanticsDocument,
    RuleSemanticsError,
    compute_semantics_digest,
    load_rule_semantics,
)

__all__ = [
    "CATALOG_SCHEMA_ID",
    "RuleCatalogArtifact",
    "RuleCatalogRule",
    "RuleCatalogValidationError",
    "catalog_schema_bytes",
    "catalog_schema_path",
    "catalog_yaml_bytes",
    "catalog_yaml_path",
    "compute_catalog_digest",
    "load_frozen_rule_catalog",
    "validate_catalog_document",
    "SEMANTICS_SCHEMA_ID",
    "AcceptedCondition",
    "RequirementAmendment",
    "RuleSemanticsDocument",
    "RuleSemanticsError",
    "compute_semantics_digest",
    "load_rule_semantics",
]
