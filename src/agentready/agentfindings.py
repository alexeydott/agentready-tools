"""Agent-facing audit findings for coding agents.

Builds a compact, actionable structure from readiness and SEO reports:
which checks failed or warned, why they matter, what evidence was observed,
and how a coding agent should fix each one. Pure domain logic — no transport
dependencies; MCP/CLI surfaces wrap these builders.
"""
from __future__ import annotations

import logging
from typing import Any

from .i18n import (
    agent_prompt,
    category_name,
    check_hint,
    check_title,
    detail_text,
    guidance,
    normalize_language,
)
from .mobile_models import MobilePageReport
from .models import Remediation, ScanReport
from .seo_checks import SEO_CHECK_METADATA
from .seo_models import SeoReport

logger = logging.getLogger(__name__)

PROBLEM_STATUSES = frozenset({"fail", "warn", "error"})

_SEO_METADATA = {item["id"]: item for item in SEO_CHECK_METADATA}

_MESSAGES = {
    "en": {
        "no_findings": "No optimization gaps found. All audited checks passed.",
        "plan_intro": "Fix the website issues below in priority order. After each fix, re-run the listed verification command.",
        "readiness_subject": "AI-agent readiness",
        "seo_subject": "SEO optimization",
        "mobile_subject": "mobile-friendliness",
    },
    "ru": {
        "no_findings": "Недочёты оптимизации не найдены. Все проверенные проверки пройдены.",
        "plan_intro": "Исправьте перечисленные ниже проблемы сайта в порядке приоритета. После каждого исправления повторите указанную проверочную команду.",
        "readiness_subject": "готовности к ИИ-агентам",
        "seo_subject": "SEO-оптимизации",
        "mobile_subject": "мобильной дружественности",
    },
}


def _msg(key: str, lang: str) -> str:
    return _MESSAGES[normalize_language(lang)][key]


def _target_of(report: Any) -> str:
    return getattr(report, "target", None) or getattr(report, "url", "")


def _evidence_summary(check: Any, lang: str, *, limit: int = 3) -> list[str]:
    findings: list[str] = []
    for item in check.evidence:
        text = item.finding or item.action
        if not text:
            continue
        if item.finding:
            text = detail_text(check.id, text, lang)
        if item.url:
            text = f"page/resource: {item.url}; {text}"
        findings.append(text)
        if len(findings) >= limit:
            break
    return findings


def _seo_localized(check_id: str, title: str, category: str, lang: str) -> tuple[str, str]:
    metadata = _SEO_METADATA.get(check_id)
    if metadata is None:
        return title, category_name(category, lang)
    active = normalize_language(lang)
    return (
        metadata.get("title", {}).get(active, title),
        metadata.get("category", {}).get(active, category),
    )


def _finding(check: Any, target: str, lang: str, *, seo: bool) -> dict[str, Any]:
    if seo:
        title, category = _seo_localized(check.id, check.title, check.category, lang)
        why = check_hint(check.id, check.title, check.category, lang)
    else:
        title = check_title(check.id, check.title, lang)
        category = category_name(check.category, lang)
        why = check_hint(check.id, check.title, check.category, lang)

    remediation = check.remediation or Remediation(
        summary="Review the protocol specification and publish a valid implementation.",
        rerun_command=f"agentready scan {target!r} --only {check.id}",
    )
    summary = guidance(check.id, remediation.summary, lang)
    prompt = agent_prompt(check.id, target, remediation.summary, lang)
    if seo and normalize_language(lang) == "ru" and "agentready scan" in prompt:
        prompt = prompt.replace("agentready scan", "agentready seo audit", 1)
        prompt = prompt.replace(" --only ", " --checks ", 1)

    return {
        "check_id": check.id,
        "title": title,
        "category": category,
        "status": check.status,
        "details": detail_text(check.id, check.details, lang),
        "why": why,
        "evidence": _evidence_summary(check, lang),
        "remediation": {
            "summary": summary,
            "instructions": summary,
            "agent_prompt": prompt,
            "rerun_command": remediation.rerun_command,
            "references": list(remediation.references),
        },
    }


def _priority_map(report: Any) -> dict[str, tuple[int, str, str]]:
    """Map check_id -> (priority rank, impact, effort) from report recommendations."""
    ranked: dict[str, tuple[int, str, str]] = {}
    for index, rec in enumerate(report.recommendations, 1):
        ranked[rec.check_id] = (index, rec.impact, rec.effort)
    return ranked


def build_findings(report: ScanReport | SeoReport | MobilePageReport, lang: str | None = None) -> dict[str, Any]:
    """Build an agent-facing findings payload from a readiness, SEO or mobile report.

    Only failing/warning/error checks are included. Machine identifiers stay
    stable; human-facing fields follow ``lang``.
    """
    language = normalize_language(lang or getattr(report, "language", None))
    is_seo = isinstance(report, SeoReport)
    is_mobile = isinstance(report, MobilePageReport)
    target = _target_of(report)
    logger.debug(
        "build_findings: target=%s seo=%s mobile=%s checks=%d lang=%s",
        target,
        is_seo,
        is_mobile,
        len(report.checks),
        language,
    )
    ranked = _priority_map(report)
    findings: list[dict[str, Any]] = []
    for check in report.checks:
        if check.status not in PROBLEM_STATUSES:
            continue
        item = _finding(check, target, language, seo=is_seo or is_mobile)
        priority = ranked.get(check.id)
        item["priority"] = priority[0] if priority else None
        item["impact"] = priority[1] if priority else "low"
        item["effort"] = priority[2] if priority else "medium"
        findings.append(item)
    findings.sort(key=lambda item: (item["priority"] is None, item["priority"] or 9999))
    logger.debug("build_findings: emitted=%d of %d", len(findings), len(report.checks))
    mode = "mobile" if is_mobile else ("seo" if is_seo else "readiness")
    return {
        "schema": "agentready.findings.v1",
        "mode": mode,
        "target": target,
        "score": report.score,
        "language": language,
        "findings_count": len(findings),
        "findings": findings,
        "message": _msg("no_findings", language) if not findings else None,
    }


def build_remediation_plan(report: ScanReport | SeoReport | MobilePageReport, lang: str | None = None) -> dict[str, Any]:
    """Build an ordered fix plan for a coding agent from an audit report.

    Findings are ordered by recommendation priority; each step carries a
    ready-to-use agent prompt and a verification command.
    """
    language = normalize_language(lang or getattr(report, "language", None))
    payload = build_findings(report, language)
    target = payload["target"]
    steps: list[dict[str, Any]] = []
    for index, item in enumerate(payload["findings"], 1):
        steps.append(
            {
                "step": index,
                "check_id": item["check_id"],
                "title": item["title"],
                "impact": item["impact"],
                "effort": item["effort"],
                "instructions": item["remediation"]["instructions"],
                "agent_prompt": item["remediation"]["agent_prompt"],
                "verify": item["remediation"]["rerun_command"],
                "references": item["remediation"]["references"],
            }
        )
    logger.debug("build_remediation_plan: steps=%d target=%s", len(steps), target)
    mode = payload["mode"]
    subject_key = {"readiness": "readiness_subject", "seo": "seo_subject", "mobile": "mobile_subject"}[mode]
    return {
        "schema": "agentready.remediation-plan.v1",
        "mode": mode,
        "target": target,
        "language": language,
        "subject": _msg(subject_key, language),
        "intro": _msg("plan_intro", language),
        "steps_count": len(steps),
        "steps": steps,
        "message": payload["message"],
    }
