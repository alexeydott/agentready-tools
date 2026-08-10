"""Bounded, allowlisted audit context for AI prompts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .seo_i18n import seo_detail, seo_summary

MAX_REPORT_BYTES = 2_000_000
ALLOWED_SCHEMAS = {"agentready.seo.v1", "agentready.scan.v1"}


class AIContextError(ValueError):
    pass


def load_report_file(path: str | Path) -> dict[str, Any]:
    selected = Path(path).expanduser().resolve()
    if not selected.is_file():
        raise AIContextError(f"report file not found: {selected}")
    if selected.stat().st_size > MAX_REPORT_BYTES:
        raise AIContextError("report file exceeds the AI context size limit")
    try:
        value = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AIContextError("report file is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise AIContextError("report root must be an object")
    validate_report(value)
    return value


def validate_report(report: dict[str, Any]) -> None:
    if report.get("schema", "agentready.scan.v1") not in ALLOWED_SCHEMAS:
        raise AIContextError("unsupported report schema")
    if not isinstance(report.get("checks"), list):
        raise AIContextError("report checks must be a list")
    if len(report["checks"]) > 500:
        raise AIContextError("report contains too many checks")


def project_report(report: dict[str, Any], *, mode: str, language: str, limit: int = 12000) -> dict[str, Any]:
    """Project only deterministic findings and bounded remediation metadata."""
    validate_report(report)
    if mode not in {"seo", "geo", "both"}:
        raise AIContextError("unsupported assistant mode")
    schema = report.get("schema", "agentready.scan.v1")
    projected: dict[str, Any] = {
        "schema": schema,
        "mode": mode,
        "target": _short(report.get("target") or report.get("url"), 500),
        "score": report.get("score"),
        "checks": [],
        "recommendations": [],
    }
    for check in report["checks"]:
        if not isinstance(check, dict) or not isinstance(check.get("id"), str):
            continue
        status = check.get("status")
        if status not in {"fail", "warn", "error", "pass", "skip"}:
            continue
        check_id = check["id"]
        details = _short(str(check.get("details") or ""), 600)
        remediation = check.get("remediation") if isinstance(check.get("remediation"), dict) else {}
        projected["checks"].append({
            "id": check_id,
            "status": status,
            "title": _short(str(check.get("title") or check_id), 200),
            "details": seo_detail(details, language) if schema == "agentready.seo.v1" else details,
            "remediation": seo_summary(check_id, _short(str(remediation.get("summary") or ""), 500), language)
            if schema == "agentready.seo.v1" else _short(str(remediation.get("summary") or ""), 500),
            "evidence": _project_evidence(check.get("evidence")),
        })
        if len(projected["checks"]) >= 500:
            break
    for recommendation in report.get("recommendations", [])[:100]:
        if isinstance(recommendation, dict):
            projected["recommendations"].append({
                "check_id": _short(str(recommendation.get("check_id") or ""), 100),
                "priority": recommendation.get("priority"),
                "impact": recommendation.get("impact"),
                "effort": recommendation.get("effort"),
                "action": seo_summary(
                    str(recommendation.get("check_id") or ""),
                    _short(str(recommendation.get("action") or ""), 500),
                    language,
                ) if schema == "agentready.seo.v1" else _short(str(recommendation.get("action") or ""), 500),
            })
    encoded = json.dumps(projected, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > limit:
        projected["checks"] = projected["checks"][: max(1, len(projected["checks"]) // 2)]
        projected["recommendations"] = projected["recommendations"][:20]
        encoded = json.dumps(projected, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > limit:
        raise AIContextError("projected report exceeds the AI context size limit")
    return projected


def _short(value: Any, limit: int) -> str:
    return str(value or "")[:limit]


def _project_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    projected: list[dict[str, Any]] = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        evidence: dict[str, Any] = {}
        for key in ("action", "url", "method", "status_code", "content_type", "finding"):
            if item.get(key) not in (None, ""):
                evidence[key] = _short(item[key], 1000)
        if isinstance(item.get("metrics"), dict):
            evidence["metrics"] = _project_value(item["metrics"])
        if evidence:
            projected.append(evidence)
    return projected


def _project_value(value: Any, depth: int = 0) -> Any:
    if depth >= 3:
        return _short(value, 500)
    if isinstance(value, dict):
        return {str(key)[:100]: _project_value(item, depth + 1) for key, item in list(value.items())[:30]}
    if isinstance(value, (list, tuple)):
        return [_project_value(item, depth + 1) for item in value[:100]]
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _short(value, 500)
