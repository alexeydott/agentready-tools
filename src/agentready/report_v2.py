"""Canonical v2 report, config, diff, inventory, and export contracts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)

SCHEMA = "agentready.audit.v2"
REPORT_VERSION = "v2"
MAX_PAGES = 100
MAX_TIMEOUT = 30.0


@dataclass(frozen=True, slots=True)
class AuditConfig:
    target: str
    preset: str = "all"
    timeout: float = 5.0
    max_pages: int = 25
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    explicit_operation: bool = False
    credential_ref: str | None = None

    @classmethod
    def from_sources(
        cls,
        *,
        target: str,
        file_values: Mapping[str, Any] | None = None,
        environment: Mapping[str, str] | None = None,
        cli_values: Mapping[str, Any] | None = None,
    ) -> "AuditConfig":
        """Merge CLI over environment over legacy/current config file values."""
        file_values = file_values or {}
        environment = environment or {}
        cli_values = cli_values or {}
        network = file_values.get("network", {}) if isinstance(file_values.get("network", {}), Mapping) else {}
        values: dict[str, Any] = {
            "preset": file_values.get("preset", "all"),
            "timeout": network.get("timeout", 5.0),
            "max_pages": file_values.get("max_pages", network.get("max_pages", 25)),
        }
        if "AGENTREADY_TIMEOUT" in environment:
            values["timeout"] = float(environment["AGENTREADY_TIMEOUT"])
        if "AGENTREADY_MAX_PAGES" in environment:
            values["max_pages"] = int(environment["AGENTREADY_MAX_PAGES"])
        values.update({key: value for key, value in cli_values.items() if value is not None})
        return cls(target, **values)

    def __post_init__(self) -> None:
        if not self.target:
            raise ValueError("audit target is required")
        if not 0 < self.timeout <= MAX_TIMEOUT:
            raise ValueError(f"timeout must be between 0 and {MAX_TIMEOUT:g} seconds")
        if not 0 < self.max_pages <= MAX_PAGES:
            raise ValueError(f"max_pages must be between 1 and {MAX_PAGES}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "preset": self.preset,
            "timeout": self.timeout,
            "max_pages": self.max_pages,
            "include": list(self.include),
            "exclude": list(self.exclude),
            "explicit_operation": self.explicit_operation,
            "credential_ref": self.credential_ref,
        }


class FindingStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class FindingEvidence:
    id: str
    summary: str
    url: str | None = None

    def to_dict(self) -> dict[str, str]:
        result = {"id": self.id, "summary": self.summary}
        if self.url is not None:
            result["url"] = self.url
        return result


@dataclass(frozen=True, slots=True)
class Finding:
    id: str
    title: str
    status: FindingStatus
    reason: str
    evidence: tuple[FindingEvidence, ...] = ()

    @property
    def fingerprint(self) -> str:
        payload = {
            "id": self.id,
            "status": self.status.value,
            "reason": self.reason,
            "evidence": [item.to_dict() for item in self.evidence],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @property
    def state_hash(self) -> str:
        payload = {
            "id": self.id,
            "status": self.status.value,
            "evidence": [{"id": item.id, "url": item.url} for item in self.evidence],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "reason": self.reason,
            "fingerprint": self.fingerprint,
            "state_hash": self.state_hash,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class Coverage:
    total_rules: int
    evaluated_rules: int
    applicable_rules: int
    complete_rules: int
    urls_discovered: int | None = None
    urls_fetched: int | None = None
    max_pages_hit: bool | None = None
    classification: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "total_rules": self.total_rules,
            "evaluated_rules": self.evaluated_rules,
            "applicable_rules": self.applicable_rules,
            "complete_rules": self.complete_rules,
        }
        if self.urls_discovered is not None:
            result["urls_discovered"] = self.urls_discovered
        if self.urls_fetched is not None:
            result["urls_fetched"] = self.urls_fetched
        if self.max_pages_hit is not None:
            result["limit"] = {"max_pages_hit": self.max_pages_hit}
        if self.classification is not None:
            result["classification"] = self.classification
        return result


@dataclass(frozen=True, slots=True)
class AuditReport:
    target: str
    findings: tuple[Finding, ...]
    coverage: Coverage
    version: str = REPORT_VERSION
    evidence: tuple[FindingEvidence, ...] = ()
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema": SCHEMA,
            "target": self.target,
            "version": self.version,
            "coverage": self.coverage.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "findings": [item.to_dict() for item in self.findings],
        }
        if self.run_id is not None:
            result["run_id"] = self.run_id
        return result


def report_from_checks(target: str, checks: Iterable[Any]) -> AuditReport:
    findings: list[Finding] = []
    evidence: list[FindingEvidence] = []
    for check in checks:
        check_evidence = tuple(
            FindingEvidence(f"{check.id}:{index}", item.finding or item.action, item.url)
            for index, item in enumerate(getattr(check, "evidence", ()))
        )
        evidence.extend(check_evidence)
        raw_status = getattr(check, "status", "unavailable")
        status = FindingStatus("unavailable" if raw_status == "error" else raw_status)
        findings.append(Finding(check.id, check.title, status, check.details, check_evidence))
    applicable = sum(item.status not in {FindingStatus.SKIP, FindingStatus.UNAVAILABLE} for item in findings)
    complete = sum(
        item.status in {FindingStatus.PASS, FindingStatus.FAIL, FindingStatus.WARN}
        for item in findings
    )
    return AuditReport(target, tuple(findings), Coverage(len(findings), len(findings), applicable, complete), evidence=tuple(evidence))


def report_from_dict(payload: Mapping[str, Any]) -> AuditReport:
    if payload.get("schema") != SCHEMA:
        raise ValueError("payload is not an agentready.audit.v2 report")
    findings = tuple(
        Finding(
            item["id"],
            item.get("title", item["id"]),
            FindingStatus(item["status"]),
            item.get("reason", ""),
            tuple(FindingEvidence(e["id"], e["summary"], e.get("url")) for e in item.get("evidence", ())),
        )
        for item in payload.get("findings", ())
    )
    coverage_payload = payload["coverage"]
    coverage = Coverage(
        total_rules=coverage_payload["total_rules"],
        evaluated_rules=coverage_payload["evaluated_rules"],
        applicable_rules=coverage_payload["applicable_rules"],
        complete_rules=coverage_payload["complete_rules"],
        urls_discovered=coverage_payload.get("urls_discovered"),
        urls_fetched=coverage_payload.get("urls_fetched"),
        max_pages_hit=(coverage_payload.get("limit") or {}).get("max_pages_hit"),
        classification=coverage_payload.get("classification"),
    )
    return AuditReport(payload["target"], findings, coverage, payload.get("version", REPORT_VERSION))


def adapt_legacy_baseline(payload: Mapping[str, Any]) -> AuditReport:
    """Convert a v1 report to a comparable v2-shaped baseline without guessing evidence."""
    if payload.get("schema") not in {"agentready.audit.v1", "agentready.seo.v1"}:
        raise ValueError("baseline is not a supported v1 report")
    checks = payload.get("checks", ())
    findings = tuple(
        Finding(
            item.get("id", "legacy"),
            item.get("title", item.get("id", "legacy")),
            FindingStatus("unavailable" if item.get("status") == "error" else item.get("status", "unavailable")),
            item.get("details", "legacy baseline"),
        )
        for item in checks
        if isinstance(item, Mapping)
    )
    return AuditReport(payload.get("target", ""), findings, Coverage(len(findings), len(findings), len(findings), 0))


@dataclass(frozen=True, slots=True)
class BaselineDiff:
    comparable: bool
    changed: tuple[str, ...] = ()
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparable": self.comparable,
            "changed": list(self.changed),
            "added": list(self.added),
            "removed": list(self.removed),
            "reason": self.reason,
        }


def classify_finding_changes(
    current: AuditReport,
    baseline: Mapping[str, Any],
) -> dict[str, tuple[str, ...]]:
    """Classify stable finding state changes without localized prose."""
    old = {
        item.get("id"): item
        for item in baseline.get("findings", ())
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    new = {item.id: item for item in current.findings}
    severity = {"pass": 0, "skip": 0, "unavailable": 1, "warn": 2, "fail": 3}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    resolved: list[str] = []
    regressed: list[str] = []
    changed: list[str] = []
    unchanged: list[str] = []
    for finding_id in sorted(set(new) & set(old)):
        old_item = old[finding_id]
        current = new[finding_id]
        old_state_hash = old_item.get("state_hash")
        old_fingerprint = old_item.get("fingerprint")
        if old_state_hash is not None and old_state_hash == current.state_hash:
            unchanged.append(finding_id)
            continue
        if old_state_hash is None and old_fingerprint is not None and old_fingerprint == current.fingerprint:
            unchanged.append(finding_id)
            continue
        if old_state_hash is None and old_fingerprint is None:
            if old_item.get("status") == current.status.value:
                unchanged.append(finding_id)
                continue
        before = severity.get(str(old_item.get("status", "unavailable")), 1)
        after = severity.get(current.status.value, 1)
        if after > before:
            regressed.append(finding_id)
        elif after < before:
            resolved.append(finding_id)
        else:
            changed.append(finding_id)
    return {
        "added": tuple(added),
        "removed": tuple(removed),
        "resolved": tuple(resolved),
        "regressed": tuple(regressed),
        "changed": tuple(changed),
        "unchanged": tuple(unchanged),
    }


def diff_reports(current: AuditReport, baseline: Mapping[str, Any]) -> BaselineDiff:
    if baseline.get("schema") != SCHEMA:
        raise ValueError("baseline is not an agentready.audit.v2 report")
    if baseline.get("target") != current.target or baseline.get("version") != current.version:
        raise ValueError("baseline target or report version is not comparable")
    old = {
        item.get("id"): (
            "state_hash",
            item.get("state_hash"),
        ) if item.get("state_hash") is not None else (
            "fingerprint",
            item.get("fingerprint"),
        )
        for item in baseline.get("findings", ())
        if isinstance(item, Mapping)
    }
    new = {item.id: item for item in current.findings}
    return BaselineDiff(
        True,
        tuple(
            sorted(
                key
                for key in new.keys() & old.keys()
                if (
                    old[key][0] == "state_hash"
                    and old[key][1] != new[key].state_hash
                )
                or (
                    old[key][0] == "fingerprint"
                    and old[key][1] != new[key].fingerprint
                )
            )
        ),
        tuple(sorted(new.keys() - old.keys())),
        tuple(sorted(old.keys() - new.keys())),
    )


def diff_inventory(
    current: Mapping[str, Iterable[Mapping[str, Any]]],
    baseline: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, dict[str, tuple[str, ...]]]:
    """Compare bounded technical/link/indexability/metric projections by stable state."""
    result: dict[str, dict[str, tuple[str, ...]]] = {}
    for category in sorted(set(current) | set(baseline)):
        old = {_inventory_key(row): _inventory_state(row) for row in baseline.get(category, ())}
        new = {_inventory_key(row): _inventory_state(row) for row in current.get(category, ())}
        result[category] = {
            "added": tuple(sorted(set(new) - set(old))),
            "removed": tuple(sorted(set(old) - set(new))),
            "changed": tuple(sorted(key for key in set(new) & set(old) if new[key] != old[key])),
            "unchanged": tuple(sorted(key for key in set(new) & set(old) if new[key] == old[key])),
        }
    return result


def _inventory_key(row: Mapping[str, Any]) -> str:
    for field_name in ("id", "url", "url_key", "source_key", "name"):
        value = row.get(field_name)
        if isinstance(value, str) and value:
            return value
    return hashlib.sha256(
        json.dumps(dict(row), sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _inventory_state(row: Mapping[str, Any]) -> str:
    state = row.get("state_hash")
    if isinstance(state, str) and state:
        return state
    return hashlib.sha256(
        json.dumps(dict(row), sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def paginate_inventory(items: Iterable[Mapping[str, Any]], *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    if page < 1 or not 0 < page_size <= 100:
        raise ValueError("page must be positive and page_size must be between 1 and 100")
    materialized = list(items)
    start = (page - 1) * page_size
    return {
        "page": page,
        "page_size": page_size,
        "total": len(materialized),
        "items": materialized[start : start + page_size],
        "has_next": start + page_size < len(materialized),
    }


def export_inventory(items: Iterable[Mapping[str, Any]], *, format: str = "jsonl") -> str:
    rows = list(items)
    if format == "jsonl":
        return "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    if format == "csv":
        fields = sorted({key for row in rows for key in row})
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()
    raise ValueError("format must be jsonl or csv")
