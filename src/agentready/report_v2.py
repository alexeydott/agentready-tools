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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "reason": self.reason,
            "fingerprint": self.fingerprint,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class Coverage:
    total_rules: int
    evaluated_rules: int
    applicable_rules: int
    complete_rules: int

    def to_dict(self) -> dict[str, int]:
        return {
            "total_rules": self.total_rules,
            "evaluated_rules": self.evaluated_rules,
            "applicable_rules": self.applicable_rules,
            "complete_rules": self.complete_rules,
        }


@dataclass(frozen=True, slots=True)
class AuditReport:
    target: str
    findings: tuple[Finding, ...]
    coverage: Coverage
    version: str = REPORT_VERSION
    evidence: tuple[FindingEvidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "target": self.target,
            "version": self.version,
            "coverage": self.coverage.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "findings": [item.to_dict() for item in self.findings],
        }


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
    complete = sum(item.status is FindingStatus.PASS for item in findings)
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
    coverage = Coverage(**payload["coverage"])
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


def diff_reports(current: AuditReport, baseline: Mapping[str, Any]) -> BaselineDiff:
    if baseline.get("schema") != SCHEMA:
        raise ValueError("baseline is not an agentready.audit.v2 report")
    if baseline.get("target") != current.target or baseline.get("version") != current.version:
        raise ValueError("baseline target or report version is not comparable")
    old = {item.get("id"): item.get("fingerprint") for item in baseline.get("findings", ()) if isinstance(item, Mapping)}
    new = {item.id: item.fingerprint for item in current.findings}
    return BaselineDiff(
        True,
        tuple(sorted(key for key in new.keys() & old.keys() if new[key] != old[key])),
        tuple(sorted(new.keys() - old.keys())),
        tuple(sorted(old.keys() - new.keys())),
    )


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
