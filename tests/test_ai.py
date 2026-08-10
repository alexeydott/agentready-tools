import asyncio
import sys
from types import SimpleNamespace

import pytest

from agentready.ai_assistant import AIAssistant
from agentready.ai_context import AIContextError, project_report
from agentready.ai_i18n import ai_catalog, ai_catalog_keys, ai_text
from agentready.ai_models import AssistantRequest
from agentready.ai_prompts import ai_skill_catalog, build_prompts
from agentready.ai_provider import AIProviderConfigurationError, OpenAICompatibleProvider, ProviderModel, ProviderResult, model_capabilities, validate_base_url
from agentready.config import active_ai_provider, load_config, save_ai_provider_config


class FakeProvider:
    async def complete(self, **kwargs):
        return ProviderResult(
            data={
                "summary": "Fix metadata",
                "actions": [{"title": "Title", "action": "Improve title", "priority": "high", "check_ids": ["page-metadata"]}],
            },
            usage={"total_tokens": 3},
        )


def seo_report():
    return {
        "schema": "agentready.seo.v1",
        "target": "https://example.com",
        "score": 50,
        "checks": [{
            "id": "title-length",
            "status": "fail",
            "title": "Title length",
            "details": "Title is too short",
            "remediation": {"summary": "Keep title between 30 and 60 characters."},
        }],
        "recommendations": [],
    }


def test_ai_context_is_bounded_and_localized():
    projected = project_report(seo_report(), mode="seo", language="ru", limit=12000)
    assert projected["checks"][0]["remediation"].startswith("Держите")
    assert "Keep title" not in projected["checks"][0]["remediation"]


def test_ai_context_preserves_structured_evidence():
    report = seo_report()
    report["checks"][0]["evidence"] = [{
        "action": "inspect title",
        "url": "https://example.com",
        "metrics": {"page": "https://example.com", "length": 12},
    }]
    projected = project_report(report, mode="seo", language="en")
    assert projected["checks"][0]["evidence"][0]["metrics"]["length"] == 12
    assert projected["checks"][0]["evidence"][0]["url"] == "https://example.com"


def test_ai_context_rejects_unsupported_schema():
    with pytest.raises(AIContextError):
        project_report({"schema": "unknown", "checks": []}, mode="seo", language="en")


def test_ai_context_accepts_readiness_reports_without_schema():
    projected = project_report({"target": "https://example.com", "checks": []}, mode="both", language="en")
    assert projected["schema"] == "agentready.scan.v1"


def test_provider_url_rejects_unsafe_overrides():
    with pytest.raises(AIProviderConfigurationError):
        validate_base_url("https://user:pass@example.com/v1")
    with pytest.raises(AIProviderConfigurationError):
        validate_base_url("http://example.com/v1", allow_loopback_http=True)
    assert validate_base_url("http://127.0.0.1:8080/v1", allow_loopback_http=True).endswith("/v1")


def test_provider_model_capabilities_use_metadata_and_common_id_heuristics():
    assert model_capabilities("text-embedding-3-small") == ("embedding",)
    assert model_capabilities("custom-model", {"capabilities": {"chat": True, "rerank": False}}) == ("chat",)
    assert model_capabilities("unknown-model") == ("other",)
    assert ProviderModel("gpt-4o", ("chat",), "openai").to_dict() == {
        "id": "gpt-4o",
        "capabilities": ["chat"],
        "owned_by": "openai",
    }


def test_provider_retries_not_found_model_with_catalog_chat_model(monkeypatch):
    calls = []

    class NotFoundError(Exception):
        status_code = 404

    class Completions:
        async def create(self, **kwargs):
            calls.append(kwargs["model"])
            if len(calls) == 1:
                raise NotFoundError("model not found")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
                usage=None,
                _request_id=None,
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=Completions())

        async def close(self):
            return None

    monkeypatch.setattr("agentready.ai_provider.load_api_key", lambda credential_id: ("secret", "test"))
    monkeypatch.setattr(
        OpenAICompatibleProvider,
        "list_models",
        lambda self: _resolved_models([ProviderModel("provider-chat", ("chat",))]),
    )
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=FakeClient))
    provider = OpenAICompatibleProvider(base_url="https://provider.example/v1", credential_id="provider-key", max_retries=0)
    result = asyncio.run(provider.complete(system="system", user="user", model="gpt-4o-mini", language="en"))
    assert result.data == {"ok": True}
    assert calls == ["gpt-4o-mini", "provider-chat"]


def _resolved_models(models):
    async def resolve():
        return models
    return resolve()


def test_catalog_keys_match_for_english_and_russian():
    assert ai_catalog_keys() == ai_catalog("ru").keys()
    assert ai_text("disclaimer", "ru")


def test_prompt_requires_current_interface_language():
    system, _ = build_prompts(mode="seo", language="ru", context={"schema": "agentready.seo.v1"})
    assert "MUST answer exclusively in the current interface language 'ru'" in system
    assert "structured evidence metrics" in system
    assert "page URL, resource URL" in system


def test_prompt_includes_selected_skills_mcp_context_and_attachments():
    _, user = build_prompts(
        mode="both",
        language="en",
        context={"schema": "agentready.seo.v1"},
        skills=("audit-analyst",),
        mcp_context={"tool": "agentready.seo_findings"},
        attachments=({"name": "notes.md", "content": "Check the canonical URL."},),
    )
    assert "SKILLS_SELECTED_START" in user
    assert "SKILL_INSTRUCTIONS_START" in user
    assert "Prioritize confirmed audit findings" in user
    assert "AGENTREADY_MCP_CONTEXT_START" in user
    assert "FILE_NAME: notes.md" in user


def test_seo_security_skill_is_localized_and_available():
    english = next(item for item in ai_skill_catalog("en") if item["id"] == "seo-security-interpreter")
    russian = next(item for item in ai_skill_catalog("ru") if item["id"] == "seo-security-interpreter")
    assert english["title"] == "SEO security interpreter"
    assert russian["title"] == "Интерпретатор SEO-безопасности"
    assert "possible SEO-spam injection" in build_prompts(
        mode="seo",
        language="en",
        context={"schema": "agentready.seo.v1"},
        skills=("seo-security-interpreter",),
    )[1]
    assert "возможное внедрение SEO-спама" in build_prompts(
        mode="seo",
        language="ru",
        context={"schema": "agentready.seo.v1"},
        skills=("seo-security-interpreter",),
    )[1]


def test_assistant_returns_typed_localized_response():
    report = seo_report()
    report["checks"][0]["evidence"] = [{
        "action": "inspect title",
        "url": "https://example.com",
        "metrics": {"page": "https://example.com", "length": 12},
    }]
    request = AssistantRequest(operation="recommend", mode="seo", language="ru", report=report)
    response = asyncio.run(AIAssistant(FakeProvider()).run(request, model="test-model"))
    assert response.language == "ru"
    assert response.model == "test-model"
    assert response.actions[0].priority == "high"
    assert response.disclaimer.startswith("Только")
    assert response.evidence[0].source_url == "https://example.com"
    assert response.evidence[0].metrics["length"] == 12


def test_ai_provider_profiles_persist_and_resolve_active_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save_ai_provider_config(
        {
            "id": "anthropic",
            "name": "Anthropic",
            "base_url": "https://api.anthropic.example/v1",
            "credential_id": "ai-anthropic-api-key",
        }
    )
    save_ai_provider_config(
        {
            "id": "openai",
            "name": "OpenAI-compatible",
            "base_url": "https://gateway.example/v1",
            "credential_id": "ai-openai-api-key",
        }
    )
    config, path = load_config()
    assert path and config["ai"]["active_provider"] == "openai"
    assert active_ai_provider(config["ai"])["base_url"] == "https://gateway.example/v1"
    assert {item["id"] for item in config["ai"]["providers"]} == {"openai", "anthropic"}
