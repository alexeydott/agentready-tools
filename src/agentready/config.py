from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILENAMES = (".agentready.yml", ".agentready.yaml")
AI_PROVIDER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "preset": "all",
    "checks": {"include": [], "exclude": []},
    "network": {"timeout": 5.0, "workers": 8, "verify_tls": True, "block_private": False},
    "content": {"content_url": None, "commerce_url": None, "verify_skill_digests": False},
    "gates": {"min_score": None, "fail_on_checks": False},
    "scoring": {"level_threshold": 0.8},
    "recommendations": {"max_items": 10},
    "report": {"language": "en"},
    "seo": {
        "timeout": 5.0,
        "verify_tls": True,
        "block_private": False,
        "recommendation_limit": 10,
        "language": "en",
    },
    "ai": {
        "enabled": False,
        "transport_enabled": False,
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "credential_id": "openai-api-key",
        "active_provider": "openai",
        "providers": [
            {
                "id": "openai",
                "name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "credential_id": "openai-api-key",
            }
        ],
        "api_mode": "chat_completions",
        "response_mode": "structured",
        "timeout": 30.0,
        "max_retries": 2,
        "context_limit": 12000,
        "history_limit": 12,
        "message_limit": 4000,
        "output_limit": 4000,
        "max_concurrent": 2,
        "language": "en",
        "allow_loopback_http": False,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in base.items():
        if isinstance(value, dict):
            out[key] = dict(value)
        elif isinstance(value, list):
            out[key] = list(value)
        else:
            out[key] = value
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def find_config(start: str | Path = ".") -> Path | None:
    root = Path(start).resolve()
    if root.is_file():
        root = root.parent
    for directory in (root, *root.parents):
        for name in CONFIG_FILENAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def load_config(path: str | Path | None = None, *, search: bool = True) -> tuple[dict[str, Any], str | None]:
    selected: Path | None
    if path:
        selected = Path(path).expanduser().resolve()
        if not selected.is_file():
            raise ValueError(f"config file not found: {selected}")
    else:
        selected = find_config() if search else None
    if selected is None:
        return _deep_merge(DEFAULT_CONFIG, {}), None
    try:
        raw = yaml.safe_load(selected.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML in {selected}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TypeError(f"config root must be a mapping: {selected}")
    cfg = _deep_merge(DEFAULT_CONFIG, raw)
    raw_ai = raw.get("ai") if isinstance(raw.get("ai"), dict) else {}
    if "providers" not in raw_ai and ("base_url" in raw_ai or "credential_id" in raw_ai):
        cfg["ai"]["providers"] = [{
            "id": "openai",
            "name": "OpenAI",
            "base_url": str(raw_ai.get("base_url") or DEFAULT_CONFIG["ai"]["base_url"]),
            "credential_id": str(raw_ai.get("credential_id") or DEFAULT_CONFIG["ai"]["credential_id"]),
            "model": str(raw_ai.get("model") or DEFAULT_CONFIG["ai"]["model"]),
        }]
        cfg["ai"]["active_provider"] = "openai"
    validate_config(cfg)
    return cfg, str(selected)


def validate_config(cfg: dict[str, Any]) -> None:
    if cfg.get("preset") not in {"all", "content", "api", "ai-search"}:
        raise ValueError("config preset must be all, content, api, or ai-search")
    checks = cfg.get("checks") or {}
    for key in ("include", "exclude"):
        if not isinstance(checks.get(key, []), list) or not all(isinstance(x, str) for x in checks.get(key, [])):
            raise ValueError(f"checks.{key} must be a list of check IDs")
    gates = cfg.get("gates") or {}
    min_score = gates.get("min_score")
    if min_score is not None and not (0 <= int(min_score) <= 100):
        raise ValueError("gates.min_score must be between 0 and 100")
    language = str((cfg.get("report") or {}).get("language", "en")).lower()
    if language not in {"en", "ru"}:
        raise ValueError("report.language must be en or ru")
    threshold = float((cfg.get("scoring") or {}).get("level_threshold", 0.8))
    if not 0 < threshold <= 1:
        raise ValueError("scoring.level_threshold must be in (0, 1]")
    seo = cfg.get("seo") or {}
    seo_timeout = float(seo.get("timeout", 5.0))
    if not 1 <= seo_timeout <= 30:
        raise ValueError("seo.timeout must be between 1 and 30")
    seo_limit = int(seo.get("recommendation_limit", 10))
    if not 0 <= seo_limit <= 50:
        raise ValueError("seo.recommendation_limit must be between 0 and 50")
    if str(seo.get("language", "en")).lower() not in {"en", "ru"}:
        raise ValueError("seo.language must be en or ru")
    _validate_ai_config(cfg.get("ai") or {})


def _validate_ai_config(ai: dict[str, Any]) -> None:
    if not isinstance(ai, dict):
        raise TypeError("ai must be a mapping")
    for key in ("enabled", "transport_enabled", "allow_loopback_http"):
        if not isinstance(ai.get(key, False), bool):
            raise TypeError(f"ai.{key} must be a boolean")
    for key in ("model", "credential_id", "api_mode", "response_mode", "language"):
        if not isinstance(ai.get(key), str) or not ai.get(key):
            raise TypeError(f"ai.{key} must be a non-empty string")
    if str(ai.get("language", "en")).lower() not in {"en", "ru"}:
        raise ValueError("ai.language must be en or ru")
    if ai.get("api_mode") not in {"chat_completions"}:
        raise ValueError("ai.api_mode must be chat_completions")
    if ai.get("response_mode") not in {"structured", "json"}:
        raise ValueError("ai.response_mode must be structured or json")
    base_url = ai.get("base_url")
    if base_url is not None and not isinstance(base_url, str):
        raise ValueError("ai.base_url must be a URL string or null")
    providers = ai.get("providers")
    if providers is not None:
        if not isinstance(providers, list) or not providers:
            raise ValueError("ai.providers must be a non-empty list")
        provider_ids: set[str] = set()
        for provider in providers:
            if not isinstance(provider, dict):
                raise TypeError("ai.providers entries must be mappings")
            provider_id = provider.get("id")
            if not isinstance(provider_id, str) or not AI_PROVIDER_ID.fullmatch(provider_id):
                raise ValueError("ai.providers.id must contain only letters, numbers, dot, underscore, or hyphen")
            if provider_id in provider_ids:
                raise ValueError("ai.providers.id values must be unique")
            provider_ids.add(provider_id)
            if not isinstance(provider.get("name"), str) or not provider["name"].strip():
                raise ValueError("ai.providers.name must be a non-empty string")
            if not isinstance(provider.get("base_url"), str) or not provider["base_url"].strip():
                raise ValueError("ai.providers.base_url must be a non-empty URL string")
            if not isinstance(provider.get("credential_id"), str) or not provider["credential_id"].strip():
                raise ValueError("ai.providers.credential_id must be a non-empty string")
            if "model" in provider and (not isinstance(provider["model"], str) or not provider["model"].strip()):
                raise ValueError("ai.providers.model must be a non-empty string")
            for price_key in ("input_price_per_million", "output_price_per_million"):
                if price_key in provider:
                    try:
                        price = float(provider[price_key])
                    except (TypeError, ValueError) as exc:
                        raise ValueError(f"ai.providers.{price_key} must be a non-negative number") from exc
                    if price < 0:
                        raise ValueError(f"ai.providers.{price_key} must be a non-negative number")
        active_provider = ai.get("active_provider")
        if active_provider is not None and active_provider not in provider_ids:
            raise ValueError("ai.active_provider must reference an ai.providers.id")
    timeout = float(ai.get("timeout", 30.0))
    if not 1 <= timeout <= 120:
        raise ValueError("ai.timeout must be between 1 and 120")
    retries = int(ai.get("max_retries", 2))
    if not 0 <= retries <= 5:
        raise ValueError("ai.max_retries must be between 0 and 5")
    for key, low, high in (
        ("context_limit", 1000, 50000),
        ("history_limit", 0, 50),
        ("message_limit", 100, 20000),
        ("output_limit", 100, 20000),
    ):
        value = int(ai.get(key, DEFAULT_CONFIG["ai"][key]))
        if not low <= value <= high:
            raise ValueError(f"ai.{key} must be between {low} and {high}")
    concurrency = int(ai.get("max_concurrent", 2))
    if not 1 <= concurrency <= 8:
        raise ValueError("ai.max_concurrent must be between 1 and 8")


def default_config_yaml() -> str:
    return """# AgentReady Tools configuration
# CLI flags override values from this file.

preset: all

checks:
  # Supplemental checks are opt-in so the core score remains comparable.
  # Useful supplemental options:
  # Cloudflare-docs-inspired: [llms-txt, markdown-index-fallback, markdown-efficiency]
  # GEO/AI-search profile is easier to enable with: preset: ai-search
  include: []
  exclude: []

network:
  timeout: 5.0
  workers: 8
  verify_tls: true
  block_private: false

content:
  # content_url: https://docs.example.com/guide/
  # commerce_url: https://api.example.com/paid-resource
  verify_skill_digests: false

gates:
  # min_score: 80
  fail_on_checks: false

scoring:
  level_threshold: 0.8

recommendations:
  max_items: 10

report:
  # Language used for console, JSON, Markdown and initial dashboard view.
  # The HTML dashboard also contains an interactive English/Russian switcher.
  language: en

ai:
  # AI is opt-in. Keep API keys out of this file.
  enabled: false
  # HTTP/MCP assistant transports remain disabled unless explicitly enabled.
  transport_enabled: false
  model: gpt-4o-mini
  base_url: https://api.openai.com/v1
  credential_id: openai-api-key
  model: gpt-4o-mini
  active_provider: openai
  providers:
    - id: openai
      name: OpenAI
      base_url: https://api.openai.com/v1
      credential_id: openai-api-key
  api_mode: chat_completions
  response_mode: structured
  timeout: 30.0
  max_retries: 2
  context_limit: 12000
  history_limit: 12
  message_limit: 4000
  output_limit: 4000
  max_concurrent: 2
  language: en
  # Only enable for a deliberately configured local provider.
  allow_loopback_http: false
"""


def ai_provider_profiles(ai: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized provider profiles, including single-provider config."""
    providers = ai.get("providers")
    if isinstance(providers, list) and providers:
        return [dict(provider) for provider in providers if isinstance(provider, dict)]
    return [{
        "id": "openai",
        "name": "OpenAI",
        "base_url": str(ai.get("base_url") or DEFAULT_CONFIG["ai"]["base_url"]),
        "credential_id": str(ai.get("credential_id") or DEFAULT_CONFIG["ai"]["credential_id"]),
        "model": str(ai.get("model") or DEFAULT_CONFIG["ai"]["model"]),
        "input_price_per_million": 0.0,
        "output_price_per_million": 0.0,
    }]


def active_ai_provider(ai: dict[str, Any]) -> dict[str, Any]:
    """Resolve the configured active provider for every transport surface."""
    providers = ai_provider_profiles(ai)
    active_id = ai.get("active_provider")
    if isinstance(active_id, str):
        for provider in providers:
            if provider.get("id") == active_id:
                return provider
    return providers[0]


def save_ai_provider_config(
    provider: dict[str, Any],
    *,
    active: bool = True,
    config_path: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Persist a provider profile in the discovered AgentReady YAML config."""
    selected = Path(config_path).expanduser().resolve() if config_path else find_config()
    if selected is None:
        selected = Path(".agentready.yml").resolve()
    raw: dict[str, Any] = {}
    if selected.is_file():
        loaded = yaml.safe_load(selected.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"config root must be a mapping: {selected}")
        raw = loaded
    cfg = _deep_merge(DEFAULT_CONFIG, raw)
    raw_ai = raw.get("ai") if isinstance(raw.get("ai"), dict) else {}
    if "providers" not in raw_ai and ("base_url" in raw_ai or "credential_id" in raw_ai):
        providers = [{
            "id": "openai",
            "name": "OpenAI",
            "base_url": str(raw_ai.get("base_url") or DEFAULT_CONFIG["ai"]["base_url"]),
            "credential_id": str(raw_ai.get("credential_id") or DEFAULT_CONFIG["ai"]["credential_id"]),
            "model": str(raw_ai.get("model") or DEFAULT_CONFIG["ai"]["model"]),
        }]
    else:
        providers = ai_provider_profiles(cfg["ai"])
    existing = next((item for item in providers if item["id"] == provider["id"]), None)
    if existing:
        existing.update(provider)
    else:
        providers.append(dict(provider))
    ai_raw = raw.setdefault("ai", {})
    if not isinstance(ai_raw, dict):
        raise TypeError("ai must be a mapping")
    ai_raw["providers"] = providers
    if active:
        ai_raw["active_provider"] = provider["id"]
        ai_raw["base_url"] = provider["base_url"]
        ai_raw["credential_id"] = provider["credential_id"]
    merged = _deep_merge(DEFAULT_CONFIG, raw)
    validate_config(merged)
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    logger.info("Saved AI provider profile id=%s active=%s path=%s", provider["id"], active, selected)
    return merged, str(selected)


def save_ai_provider_profiles(
    providers: list[dict[str, Any]],
    *,
    active_provider: str,
    config_path: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Replace provider profiles while preserving the rest of the YAML config."""
    if not providers or not any(item.get("id") == active_provider for item in providers):
        raise ValueError("active_provider must reference one of the provider profiles")
    selected = Path(config_path).expanduser().resolve() if config_path else find_config()
    if selected is None:
        selected = Path(".agentready.yml").resolve()
    raw: dict[str, Any] = {}
    if selected.is_file():
        loaded = yaml.safe_load(selected.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise TypeError(f"config root must be a mapping: {selected}")
        raw = loaded
    ai_raw = raw.setdefault("ai", {})
    if not isinstance(ai_raw, dict):
        raise TypeError("ai must be a mapping")
    selected_provider = next(item for item in providers if item["id"] == active_provider)
    ai_raw["providers"] = [dict(item) for item in providers]
    ai_raw["active_provider"] = active_provider
    ai_raw["base_url"] = selected_provider["base_url"]
    ai_raw["credential_id"] = selected_provider["credential_id"]
    merged = _deep_merge(DEFAULT_CONFIG, raw)
    validate_config(merged)
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    logger.info("Saved AI provider profiles count=%d active=%s path=%s", len(providers), active_provider, selected)
    return merged, str(selected)


def save_ai_enablement(
    enabled: bool,
    *,
    transport_enabled: bool | None = None,
    config_path: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    """Persist the explicit AI enablement state used by CLI, serve, and MCP."""
    selected = Path(config_path).expanduser().resolve() if config_path else find_config()
    if selected is None:
        selected = Path(".agentready.yml").resolve()
    raw: dict[str, Any] = {}
    if selected.is_file():
        loaded = yaml.safe_load(selected.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"config root must be a mapping: {selected}")
        raw = loaded
    ai_raw = raw.setdefault("ai", {})
    if not isinstance(ai_raw, dict):
        raise TypeError("ai must be a mapping")
    ai_raw["enabled"] = bool(enabled)
    ai_raw["transport_enabled"] = bool(enabled if transport_enabled is None else transport_enabled)
    merged = _deep_merge(DEFAULT_CONFIG, raw)
    validate_config(merged)
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    logger.info(
        "Saved AI enablement enabled=%s transport_enabled=%s path=%s",
        ai_raw["enabled"],
        ai_raw["transport_enabled"],
        selected,
    )
    return merged, str(selected)
