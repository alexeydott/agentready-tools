"""SEO/GEO assistant orchestration independent of CLI, HTTP, and MCP."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .ai_context import project_report
from .ai_i18n import ai_text
from .ai_models import (
    AssistantAction,
    AssistantRequest,
    AssistantResponse,
    AssistantUsage,
    EvidenceReference,
)
from .ai_prompts import build_prompts
from .ai_provider import AIProvider, ProviderResult

logger = logging.getLogger(__name__)


class AIAssistant:
    def __init__(
        self,
        provider: AIProvider,
        *,
        context_limit: int = 12000,
        history_limit: int = 12,
        message_limit: int = 4000,
        output_limit: int = 4000,
        max_concurrent: int = 2,
    ) -> None:
        self.provider = provider
        self.context_limit = context_limit
        self.history_limit = history_limit
        self.message_limit = message_limit
        self.output_limit = output_limit
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, request: AssistantRequest, *, model: str) -> AssistantResponse:
        language = request.language
        context = project_report(request.report or _empty_report(request.target), mode=request.mode, language=language, limit=self.context_limit)
        message = (request.message or "")[: self.message_limit]
        history = request.history[-self.history_limit :]
        if history:
            message += "\nHISTORY_START\n" + "\n".join(f"{item.role}: {item.content[:self.message_limit]}" for item in history) + "\nHISTORY_END"
        system, user = build_prompts(
            mode=request.mode,
            language=language,
            context=context,
            message=message or None,
            skills=request.skills or ("seo-security-interpreter",),
            mcp_context=request.mcp_context,
            attachments=request.attachments,
        )
        logger.info("Starting AI assistant operation=%s mode=%s language=%s", request.operation, request.mode, language)
        async with self._semaphore:
            result = await self.provider.complete(system=system, user=user, model=model, language=language)
        response = _response_from_provider(request, result, model=model, output_limit=self.output_limit)
        response.disclaimer = ai_text("disclaimer", language)
        return response


def _response_from_provider(
    request: AssistantRequest,
    result: ProviderResult,
    *,
    model: str,
    output_limit: int,
) -> AssistantResponse:
    data = result.data
    summary = str(data.get("summary") or ai_text("summary", request.language))[:output_limit]
    actions: list[AssistantAction] = []
    for item in data.get("actions", [])[:20]:
        if not isinstance(item, dict):
            continue
        priority = item.get("priority")
        if priority not in {"high", "medium", "low"}:
            priority = "medium"
        actions.append(AssistantAction(
            title=str(item.get("title") or ai_text("default_action", request.language))[:300],
            action=str(item.get("action") or "")[:output_limit],
            priority=priority,
            check_ids=tuple(str(value)[:100] for value in item.get("check_ids", [])[:20]) if isinstance(item.get("check_ids"), list) else (),
            verification=tuple(str(value)[:300] for value in item.get("verification", [])[:10]) if isinstance(item.get("verification"), list) else (),
        ))
    cautions = [str(value)[:500] for value in data.get("cautions", [])[:10]] if isinstance(data.get("cautions"), list) else []
    return AssistantResponse(
        operation=request.operation,
        mode=request.mode,
        language=request.language,
        target=request.target,
        model=model,
        summary=summary,
        actions=actions,
        evidence=_evidence_from_request(request),
        cautions=cautions,
        usage=AssistantUsage(**result.usage) if result.usage else None,
    )


def _evidence_from_request(request: AssistantRequest) -> list[EvidenceReference]:
    if not request.report:
        return []
    references: list[EvidenceReference] = []
    for check in request.report.get("checks", [])[:100]:
        if not isinstance(check, dict) or check.get("status") not in {"fail", "warn", "error"}:
            continue
        evidence_items = check.get("evidence") if isinstance(check.get("evidence"), list) else []
        first = evidence_items[0] if evidence_items and isinstance(evidence_items[0], dict) else {}
        references.append(
            EvidenceReference(
                check_id=str(check.get("id")),
                status=str(check.get("status")),
                details=str(check.get("details") or "")[:600],
                evidence=tuple(
                    str(item.get("action") or item.get("finding") or "")[:500]
                    for item in evidence_items[:5]
                    if isinstance(item, dict) and (item.get("action") or item.get("finding"))
                ),
                source_url=str(first.get("url"))[:1000] if first.get("url") else None,
                metrics=_bounded_metrics(first.get("metrics")),
            )
        )
    return references


def _bounded_metrics(value: Any, depth: int = 0) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    if depth >= 3:
        return {str(key)[:100]: str(item)[:500] for key, item in list(value.items())[:30]}
    result: dict[str, Any] = {}
    for key, item in list(value.items())[:30]:
        if isinstance(item, dict):
            result[str(key)[:100]] = _bounded_metrics(item, depth + 1)
        elif isinstance(item, list):
            result[str(key)[:100]] = [
                _bounded_metrics(entry, depth + 1) if isinstance(entry, dict) else str(entry)[:1000]
                for entry in item[:100]
            ]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            result[str(key)[:100]] = item if not isinstance(item, str) else item[:1000]
    return result


def _empty_report(target: str | None) -> dict[str, Any]:
    return {"schema": "agentready.audit.v2", "target": target or "", "findings": []}
