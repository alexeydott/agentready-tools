"""Injectable asynchronous OpenAI-compatible provider boundary."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

from .ai_credentials import load_api_key

logger = logging.getLogger(__name__)


class AIProviderError(RuntimeError):
    """Base class for provider failures."""

    def __init__(self, message: str, *, code: str = "provider_error", retryable: bool = False, request_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.request_id = request_id


class AIProviderConfigurationError(AIProviderError):
    pass


class AISchemaError(AIProviderError):
    pass


class AIProvider(Protocol):
    async def complete(self, *, system: str, user: str, model: str, language: str) -> ProviderResult:
        ...


@dataclass(slots=True, frozen=True)
class ProviderResult:
    data: dict[str, Any]
    request_id: str | None = None
    usage: dict[str, int] | None = None


@dataclass(slots=True, frozen=True)
class ProviderModel:
    id: str
    capabilities: tuple[str, ...]
    owned_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "capabilities": list(self.capabilities), "owned_by": self.owned_by}


def model_capabilities(model_id: str, metadata: Any = None) -> tuple[str, ...]:
    """Classify common provider model families for the local model picker."""
    text = model_id.lower()
    if isinstance(metadata, dict):
        raw = metadata.get("capabilities")
        if isinstance(raw, dict):
            explicit = tuple(key for key, value in raw.items() if value is True and isinstance(key, str))
            if explicit:
                return tuple(dict.fromkeys(explicit))
        if isinstance(raw, (list, tuple, set)):
            explicit = tuple(value for value in raw if isinstance(value, str) and value)
            if explicit:
                return tuple(dict.fromkeys(explicit))
    capabilities: list[str] = []
    if any(token in text for token in ("embed", "bge-", "e5-", "gte-")):
        capabilities.append("embedding")
    if any(token in text for token in ("rerank", "reranker", "cross-encoder")):
        capabilities.append("rerank")
    if any(token in text for token in ("moderation", "safety")):
        capabilities.append("moderation")
    if any(token in text for token in ("whisper", "transcri", "tts", "audio", "speech")):
        capabilities.append("audio")
    if not capabilities and any(token in text for token in (
        "chat", "gpt", "claude", "llama", "qwen", "mistral", "mixtral", "deepseek", "gemini", "command", "gemma", "kimi",
    )):
        capabilities.append("chat")
    return tuple(dict.fromkeys(capabilities or ["other"]))


def validate_base_url(base_url: str, *, allow_loopback_http: bool = False) -> str:
    """Validate a trusted-local provider URL before passing it to the SDK."""
    if not isinstance(base_url, str) or not base_url.strip():
        raise AIProviderConfigurationError("AI base_url must be a non-empty URL", code="invalid_base_url")
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise AIProviderConfigurationError("AI base_url must use HTTPS", code="invalid_base_url")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AIProviderConfigurationError("AI base_url cannot contain userinfo, query, or fragment", code="invalid_base_url")
    if parsed.scheme == "http" and not (allow_loopback_http and parsed.hostname in {"127.0.0.1", "::1", "localhost"}):
        raise AIProviderConfigurationError("HTTP is allowed only for explicitly enabled loopback providers", code="insecure_base_url")
    return base_url.rstrip("/")


class OpenAICompatibleProvider:
    """Thin adapter around the optional official ``openai`` async client."""

    def __init__(
        self,
        *,
        base_url: str,
        credential_id: str,
        timeout: float = 30.0,
        max_retries: int = 2,
        allow_loopback_http: bool = False,
    ) -> None:
        self.base_url = validate_base_url(base_url, allow_loopback_http=allow_loopback_http)
        self.credential_id = credential_id
        self.timeout = timeout
        self.max_retries = max_retries

    async def complete(self, *, system: str, user: str, model: str, language: str) -> ProviderResult:
        api_key, source = load_api_key(self.credential_id)
        if not api_key:
            raise AIProviderConfigurationError("AI provider credentials are not configured", code="missing_credential")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise AIProviderConfigurationError(
                "Install AI extras: pip install 'agentready-tools[ai]'", code="missing_dependency"
            ) from exc
        logger.info("Starting AI provider request model=%s source=%s", model, source)
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=0,
        )
        started = time.monotonic()
        fallback_attempted = False
        attempt = 0
        while attempt <= self.max_retries:
            try:
                result = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                )
                content = result.choices[0].message.content if result.choices else None
                if not content:
                    raise AISchemaError("AI provider returned empty content", code="schema_error")
                try:
                    data = json.loads(content)
                except json.JSONDecodeError as exc:
                    raise AISchemaError("AI provider returned invalid JSON", code="schema_error") from exc
                if not isinstance(data, dict):
                    raise AISchemaError("AI provider returned a non-object JSON value", code="schema_error")
                usage = None
                if result.usage:
                    usage = {
                        key: value for key, value in {
                            "prompt_tokens": result.usage.prompt_tokens,
                            "completion_tokens": result.usage.completion_tokens,
                            "total_tokens": result.usage.total_tokens,
                        }.items() if value is not None
                    }
                request_id = getattr(result, "_request_id", None)
                logger.debug("AI provider request completed elapsed_ms=%d request_id=%s", int((time.monotonic() - started) * 1000), request_id)
                await client.close()
                return ProviderResult(data=data, request_id=request_id, usage=usage)
            except asyncio.CancelledError:
                logger.info("AI provider request cancelled")
                await client.close()
                raise
            except AISchemaError:
                await client.close()
                raise
            except Exception as exc:
                if getattr(exc, "status_code", None) == 404 and not fallback_attempted:
                    fallback_attempted = True
                    try:
                        catalog = await self.list_models()
                    except asyncio.CancelledError:
                        await client.close()
                        raise
                    except AIProviderError:
                        catalog = []
                    fallback = next(
                        (item.id for item in catalog if "chat" in item.capabilities and item.id != model),
                        None,
                    )
                    if fallback:
                        logger.warning(
                            "Requested AI model was not found; retrying with catalog chat model=%s",
                            fallback,
                        )
                        model = fallback
                        continue
                retryable = attempt < self.max_retries and _is_retryable(exc)
                logger.warning("AI provider request failed attempt=%d retryable=%s type=%s", attempt + 1, retryable, type(exc).__name__)
                if not retryable:
                    await client.close()
                    raise AIProviderError(str(exc), code=_error_code(exc), retryable=False) from exc
                try:
                    await asyncio.sleep(min(2**attempt, 4))
                except asyncio.CancelledError:
                    await client.close()
                    raise
                attempt += 1
        await client.close()
        raise AIProviderError("AI provider request failed", code="provider_error")

    async def list_models(self) -> list[ProviderModel]:
        """Load the provider's available models without exposing the API key."""
        api_key, source = load_api_key(self.credential_id)
        if not api_key:
            raise AIProviderConfigurationError("AI provider credentials are not configured", code="missing_credential")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise AIProviderConfigurationError(
                "Install AI extras: pip install 'agentready-tools[ai]'", code="missing_dependency"
            ) from exc
        client = AsyncOpenAI(api_key=api_key, base_url=self.base_url, timeout=self.timeout, max_retries=0)
        try:
            result = await client.models.list()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("AI model catalog request failed type=%s", type(exc).__name__)
            raise AIProviderError(str(exc), code=_error_code(exc), retryable=False) from exc
        finally:
            await client.close()
        models: list[ProviderModel] = []
        for item in getattr(result, "data", []) or []:
            model_id = getattr(item, "id", None)
            if not isinstance(model_id, str) and isinstance(item, dict):
                model_id = item.get("id")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            owned_by = getattr(item, "owned_by", None)
            if owned_by is None and isinstance(item, dict):
                owned_by = item.get("owned_by")
            metadata = item if isinstance(item, dict) else getattr(item, "model_dump", dict)()
            models.append(ProviderModel(model_id, model_capabilities(model_id, metadata), owned_by))
        models.sort(key=lambda item: item.id.lower())
        logger.info("Loaded AI model catalog count=%d source=%s", len(models), source)
        return models


def _is_retryable(error: Exception) -> bool:
    status = getattr(error, "status_code", None)
    return status == 429 or status is None or status >= 500


def _error_code(error: Exception) -> str:
    status = getattr(error, "status_code", None)
    if status == 404:
        return "model_not_found"
    if status == 401 or status == 403:
        return "provider_auth"
    if status == 429:
        return "rate_limited"
    if status and status >= 500:
        return "provider_unavailable"
    return "provider_error"
