"""Localized application-owned strings for the SEO/GEO AI assistant."""
from __future__ import annotations

from .i18n import normalize_language

_TEXT = {
    "en": {
        "disabled": "AI assistant is disabled in configuration.",
        "missing_credential": "AI provider credentials are not configured.",
        "invalid_request": "The AI assistant request is invalid.",
        "provider_error": "The AI provider request failed.",
        "schema_error": "The AI provider returned an invalid structured response.",
        "timeout": "The AI provider request timed out.",
        "cancelled": "The AI provider request was cancelled.",
        "busy": "The AI assistant is busy. Try again shortly.",
        "disclaimer": "AI-generated, evidence-grounded guidance only; it does not guarantee rankings or indexing and does not change the audited site.",
        "no_findings": "No supported optimization gaps were found in the supplied audit evidence.",
        "summary": "SEO/GEO optimization guidance based on the supplied deterministic audit evidence.",
        "default_action": "Optimization action",
    },
    "ru": {
        "disabled": "AI-помощник отключён в конфигурации.",
        "missing_credential": "Учётные данные провайдера AI не настроены.",
        "invalid_request": "Запрос к AI-помощнику некорректен.",
        "provider_error": "Запрос к провайдеру AI завершился ошибкой.",
        "schema_error": "Провайдер AI вернул некорректный структурированный ответ.",
        "timeout": "Истекло время ожидания ответа провайдера AI.",
        "cancelled": "Запрос к провайдеру AI отменён.",
        "busy": "AI-помощник занят. Повторите попытку позже.",
        "disclaimer": "Только сгенерированные AI рекомендации на основе проверяемых данных; они не гарантируют позиции или индексацию и не изменяют сайт.",
        "no_findings": "В переданных результатах аудита не найдено поддерживаемых недочётов оптимизации.",
        "summary": "Рекомендации по SEO/GEO на основе переданных детерминированных результатов аудита.",
        "default_action": "Действие по оптимизации",
    },
}


def ai_text(key: str, language: str = "en") -> str:
    """Return a localized assistant string, failing clearly for unknown keys."""
    lang = normalize_language(language)
    try:
        return _TEXT[lang][key]
    except KeyError as exc:
        raise KeyError(f"unknown AI localization key: {key}") from exc


def ai_catalog(language: str = "en") -> dict[str, str]:
    """Return a copy of one locale catalog for transport adapters."""
    return dict(_TEXT[normalize_language(language)])


def ai_catalog_keys() -> frozenset[str]:
    """Return the canonical catalog keys used by parity tests and adapters."""
    return frozenset(_TEXT["en"])
