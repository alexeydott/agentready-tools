from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Server dependencies missing. Install: pip install 'agentready-tools[server]'") from exc

from .i18n import category_name, check_hint, check_title, guidance, localized_report_dict, normalize_language
from .dashboard import render_dashboard
from .remediation import remediation_for
from .registry import CHECKS
from .report import render_html
from .scanner import scan
from .seo_report import render_seo_html
from .seo_checks import SEO_CHECKS_BY_ID, SEO_CHECK_METADATA
from .seo_crawler import CRAWL_CHECK_METADATA
from .seo_scanner import audit_seo
from .mobile_checks import MOBILE_CHECK_METADATA, MOBILE_STATIC_CHECKS_BY_ID
from .mobile_report import render_mobile_html
from .mobile_scanner import audit_mobile
from .target import TargetError
from .ai_prompts import ai_skill_catalog
from .compatibility import COMPATIBILITY
from .jobs_v2 import AuditJobManager
from .report_v2 import diff_reports, export_inventory, report_from_checks, report_from_dict
from .audit_service import AuditRequest, AuditService

logger = logging.getLogger(__name__)


def default_data_dir() -> Path:
    """Return the serve cache beside the running application."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / ".cache"
    return Path(__file__).resolve().parents[2] / ".cache"


_SERVER_DATA_DIR = default_data_dir()
_V2_JOBS = AuditJobManager(max_jobs=8)
_AUDIT_SERVICE = AuditService()


def configure_data_dir(path: str | Path | None = None) -> Path:
    """Configure and create the serve-owned directory for AI tool settings."""
    global _SERVER_DATA_DIR
    _SERVER_DATA_DIR = (Path(path).expanduser() if path is not None else default_data_dir()).resolve()
    _SERVER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Serve data directory ready: %s", _SERVER_DATA_DIR)
    return _SERVER_DATA_DIR


def _ai_tools_path() -> Path:
    _SERVER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _SERVER_DATA_DIR / "ai-tools.json"


def _load_ai_tools() -> dict:
    path = _ai_tools_path()
    if not path.is_file():
        return {"skills": ["seo-security-interpreter"], "mcp_tools": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unable to read AI tools settings path=%s error=%s", path, exc)
        return {"skills": ["seo-security-interpreter"], "mcp_tools": []}
    allowed_skills = {item["id"] for item in ai_skill_catalog("en")}
    return {
        "skills": [item for item in data.get("skills", []) if item in allowed_skills][:8],
        "mcp_tools": [item for item in data.get("mcp_tools", []) if item in {"agentready.seo_findings", "agentready.remediation_plan"}][:8],
    }


def _save_ai_tools(data: dict) -> dict:
    allowed_skills = {item["id"] for item in ai_skill_catalog("en")}
    payload = {
        "skills": [item for item in data.get("skills", []) if item in allowed_skills][:8],
        "mcp_tools": [item for item in data.get("mcp_tools", []) if item in {"agentready.seo_findings", "agentready.remediation_plan"}][:8],
    }
    _ai_tools_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("Saved AI tools settings path=%s skills=%d mcp_tools=%d", _ai_tools_path(), len(payload["skills"]), len(payload["mcp_tools"]))
    return payload


DEFAULT_PROMPTS = [
    {"id": "seo-indexability", "title": {"en": "SEO: why is the page not indexed?", "ru": "SEO: почему страница не индексируется?"}, "mode": "seo", "prompt": {"en": "Analyze the audit and explain why the page may not be indexed. Rank the causes by impact and give concrete checks and fixes.", "ru": "Проанализируй аудит и объясни, почему страница может не индексироваться. Ранжируй причины по влиянию и предложи конкретные проверки и исправления."}},
    {"id": "seo-images", "title": {"en": "SEO: image indexing problems", "ru": "SEO: проблемы индексации изображений"}, "mode": "seo", "prompt": {"en": "Analyze why images may not be indexed or found in search. Use the audit evidence and identify specific image, metadata, crawlability, URL, and performance issues to fix.", "ru": "Проанализируй, почему изображения могут не индексироваться или не находиться в поиске. Используй данные аудита и укажи проблемы изображений, метаданных, краулинга, URL и производительности."}},
    {"id": "seo-metadata", "title": {"en": "SEO: metadata and headings", "ru": "SEO: метаданные и заголовки"}, "mode": "seo", "prompt": {"en": "Review title, description, canonical, headings, and structured data. Return a prioritized implementation checklist with verification steps.", "ru": "Проверь title, description, canonical, заголовки и структурированные данные. Верни приоритетный список внедрения с шагами проверки."}},
    {"id": "geo-citations", "title": {"en": "GEO: citation readiness", "ru": "GEO: готовность к цитированию"}, "mode": "geo", "prompt": {"en": "Assess whether the site is easy for AI search systems to understand and cite. Explain evidence gaps and provide safe, verifiable improvements.", "ru": "Оцени, насколько сайт понятен и пригоден для цитирования AI-поиском. Объясни пробелы в доказательствах и предложи безопасные проверяемые улучшения."}},
    {"id": "geo-crawlers", "title": {"en": "GEO: AI crawler access", "ru": "GEO: доступ AI-краулеров"}, "mode": "geo", "prompt": {"en": "Analyze AI crawler discoverability and access controls. Separate robots policy, WAF/CDN, content availability, and protocol discovery concerns.", "ru": "Проанализируй обнаруживаемость и доступ AI-краулеров. Раздели вопросы robots-политики, WAF/CDN, доступности контента и обнаружения протоколов."}},
    {"id": "both-roadmap", "title": {"en": "SEO/GEO: prioritized roadmap", "ru": "SEO/GEO: приоритетная дорожная карта"}, "mode": "both", "prompt": {"en": "Create a practical SEO/GEO roadmap from the audit. Group work into quick wins, medium effort, and deeper technical changes, with check IDs and verification.", "ru": "Создай практическую дорожную карту SEO/GEO по аудиту. Раздели работы на быстрые улучшения, средние и глубокие технические изменения с ID проверок и верификацией."}},
    {"id": "seo-technical-crawl", "title": {"en": "SEO: technical crawl triage", "ru": "SEO: разбор технического краулинга"}, "mode": "seo", "prompt": {"en": "Use page-level crawl evidence to triage indexability, status codes, redirects, canonicals, robots rules, duplicate metadata, and orphan-page risks. Return confirmed URLs only.", "ru": "Используй постраничные данные краулинга для разбора индексируемости, кодов ответа, редиректов, canonical, robots, дубликатов метаданных и риска сиротских страниц. Возвращай только подтверждённые URL."}},
    {"id": "seo-images-pages", "title": {"en": "SEO: find pages with image issues", "ru": "SEO: найти страницы с проблемами изображений"}, "mode": "seo", "prompt": {"en": "Find every crawled page containing image SEO problems. List the confirmed page URL, image URL or selector when available, problem type, and a verification step. Never invent missing URLs.", "ru": "Найди каждую просканированную страницу с проблемами SEO изображений. Укажи подтверждённый URL страницы, URL или селектор изображения если доступен, тип проблемы и шаг проверки. Не придумывай отсутствующие URL."}},
    {"id": "seo-content-brief", "title": {"en": "SEO: evidence-based content brief", "ru": "SEO: контент-бриф на основе доказательств"}, "mode": "seo", "prompt": {"en": "Turn the audit evidence into a content brief: search intent, primary and secondary topics, title, headings, internal links, media requirements, and measurable acceptance criteria. Separate evidence from suggestions.", "ru": "Преобразуй данные аудита в контент-бриф: поисковый интент, основные и дополнительные темы, title, заголовки, внутренние ссылки, требования к медиа и измеримые критерии приёмки. Отделяй факты от предложений."}},
    {"id": "seo-structured-data", "title": {"en": "SEO: structured data implementation", "ru": "SEO: внедрение структурированных данных"}, "mode": "seo", "prompt": {"en": "Recommend only schema types supported by the observed page content. Provide a minimal JSON-LD plan, required properties, validation checks, and warnings against fabricated business facts.", "ru": "Рекомендуй только типы schema.org, соответствующие наблюдаемому содержимому страницы. Дай минимальный план JSON-LD, обязательные свойства, проверки и предупреждения против выдуманных фактов о бизнесе."}},
    {"id": "geo-citability", "title": {"en": "GEO: improve citability", "ru": "GEO: повысить цитируемость"}, "mode": "geo", "prompt": {"en": "Assess answer-engine citability from the evidence. Identify unclear claims, missing sources, weak entity context, and hard-to-quote passages, then propose verifiable page changes.", "ru": "Оцени цитируемость в answer engines по имеющимся данным. Найди неясные утверждения, отсутствующие источники, слабый контекст сущностей и неудобные для цитирования фрагменты, затем предложи проверяемые изменения."}},
    {"id": "geo-llms-discovery", "title": {"en": "GEO: AI discovery protocol checklist", "ru": "GEO: протоколы обнаружения AI"}, "mode": "geo", "prompt": {"en": "Create a protocol checklist for AI discovery covering robots directives, sitemap, llms.txt or equivalent machine-readable guidance, canonical URLs, stable content, and access failures. Mark each item confirmed, unknown, or failing.", "ru": "Создай чек-лист обнаружения AI: директивы robots, sitemap, llms.txt или аналогичные машиночитаемые инструкции, canonical, стабильность контента и ошибки доступа. Пометь каждый пункт как подтверждённый, неизвестный или проблемный."}},
    {"id": "both-prioritize-impact", "title": {"en": "SEO/GEO: impact and effort prioritization", "ru": "SEO/GEO: приоритизация по влиянию и усилиям"}, "mode": "both", "prompt": {"en": "Rank audit remediations by expected search or agent-readiness impact versus implementation effort. Cite check IDs and URLs, state assumptions, and define a measurable verification for each item.", "ru": "Ранжируй исправления аудита по ожидаемому влиянию на поиск или готовность для агентов и трудозатратам. Указывай ID проверок и URL, отмечай допущения и задавай измеримую проверку для каждого пункта."}},
]


def _prompts_path() -> Path:
    _SERVER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _SERVER_DATA_DIR / "prompts.json"


def _load_prompts() -> list[dict]:
    path = _prompts_path()
    if not path.is_file():
        path.write_text(json.dumps(DEFAULT_PROMPTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return list(DEFAULT_PROMPTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unable to read prompt library path=%s error=%s", path, exc)
        return list(DEFAULT_PROMPTS)
    defaults_by_id = {item["id"]: item for item in DEFAULT_PROMPTS}
    prompts = []
    for item in data:
        if not isinstance(item, dict) or not item.get("id") or not item.get("prompt"):
            continue
        if item["id"] in defaults_by_id:
            item = {**item, **defaults_by_id[item["id"]]}
        if isinstance(item["title"], str):
            item["title"] = {"en": item["title"], "ru": item["title"]}
        if isinstance(item["prompt"], str):
            item["prompt"] = {"en": item["prompt"], "ru": item["prompt"]}
        prompts.append(item)
    known_ids = {item["id"] for item in prompts}
    missing_defaults = [item for item in DEFAULT_PROMPTS if item["id"] not in known_ids]
    prompts.extend(missing_defaults)
    if missing_defaults:
        try:
            path.write_text(json.dumps(prompts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("Unable to update prompt library path=%s error=%s", path, exc)
    return prompts[:100]


def _localized_prompts(language: str) -> list[dict]:
    return [
        {
            "id": item["id"],
            "title": item["title"].get(language, item["title"].get("en", "")),
            "mode": item["mode"],
            "prompt": item["prompt"].get(language, item["prompt"].get("en", "")),
        }
        for item in _load_prompts()
    ]


def _save_prompt(prompt: dict) -> dict:
    prompts = [item for item in _load_prompts() if item.get("id") != prompt["id"]]
    prompts.append(prompt)
    _prompts_path().write_text(json.dumps(prompts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return prompt


def _chats_dir() -> Path:
    path = _SERVER_DATA_DIR / "chats"
    path.mkdir(parents=True, exist_ok=True)
    return path

app = FastAPI(
    title="AgentReady Tools API",
    version=COMPATIBILITY.release,
    description="Read-only AI-agent readiness website scanner. Private targets are blocked by default to reduce SSRF risk.",
)


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, language: Literal["en", "ru"] | None = None) -> HTMLResponse:
    """Serve the localized interactive control center for all read-only modes."""
    explicit_language = language is not None
    if explicit_language:
        lang = normalize_language(language)
    else:
        browser_language = request.headers.get("accept-language", "").split(",", 1)[0].split(";", 1)[0].strip()
        lang = "ru" if browser_language.lower().split("-", 1)[0] == "ru" else "en"
    logger.debug("Serving interactive dashboard: language=%s explicit=%s", lang, explicit_language)
    return HTMLResponse(render_dashboard(lang))


class ScanRequest(BaseModel):
    url: str
    preset: Literal["all", "content", "api", "ai-search"] = "all"
    language: Literal["en", "ru"] = "en"
    content_url: str | None = None
    commerce_url: str | None = None
    only: list[str] | None = None
    include: list[str] | None = None
    exclude: list[str] | None = None
    verify_skill_digests: bool = False
    timeout: float = Field(default=5.0, ge=1.0, le=30.0)
    workers: int = Field(default=8, ge=1, le=24)
    level_threshold: float = Field(default=0.8, gt=0.0, le=1.0)
    recommendation_limit: int = Field(default=10, ge=0, le=50)


class V2AuditRequest(BaseModel):
    url: str
    preset: Literal["all", "content", "api", "ai-search"] = "all"
    profile: Literal["quick", "standard", "deep", "custom"] = "standard"
    language: Literal["en", "ru"] = "en"
    timeout: float = Field(default=5.0, ge=1.0, le=30.0)
    max_pages: int = Field(default=25, ge=1, le=100)
    limits: dict[str, int | float] = Field(default_factory=dict)
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    render: bool = False
    provider: str | None = None
    rescan_of: str | None = None
    selected_urls: list[str] = Field(default_factory=list)


class SeoRequest(BaseModel):
    url: str
    language: Literal["en", "ru"] = "en"
    checks: list[str] | None = None
    timeout: float = Field(default=5.0, ge=1.0, le=30.0)
    recommendation_limit: int = Field(default=10, ge=0, le=50)
    crawl: bool = False
    max_pages: int = Field(default=25, ge=1, le=100)
    render: bool = False
    ga_property: str | None = None
    gsc_site: str | None = None


class MobileRequest(BaseModel):
    urls: list[str] = Field(min_length=1)
    language: Literal["en", "ru"] = "en"
    render: bool = False
    timeout: float = Field(default=5.0, ge=1.0, le=30.0)
    recommendation_limit: int = Field(default=10, ge=0, le=50)


class AIRequest(BaseModel):
    mode: Literal["seo", "geo", "both"] = "both"
    operation: Literal["recommend", "chat"] = "recommend"
    language: Literal["en", "ru"] = "en"
    target: str | None = None
    report: dict | None = None
    message: str | None = Field(default=None, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=12)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    skills: list[str] = Field(default_factory=list, max_length=8)
    mcp_tools: list[str] = Field(default_factory=list, max_length=8)
    attachments: list[dict[str, str]] = Field(default_factory=list, max_length=5)


class AICredentialRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=1000)


class AIProviderRequest(BaseModel):
    provider_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)
    active: bool = True
    enable_ai: bool | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200)
    chat_only: bool = False
    input_price_per_million: float = Field(default=0.0, ge=0)
    output_price_per_million: float = Field(default=0.0, ge=0)


class AIProviderSelectionRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=64)


class AIToolsRequest(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=8)
    mcp_tools: list[str] = Field(default_factory=list, max_length=8)


class AIPromptRequest(BaseModel):
    id: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    mode: Literal["seo", "geo", "both"] = "both"
    prompt: str = Field(min_length=1, max_length=4000)
    language: Literal["en", "ru"] = "en"


class AIChatSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    target: str | None = Field(default=None, max_length=500)
    language: Literal["en", "ru"] = "en"
    mode: Literal["seo", "geo", "both"] = "both"
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    messages: list[dict[str, str]] = Field(default_factory=list, max_length=100)
    usage: dict | None = None


def _require_loopback(http_request: Request) -> None:
    if http_request.client and http_request.client.host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="AI transport is loopback-only")


@app.get("/ai/status")
def ai_status_endpoint(http_request: Request) -> dict:
    """Return redacted AI enablement and credential status."""
    _require_loopback(http_request)
    from .ai_credentials import api_key_status
    from .config import active_ai_provider, ai_provider_profiles, load_config

    cfg, _ = load_config()
    ai_cfg = cfg["ai"]
    active = active_ai_provider(ai_cfg)
    return {
        "enabled": ai_cfg["enabled"],
        "transport_enabled": ai_cfg["transport_enabled"],
        "model": ai_cfg["model"],
        "active_provider": active["id"],
        "credential": api_key_status(active["credential_id"]),
        "providers": [
            {
                "id": provider["id"],
                "name": provider["name"],
                "base_url": provider["base_url"],
                "model": provider.get("model") or ai_cfg["model"],
                "chat_only": bool(provider.get("chat_only", False)),
                "input_price_per_million": float(provider.get("input_price_per_million") or 0.0),
                "output_price_per_million": float(provider.get("output_price_per_million") or 0.0),
                "credential": api_key_status(provider["credential_id"]),
            }
            for provider in ai_provider_profiles(ai_cfg)
        ],
        "language": ai_cfg["language"],
    }


@app.get("/ai/tools")
def ai_tools_get_endpoint(http_request: Request, language: Literal["en", "ru"] = "en") -> dict:
    """Return persisted AI selections and the localized built-in skill catalog."""
    _require_loopback(http_request)
    return {**_load_ai_tools(), "skills_catalog": ai_skill_catalog(language)}


@app.post("/ai/tools")
def ai_tools_save_endpoint(request: AIToolsRequest, http_request: Request) -> dict:
    """Persist dashboard skill and MCP selections in the serve data directory."""
    _require_loopback(http_request)
    return _save_ai_tools(request.model_dump())


@app.get("/ai/prompts")
def ai_prompts_get_endpoint(http_request: Request, language: Literal["en", "ru"] = "en") -> dict:
    _require_loopback(http_request)
    return {"prompts": _localized_prompts(language)}


@app.post("/ai/prompts")
def ai_prompts_save_endpoint(request: AIPromptRequest, http_request: Request) -> dict:
    _require_loopback(http_request)
    prompt_id = request.id or re.sub(r"[^a-z0-9]+", "-", request.title.lower()).strip("-")[:80] or "custom-prompt"
    localized = {"en": request.title, "ru": request.title}
    localized_prompt = {"en": request.prompt, "ru": request.prompt}
    return {"prompt": _save_prompt({"id": prompt_id, "title": localized, "mode": request.mode, "prompt": localized_prompt})}


@app.get("/ai/chats")
def ai_chats_get_endpoint(http_request: Request) -> dict:
    _require_loopback(http_request)
    rows = []
    for path in sorted(_chats_dir().glob("*.json"), reverse=True)[:100]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows.append({"file": path.name, "name": data.get("name", path.stem), "target": data.get("target"), "created_at": data.get("created_at")})
        except (OSError, json.JSONDecodeError):
            logger.warning("Ignoring invalid saved chat file path=%s", path)
    return {"chats": rows}


@app.get("/ai/chats/{filename}")
def ai_chat_get_endpoint(filename: str, http_request: Request) -> dict:
    _require_loopback(http_request)
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.endswith(".json"):
        raise HTTPException(status_code=400, detail="invalid chat filename")
    path = _chats_dir() / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="saved chat not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="saved chat is invalid") from exc


@app.post("/ai/chats")
def ai_chats_save_endpoint(request: AIChatSaveRequest, http_request: Request) -> dict:
    _require_loopback(http_request)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", request.name).strip("-").lower()[:60] or "chat"
    path = _chats_dir() / f"{stamp}-{slug}.json"
    payload = request.model_dump()
    payload["created_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("Saved AI chat path=%s messages=%d", path, len(request.messages))
    return {"file": path.name, "name": request.name}


@app.post("/ai/providers")
def ai_provider_save_endpoint(request: AIProviderRequest, http_request: Request) -> dict:
    """Save a provider profile and optionally its key in local configuration/vault."""
    _require_loopback(http_request)
    from .ai_credentials import store_api_key
    from .ai_provider import validate_base_url
    from .config import AI_PROVIDER_ID, ai_provider_profiles, load_config, save_ai_enablement, save_ai_provider_config

    provider_id = request.provider_id or re.sub(r"[^A-Za-z0-9._-]+", "-", request.name.strip().lower()).strip("-")[:64]
    if not provider_id or not AI_PROVIDER_ID.fullmatch(provider_id):
        raise HTTPException(status_code=400, detail="provider_id must contain only letters, numbers, dot, underscore, or hyphen")
    cfg, config_path = load_config()
    ai_cfg = cfg["ai"]
    try:
        base_url = validate_base_url(request.base_url, allow_loopback_http=ai_cfg["allow_loopback_http"])
        existing = next((item for item in ai_provider_profiles(ai_cfg) if item["id"] == provider_id), None)
        credential_id = existing["credential_id"] if existing else f"ai-{provider_id}-api-key"
        provider = {
            "id": provider_id,
            "name": request.name.strip(),
            "base_url": base_url,
            "credential_id": credential_id,
            "model": request.model or (existing or {}).get("model") or ai_cfg["model"],
            "chat_only": request.chat_only,
            "input_price_per_million": request.input_price_per_million,
            "output_price_per_million": request.output_price_per_million,
        }
        save_ai_provider_config(provider, active=request.active, config_path=config_path)
        if request.api_key is not None:
            store_api_key(request.api_key, credential_id)
        if request.enable_ai is not None:
            save_ai_enablement(request.enable_ai, config_path=config_path)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail="Unable to save AI provider") from exc
    logger.info("Saved AI provider through loopback serve endpoint id=%s active=%s", provider_id, request.active)
    return {"ok": True, "provider_id": provider_id, "active": request.active}


@app.post("/ai/providers/active")
def ai_provider_activate_endpoint(request: AIProviderSelectionRequest, http_request: Request) -> dict:
    """Select an existing provider profile for CLI, serve, and MCP."""
    _require_loopback(http_request)
    from .config import ai_provider_profiles, load_config, save_ai_provider_profiles

    cfg, config_path = load_config()
    provider = next((item for item in ai_provider_profiles(cfg["ai"]) if item["id"] == request.provider_id), None)
    if provider is None:
        raise HTTPException(status_code=404, detail="AI provider not found")
    try:
        save_ai_provider_profiles([*ai_provider_profiles(cfg["ai"])], active_provider=request.provider_id, config_path=config_path)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail="Unable to activate AI provider") from exc
    logger.info("Activated AI provider through loopback serve endpoint id=%s", request.provider_id)
    return {"ok": True, "active_provider": request.provider_id}


@app.get("/ai/providers/{provider_id}/models")
def ai_provider_models_endpoint(provider_id: str, http_request: Request) -> dict:
    """Load the provider model catalog for the local dashboard picker."""
    _require_loopback(http_request)
    import asyncio
    from .ai_provider import AIProviderError, OpenAICompatibleProvider
    from .config import ai_provider_profiles, load_config

    cfg, _ = load_config()
    ai_cfg = cfg["ai"]
    provider = next((item for item in ai_provider_profiles(ai_cfg) if item["id"] == provider_id), None)
    if provider is None:
        raise HTTPException(status_code=404, detail="AI provider not found")
    try:
        models = asyncio.run(OpenAICompatibleProvider(
            base_url=provider["base_url"],
            credential_id=provider["credential_id"],
            timeout=ai_cfg["timeout"],
            max_retries=ai_cfg["max_retries"],
            allow_loopback_http=ai_cfg["allow_loopback_http"],
        ).list_models())
        logger.info("Served AI model catalog provider_id=%s count=%d", provider_id, len(models))
        return {
            "provider_id": provider_id,
            "selected_model": provider.get("model") or ai_cfg["model"],
            "models": [model.to_dict() for model in models],
        }
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail={"code": exc.code, "message": str(exc)}) from exc


@app.delete("/ai/providers/{provider_id}")
def ai_provider_delete_endpoint(provider_id: str, http_request: Request) -> dict:
    """Remove a provider profile and its OS-vault key."""
    _require_loopback(http_request)
    from .ai_credentials import clear_api_key
    from .config import ai_provider_profiles, load_config, save_ai_provider_config

    cfg, config_path = load_config()
    providers = ai_provider_profiles(cfg["ai"])
    provider = next((item for item in providers if item["id"] == provider_id), None)
    if provider is None:
        raise HTTPException(status_code=404, detail="AI provider not found")
    if len(providers) == 1:
        raise HTTPException(status_code=400, detail="At least one AI provider must remain")
    remaining = [item for item in providers if item["id"] != provider_id]
    try:
        clear_api_key(provider["credential_id"])
        save_ai_provider_profiles(remaining, active_provider=remaining[0]["id"], config_path=config_path)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail="Unable to remove AI provider") from exc
    logger.info("Removed AI provider through loopback serve endpoint id=%s", provider_id)
    return {"ok": True, "active_provider": remaining[0]["id"]}


@app.post("/ai/credentials")
def ai_credentials_set_endpoint(request: AICredentialRequest, http_request: Request) -> dict:
    """Store the configured AI provider key in the local OS credential vault."""
    _require_loopback(http_request)
    from .ai_credentials import store_api_key
    from .config import active_ai_provider, load_config

    cfg, _ = load_config()
    try:
        store_api_key(request.api_key, active_ai_provider(cfg["ai"])["credential_id"])
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail="Unable to store AI credential") from exc
    logger.info("Stored AI credential through loopback serve endpoint")
    return {"ok": True, "credential": {"configured": True, "source": "keyring", "credential_id": active_ai_provider(cfg["ai"])["credential_id"]}}


@app.delete("/ai/credentials")
def ai_credentials_clear_endpoint(http_request: Request) -> dict:
    """Remove the configured AI provider key from the local OS credential vault."""
    _require_loopback(http_request)
    from .ai_credentials import clear_api_key
    from .config import active_ai_provider, load_config

    cfg, _ = load_config()
    try:
        removed = clear_api_key(active_ai_provider(cfg["ai"])["credential_id"])
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail="Unable to clear AI credential") from exc
    logger.info("Cleared AI credential through loopback serve endpoint removed=%s", removed)
    return {"ok": True, "removed": removed}


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/checks")
def checks_endpoint(language: Literal["en", "ru"] = "en") -> list[dict[str, object]]:
    """List the checks available to every Agent Readiness scan preset."""
    lang = normalize_language(language)
    logger.debug("Serving localized check catalog: language=%s count=%d", lang, len(CHECKS))
    return [
        {
            "id": spec.id,
            "title": check_title(spec.id, spec.title, lang),
            "category": category_name(spec.category, lang),
            "description": guidance(
                spec.id,
                remediation_for(spec, "https://example.com").summary,
                lang,
            ),
            "hint": check_hint(spec.id, spec.title, spec.category, lang),
            "scored": spec.scored,
            "presets": sorted(spec.presets),
            "experimental": spec.experimental,
            "supplemental": spec.supplemental,
            "geo_scored": spec.geo_scored,
            "effort": spec.effort,
            "references": list(spec.references),
            "language": lang,
        }
        for spec in CHECKS
    ]


@app.get("/seo/checks")
def seo_checks_endpoint(language: Literal["en", "ru"] = "en") -> list[dict[str, str]]:
    """List localized SEO checks available to the independent SEO profile."""
    lang = normalize_language(language)
    logger.debug("Serving localized SEO hint catalog: language=%s count=%d", lang, len(SEO_CHECK_METADATA) + len(CRAWL_CHECK_METADATA))
    return [
        {
            "id": item["id"],
            "title": item["title"][lang],
            "category": item["category"][lang],
            "description": item["description"][lang],
            "hint": item["description"][lang],
            "language": lang,
        }
        for item in (*SEO_CHECK_METADATA, *CRAWL_CHECK_METADATA)
    ]


def _run_scan(request: ScanRequest):
    return scan(
        request.url,
        preset=request.preset,
        only=request.only,
        include=request.include,
        exclude=request.exclude,
        content_url=request.content_url,
        commerce_url=request.commerce_url,
        verify_skill_digests=request.verify_skill_digests,
        timeout=request.timeout,
        allow_private=False,
        workers=request.workers,
        level_threshold=request.level_threshold,
        recommendation_limit=request.recommendation_limit,
        language=request.language,
    )


@app.post("/scan")
def scan_endpoint(request: ScanRequest) -> dict:
    """Run a scan and return localized JSON. Stable IDs/status values remain language-neutral."""
    try:
        report = _run_scan(request)
        return localized_report_dict(report, request.language)
    except (TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run_v2_scan(request: V2AuditRequest, *, parent_run_id: str | None = None) -> dict:
    fields_set = getattr(request, "model_fields_set", None)
    if fields_set is None:
        fields_set = getattr(request, "__fields_set__", set())
    max_pages = request.max_pages
    if "max_pages" not in fields_set and "max_pages" in request.limits:
        max_pages = int(request.limits["max_pages"])
    if not 1 <= max_pages <= 100:
        raise ValueError("max_pages must be between 1 and 100")
    result = _AUDIT_SERVICE.run(
        AuditRequest(
            target=request.url,
            preset=request.preset,
            profile=request.profile,
            max_pages=max_pages,
            timeout=request.timeout,
            limits=request.limits,
            include=tuple(request.include),
            exclude=tuple(request.exclude),
            render=request.render,
            provider=request.provider,
            language=request.language,
            parent_run_id=parent_run_id if parent_run_id is not None else request.rescan_of,
            selected_urls=tuple(request.selected_urls),
        )
    )
    return result.to_dict()


@app.post("/v2/audit")
def audit_v2_endpoint(request: V2AuditRequest) -> dict:
    """Run the additive canonical v2 report without changing the v1 endpoint."""
    try:
        return _run_v2_scan(request)
    except (TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/rescan")
def audit_v2_rescan_endpoint(request: V2AuditRequest) -> dict:
    """Run a new child audit linked to the requested parent run."""
    try:
        return _run_v2_scan(request, parent_run_id=request.rescan_of)
    except (TargetError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/jobs")
def audit_v2_job_endpoint(request: V2AuditRequest) -> dict:
    try:
        job_id = _V2_JOBS.submit(lambda: _run_v2_scan(request))
    except (RuntimeError, TargetError, ValueError) as exc:
        raise HTTPException(status_code=429 if isinstance(exc, RuntimeError) else 400, detail=str(exc)) from exc
    return {"job_id": job_id, "status": "running"}


@app.get("/v2/jobs/{job_id}")
def audit_v2_job_status_endpoint(job_id: str) -> dict:
    try:
        return _V2_JOBS.get(job_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc


@app.post("/v2/jobs/{job_id}/cancel")
def audit_v2_job_cancel_endpoint(job_id: str) -> dict:
    try:
        snapshot = _V2_JOBS.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    if snapshot.status.value in {"completed", "failed", "cancelled"}:
        return snapshot.to_dict()
    _V2_JOBS.cancel(job_id)
    return _V2_JOBS.get(job_id).to_dict()


@app.post("/v2/diff")
def audit_v2_diff_endpoint(payload: dict) -> dict:
    try:
        request = V2AuditRequest.model_validate(payload["request"])
        current = _run_v2_scan(request)
        return diff_reports(report_from_dict(current), payload["baseline"]).to_dict()
    except (KeyError, TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/export")
def audit_v2_export_endpoint(payload: dict) -> dict:
    format_name = payload.get("format", "jsonl")
    try:
        return {"format": format_name, "content": export_inventory(payload.get("items", []), format=format_name)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/scan/dashboard", response_class=HTMLResponse)
def scan_dashboard(request: ScanRequest) -> HTMLResponse:
    """Run a scan and return the self-contained bilingual HTML dashboard."""
    try:
        report = _run_scan(request)
        html = render_html(report, request.language)
        v2 = report_from_checks(request.url, report.checks).to_dict()
        embedded = json.dumps(v2, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
        return HTMLResponse(f'{html}\n<script id="agentready-v2-report" type="application/json">{embedded}</script>')
    except (TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/mobile/checks")
def mobile_checks_endpoint(language: Literal["en", "ru"] = "en") -> list[dict[str, str]]:
    """List localized mobile-friendliness checks."""
    lang = normalize_language(language)
    logger.debug("Serving localized mobile check catalog: language=%s count=%d", lang, len(MOBILE_CHECK_METADATA))
    return [
        {
            "id": item["id"],
            "title": item["title"][lang],
            "category": item["category"][lang],
            "description": item["description"][lang],
            "hint": item["description"][lang],
            "language": lang,
        }
        for item in MOBILE_CHECK_METADATA
    ]


def _run_mobile(request: MobileRequest):
    return audit_mobile(
        request.urls,
        render=request.render,
        timeout=request.timeout,
        allow_private=False,
        recommendation_limit=request.recommendation_limit,
        language=request.language,
    )


@app.post("/mobile/audit")
def mobile_audit_endpoint(request: MobileRequest) -> dict:
    """Run a mobile-friendliness audit for one or more public pages."""
    try:
        return _run_mobile(request).to_dict()
    except (TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/mobile/audit/dashboard", response_class=HTMLResponse)
def mobile_audit_dashboard(request: MobileRequest) -> HTMLResponse:
    """Return the mobile-friendliness audit as a self-contained HTML report."""
    try:
        report = _run_mobile(request)
        return HTMLResponse(render_mobile_html(report, request.language))
    except (TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _build_agentready_mcp_context(report: object | None, tools: list[str], language: str) -> dict | None:
    if report is None or not tools:
        return None
    from .agentfindings import build_findings, build_remediation_plan

    context: dict = {}
    if "agentready.seo_findings" in tools:
        context["tool"] = "agentready.seo_findings"
        context["result"] = build_findings(report, language)
    if "agentready.remediation_plan" in tools:
        context["remediation_plan"] = build_remediation_plan(report, language)
    return context or None


def _ai_assistant(request: AIRequest):
    import asyncio
    from dataclasses import replace
    from .ai_assistant import AIAssistant
    from .ai_models import AssistantRequest, AssistantUsage, ConversationMessage
    from .ai_provider import AIProviderError, OpenAICompatibleProvider
    from .config import load_config
    from .report_v2 import report_from_checks
    from .scanner import scan

    cfg, _ = load_config()
    ai_cfg = cfg["ai"]
    if not ai_cfg["enabled"] or not ai_cfg["transport_enabled"]:
        raise HTTPException(status_code=404, detail="AI assistant transport is disabled")
    if request.report is None:
        if not request.target:
            raise HTTPException(status_code=400, detail="target or report is required")
        legacy_report = scan(request.target, allow_private=False, language=request.language)
        report_object = report_from_checks(request.target, legacy_report.checks)
        report = report_object.to_dict()
    else:
        report_object = None
        report = request.report
    try:
        history = tuple(ConversationMessage(item["role"], item["content"]) for item in request.history)
        saved_tools = _load_ai_tools()
        selected_skills = request.skills or saved_tools["skills"] or ["seo-security-interpreter"]
        selected_mcp_tools = request.mcp_tools or saved_tools["mcp_tools"]
        assistant_request = AssistantRequest(
            operation=request.operation,
            mode=request.mode,
            language=request.language,
            target=request.target,
            report=report,
            message=request.message,
            history=history,
            skills=tuple(item[:500] for item in selected_skills),
            mcp_tools=tuple(item for item in selected_mcp_tools if item in {"agentready.seo_findings", "agentready.remediation_plan"}),
            attachments=tuple(
                {
                    "name": item.get("name", "attachment")[:200],
                    "type": item.get("type", "application/octet-stream")[:120],
                    "content": item.get("content", "")[:16000],
                }
                for item in request.attachments
                if isinstance(item.get("content"), str)
            ),
            mcp_context=_build_agentready_mcp_context(
                report_object,
                selected_mcp_tools,
                request.language,
            ),
        )
        from .config import active_ai_provider
        selected_provider = active_ai_provider(ai_cfg)
        provider = OpenAICompatibleProvider(
            base_url=selected_provider["base_url"],
            credential_id=selected_provider["credential_id"],
            timeout=ai_cfg["timeout"],
            max_retries=ai_cfg["max_retries"],
            allow_loopback_http=ai_cfg["allow_loopback_http"],
        )
        result = asyncio.run(AIAssistant(
            provider,
            context_limit=ai_cfg["context_limit"],
            history_limit=ai_cfg["history_limit"],
            message_limit=ai_cfg["message_limit"],
            output_limit=ai_cfg["output_limit"],
            max_concurrent=ai_cfg["max_concurrent"],
        ).run(assistant_request, model=request.model or selected_provider.get("model") or ai_cfg["model"]))
        if result.usage:
            configured_input_price = selected_provider.get("input_price_per_million")
            configured_output_price = selected_provider.get("output_price_per_million")
            input_price = float(configured_input_price) if configured_input_price is not None and float(configured_input_price) > 0 else None
            output_price = float(configured_output_price) if configured_output_price is not None and float(configured_output_price) > 0 else None
            prompt_tokens = result.usage.prompt_tokens or 0
            completion_tokens = result.usage.completion_tokens or 0
            input_cost = prompt_tokens * input_price / 1_000_000 if input_price is not None else None
            output_cost = completion_tokens * output_price / 1_000_000 if output_price is not None else None
            result.usage = replace(
                result.usage,
                input_price_per_million=input_price,
                output_price_per_million=output_price,
                input_cost=input_cost,
                output_cost=output_cost,
                total_cost=input_cost + output_cost if input_cost is not None and output_cost is not None else None,
            )
        return result.to_dict()
    except HTTPException:
        raise
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail={"code": exc.code, "message": str(exc)}) from exc


@app.post("/ai/recommend")
def ai_recommend_endpoint(request: AIRequest, http_request: Request) -> dict:
    """Run an explicitly enabled, loopback-only AI recommendation request."""
    if http_request.client and http_request.client.host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="AI transport is loopback-only")
    request.operation = "recommend"
    return _ai_assistant(request)


@app.post("/ai/chat")
def ai_chat_endpoint(request: AIRequest, http_request: Request) -> dict:
    """Run an explicitly enabled, loopback-only stateless AI chat turn."""
    if http_request.client and http_request.client.host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="AI transport is loopback-only")
    request.operation = "chat"
    if not request.message:
        raise HTTPException(status_code=400, detail="message is required")
    return _ai_assistant(request)


def _run_seo(request: SeoRequest):
    from .seo_crawler import CRAWL_CHECKS_BY_ID

    checks = None
    crawl_ids: list[str] = []
    if request.checks is not None:
        page_ids: list[str] = []
        unknown: list[str] = []
        for check_id in request.checks:
            if check_id in SEO_CHECKS_BY_ID:
                page_ids.append(check_id)
            elif check_id in CRAWL_CHECKS_BY_ID:
                crawl_ids.append(check_id)
            else:
                unknown.append(check_id)
        if unknown:
            raise ValueError(f"Unknown SEO check(s): {', '.join(unknown)}")
        checks = [SEO_CHECKS_BY_ID[check_id] for check_id in page_ids]
        logger.debug("SEO request split: page_checks=%d crawl_checks=%d", len(page_ids), len(crawl_ids))
    return audit_seo(
        request.url,
        checks=checks,
        timeout=request.timeout,
        allow_private=False,
        recommendation_limit=request.recommendation_limit,
        language=request.language,
        crawl=request.crawl or bool(crawl_ids),
        max_pages=request.max_pages,
        render=request.render,
        crawl_checks=[CRAWL_CHECKS_BY_ID[check_id] for check_id in crawl_ids] if crawl_ids else None,
        ga_property=request.ga_property,
        gsc_site=request.gsc_site,
    )


@app.post("/seo/audit")
def seo_audit_endpoint(request: SeoRequest) -> dict:
    """Run the independent SEO audit against one public page and discovery resources."""
    try:
        return _run_seo(request).to_dict()
    except (TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/seo/audit/dashboard", response_class=HTMLResponse)
def seo_audit_dashboard(request: SeoRequest) -> HTMLResponse:
    """Return the independent SEO audit as a self-contained HTML report."""
    try:
        report = _run_seo(request)
        return HTMLResponse(render_seo_html(report, request.language))
    except (TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
