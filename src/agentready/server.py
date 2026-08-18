from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import sys
import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

try:
    from fastapi import FastAPI, HTTPException, Query, Request
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Server dependencies missing. Install: pip install 'agentready-tools[server]'") from exc

from .ai_prompts import ai_skill_catalog
from .audit_core.store import MemorySiteStore, ProjectRecord, RunUrlState, SQLiteSiteStore
from .audit_service import AuditRequest, AuditService
from .compatibility import COMPATIBILITY
from .custom_rules import apply_rules, compile_rules, validate_rules
from .crawl_profiles import HARD_CAPS
from .dashboard import render_dashboard
from .duplicates import DuplicateAnalysis, analyze_signatures, signature
from .exports import export_query
from .i18n import (
    category_name,
    check_hint,
    check_title,
    crawl_classification_label,
    guidance,
    normalize_language,
)
from .jobs_v2 import AuditJobManager
from .link_graph import LinkGraphProjection, project_link_graph
from .metrics import (
    ExternalMetric,
    ProviderConfig,
    ProviderStatus,
    ga4_adapter,
    gsc_adapter,
    pagespeed_adapter,
    url_inspection_adapter,
)
from .mobile_checks import MOBILE_CHECK_METADATA
from .mobile_report import render_mobile_html
from .mobile_scanner import audit_mobile
from .query_service import (
    FindingQuery,
    LinkQuery,
    MetricQuery,
    PageQuery,
    QueryPage,
    QueryService,
    RedirectQuery,
    ResourceQuery,
    RunUrlQuery,
)
from .projects import ProjectService, project_run_to_dict, project_to_dict
from .registry import CHECKS
from .remediation import remediation_for
from .report_storage import save_report
from .report_v2 import diff_reports, export_inventory, report_from_dict, semantic_diff
from .robots import RobotsInterpretation, RobotsSimulationService, parse_robots
from .saved_views import SavedView, SavedViewRegistry
from .sitemap_reconciliation import build_reconciliation_report
from .seo_checks import SEO_CHECK_METADATA, SEO_CHECKS_BY_ID
from .seo_crawler import CRAWL_CHECK_METADATA
from .seo_report import render_seo_html
from .seo_scanner import audit_seo
from .target import TargetError
from .workflows import InventoryRequest

logger = logging.getLogger(__name__)


def default_data_dir() -> Path:
    """Return the serve cache beside the running application."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / ".cache"
    return Path(__file__).resolve().parents[2] / ".cache"


_SERVER_DATA_DIR = default_data_dir()
_V2_JOBS = AuditJobManager(max_jobs=8)
_AUDIT_SERVICE = AuditService()


class _V2RunRegistry:
    """Bounded in-process access to completed v2 audit stores.

    Bounded by both the number of retained runs and the total number of retained
    inventory records, so a small number of deep runs cannot pin unbounded memory.
    """

    def __init__(self, *, max_runs: int = 32, max_records: int = 250_000) -> None:
        self._max_runs = max_runs
        self._max_records = max_records
        self._runs: OrderedDict[str, MemorySiteStore] = OrderedDict()
        self._sizes: dict[str, int] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _record_count(run_id: str, store: MemorySiteStore) -> int:
        return sum(
            sum(1 for _ in iterator(run_id))
            for iterator in (
                store.iter_pages,
                store.iter_run_urls,
                store.iter_link_occurrences,
                store.iter_resource_occurrences,
                store.iter_metrics,
                store.iter_redirects,
                store.iter_findings,
            )
        )

    def _evict_oldest(self, reason: str) -> None:
        run_id, evicted = self._runs.popitem(last=False)
        self._sizes.pop(run_id, None)
        evicted.close()
        logger.info("v2 run inventory evicted run_id=%s reason=%s", run_id, reason)

    def put(self, run_id: str, store: MemorySiteStore) -> None:
        with self._lock:
            self._runs.pop(run_id, None)
            self._sizes.pop(run_id, None)
            self._runs[run_id] = store
            self._sizes[run_id] = self._record_count(run_id, store)
            while len(self._runs) > self._max_runs:
                self._evict_oldest("max-runs")
            while len(self._runs) > 1 and sum(self._sizes.values()) > self._max_records:
                self._evict_oldest("max-records")
            logger.debug(
                "v2 run inventory stored run_id=%s runs=%d records=%d",
                run_id,
                len(self._runs),
                sum(self._sizes.values()),
            )

    def get(self, run_id: str) -> MemorySiteStore:
        with self._lock:
            store = self._runs.get(run_id)
            if store is None:
                if os.environ.get("AGENTREADY_SERVE_SQLITE") == "1":
                    durable = _serve_sqlite_store()
                    if durable is not None:
                        logger.info("[FIX:serve-recovery] rehydrated durable run store run_id=%s", run_id)
                        self._runs[run_id] = durable  # type: ignore[assignment]
                        self._sizes[run_id] = 0
                        store = durable
                if store is None:
                    raise KeyError(run_id)
            self._runs.move_to_end(run_id)
            return store


_V2_RUNS = _V2RunRegistry()
_V2_SAVED_VIEWS = SavedViewRegistry()
_V2_GRAPH_CACHE: OrderedDict[tuple[str, str], LinkGraphProjection] = OrderedDict()
_V2_DUPLICATE_CACHE: OrderedDict[tuple[str, int], DuplicateAnalysis] = OrderedDict()
_V2_PROJECT_STORE: MemorySiteStore | SQLiteSiteStore | None = None


def _serve_sqlite_store() -> SQLiteSiteStore | None:
    """Open the optional durable serve store when explicitly enabled."""
    if os.environ.get("AGENTREADY_SERVE_SQLITE") != "1":
        return None
    path = _SERVER_DATA_DIR / "audit.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("[FIX:serve-recovery] durable SQLite serve history path=%s", path)
    return SQLiteSiteStore(path)


def _project_store() -> MemorySiteStore | SQLiteSiteStore:
    global _V2_PROJECT_STORE
    if _V2_PROJECT_STORE is None:
        _V2_PROJECT_STORE = _serve_sqlite_store() or MemorySiteStore()
    return _V2_PROJECT_STORE


def _link_graph_projection(run_id: str, origin: str | None = None) -> LinkGraphProjection:
    store = _V2_RUNS.get(run_id)
    pages = tuple(store.iter_pages(run_id))
    resolved_origin = origin or (urlsplit(pages[0].url_key).scheme + "://" + urlsplit(pages[0].url_key).netloc if pages else "")
    if not resolved_origin:
        raise ValueError("origin is required when run has no pages")
    key = (run_id, resolved_origin)
    cached = _V2_GRAPH_CACHE.get(key)
    if cached is not None:
        _V2_GRAPH_CACHE.move_to_end(key)
        return cached
    projection = project_link_graph(
        tuple(store.iter_link_occurrences(run_id)),
        run_id=run_id,
        origin=resolved_origin,
        known_pages=tuple(page.url_key for page in pages),
        page_depths={page.url_key: page.depth for page in pages},
        redirect_sources=tuple(item.from_url for item in store.iter_redirects(run_id)),
    )
    _V2_GRAPH_CACHE[key] = projection
    while len(_V2_GRAPH_CACHE) > 32:
        _V2_GRAPH_CACHE.popitem(last=False)
    return projection


def _duplicate_analysis(run_id: str, threshold: int = 3) -> DuplicateAnalysis:
    key = (run_id, threshold)
    cached = _V2_DUPLICATE_CACHE.get(key)
    if cached is not None:
        _V2_DUPLICATE_CACHE.move_to_end(key)
        return cached
    store = _V2_RUNS.get(run_id)
    signatures = tuple(
        signature(page.url_key, page.content or page.content_hash or "")
        for page in store.iter_pages(run_id)
        if page.content or page.content_hash
    )
    analysis = analyze_signatures(signatures, max_hamming_distance=threshold)
    _V2_DUPLICATE_CACHE[key] = analysis
    while len(_V2_DUPLICATE_CACHE) > 32:
        _V2_DUPLICATE_CACHE.popitem(last=False)
    return analysis


def _saved_views_path() -> Path:
    _SERVER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _SERVER_DATA_DIR / "saved-views.jsonl"


def _persist_saved_views() -> None:
    path = _saved_views_path()
    path.write_text("\n".join(_V2_SAVED_VIEWS.snapshot()) + ("\n" if _V2_SAVED_VIEWS.list() else ""), encoding="utf-8")


def _restore_saved_views() -> None:
    path = _saved_views_path()
    if not path.is_file():
        return
    records = tuple(line for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    try:
        restored = _V2_SAVED_VIEWS.restore(records)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.error("[FIX:serve-recovery] saved-view restore failed path=%s error=%s", path, exc)
        return
    logger.info("[FIX:serve-recovery] saved views restored count=%d", restored)


def _run_provider_enrichment(run_id: str, request: ProviderEnrichmentRequest) -> dict:
    """Persist bounded, explicitly supplied provider observations.

    Public API/MCP calls never receive credentials and never contact a provider
    implicitly.  A caller may replay a redacted cached fixture; otherwise the
    typed result is ``not_requested`` and the core audit score is untouched.
    """
    try:
        store = _V2_RUNS.get(run_id)
    except KeyError as exc:
        raise ValueError("run not found") from exc
    service = QueryService(store)
    urls = list(dict.fromkeys(request.sample_urls))[:100]
    if not urls:
        page = service.run_urls(RunUrlQuery(run_id, limit=100))
        urls = [item.url_key for item in page.items]
    metrics = tuple(
        ExternalMetric(
            request.provider,
            item.name,
            item.value,
            item.unit,
            item.source,
            item.version,
            item.observed_at,
        )
        for item in request.cached_metrics
        if item.url_key is None or item.url_key in urls
    )
    if not metrics:
        result = {
            "provider": request.provider,
            "status": ProviderStatus.NOT_REQUESTED.value,
            "detail": "no cached observations supplied; credentials remain in the local OS vault",
            "from_cache": False,
            "sample_count": len(urls),
            "metrics": [],
        }
    else:
        adapter = {
            "pagespeed": pagespeed_adapter,
            "ga4": ga4_adapter,
            "gsc": gsc_adapter,
            "url-inspection": url_inspection_adapter,
        }[request.provider](ProviderConfig())

        async def cached_operation(_: str | None) -> tuple[ExternalMetric, ...]:
            return metrics

        result = adapter.run(cached_operation, cached=metrics).to_dict()
        result["sample_count"] = len(urls)
        for item in request.cached_metrics:
            if item.url_key is None:
                targets = urls[:1] or [None]
            else:
                targets = [item.url_key]
            metric = ExternalMetric(
                request.provider,
                item.name,
                item.value,
                item.unit,
                item.source,
                item.version,
                item.observed_at,
            )
            for url_key in targets:
                store.put_metric(metric.to_record(run_id, url_key=url_key))
        store.put_evidence(run_id, f"provider:{request.provider}:summary", result)
    logger.info(
        "provider enrichment complete run_id=%s provider=%s status=%s samples=%d metrics=%d",
        run_id,
        request.provider,
        result["status"],
        len(urls),
        len(result.get("metrics", [])),
    )
    return result


def configure_data_dir(path: str | Path | None = None) -> Path:
    """Configure and create the serve-owned directory for AI tool settings."""
    global _SERVER_DATA_DIR
    _SERVER_DATA_DIR = (Path(path).expanduser() if path is not None else default_data_dir()).resolve()
    _SERVER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    _restore_saved_views()
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


@app.get("/v2/capabilities")
def v2_capabilities() -> dict:
    """Discover canonical v2 product-workflow capabilities and version."""
    return _AUDIT_SERVICE.workflow_capabilities()


class V2AuditRequest(BaseModel):
    url: str
    preset: Literal["all", "content", "api", "ai-search"] = "all"
    profile: Literal["quick", "standard", "deep", "custom"] = "standard"
    language: Literal["en", "ru"] = "en"
    timeout: float = Field(default=5.0, ge=1.0, le=30.0)
    max_pages: int = Field(default=25, ge=0, le=25_000)
    limits: dict[str, int | float] = Field(default_factory=dict)
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    render: bool = False
    provider: str | None = None
    rescan_of: str | None = None
    selected_urls: list[str] = Field(default_factory=list)
    selected_finding_ids: list[str] = Field(default_factory=list)
    selection_hash: str | None = Field(default=None, min_length=8, max_length=128)
    confirm: bool = False
    discovery_kind: Literal["single", "list", "sitemap", "robots-sitemap", "crawl"] = "single"
    discovery_urls: list[str] = Field(default_factory=list)
    discovery_sitemap_xml: str | None = None
    discovery_sitemap_urls: list[str] = Field(default_factory=list)
    discovery_limit: int = Field(default=1000, ge=1, le=100_000)


class ProjectCreateRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=2048)
    default_profile: Literal["quick", "standard", "deep", "custom"] = "standard"
    default_ruleset: str | None = Field(default=None, max_length=2048)
    retention_policy: str = Field(default="metadata-only", max_length=64)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    default_profile: Literal["quick", "standard", "deep", "custom"] | None = None
    default_ruleset: str | None = Field(default=None, max_length=2048)
    retention_policy: str | None = Field(default=None, max_length=64)


class ProjectRunRequest(BaseModel):
    profile: Literal["quick", "standard", "deep", "custom"] | None = None
    preset: Literal["all", "content", "api", "ai-search"] = "all"
    language: Literal["en", "ru"] = "en"
    max_pages: int = Field(default=25, ge=0, le=25_000)
    parent_run_id: str | None = Field(default=None, max_length=128)
    trigger: str = Field(default="manual", max_length=40)
    baseline_run_id: str | None = Field(default=None, max_length=128)


class RobotsSimulationRequest(BaseModel):
    live_robots: str = Field(default="", max_length=500 * 1024)
    proposed_robots: str = Field(min_length=1, max_length=500 * 1024)
    user_agents: list[str] = Field(default_factory=lambda: ["*"] , min_length=1, max_length=8)
    observed_search_pages: list[str] = Field(default_factory=list, max_length=1000)
    interpretation: Literal["rfc9309", "google"] = "rfc9309"
    origin: str | None = Field(default=None, max_length=2048)


class SitemapReconciliationRequest(BaseModel):
    """Caller-supplied bounded sitemap documents; no network fetch is performed."""

    documents: list[str] = Field(min_length=1, max_length=32)
    origin: str = Field(min_length=1, max_length=2048)
    category: str = "sitemap_only"
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=100, ge=1, le=1000)
    format: Literal["json", "csv"] = "json"
    sitemap_id: str | None = Field(default=None, max_length=80)


class CustomRulesRequest(BaseModel):
    rules: str | dict = Field(min_length=1)
    url: str = Field(default="", max_length=2048)
    text: str = Field(default="", max_length=1_000_000)
    headers: dict[str, str] = Field(default_factory=dict, max_length=100)
    structured_data: list[dict] = Field(default_factory=list, max_length=100)
    links: list[str] = Field(default_factory=list, max_length=1000)
    resources: list[str] = Field(default_factory=list, max_length=1000)
    css_matches: list[str] = Field(default_factory=list, max_length=1000)
    run_id: str | None = Field(default=None, max_length=128)
    url_key: str | None = Field(default=None, max_length=2048)


class SeoRequest(BaseModel):
    url: str
    profile: Literal["quick", "standard", "deep", "custom"] = "standard"
    language: Literal["en", "ru"] = "en"
    checks: list[str] | None = None
    timeout: float = Field(default=5.0, ge=1.0, le=30.0)
    recommendation_limit: int = Field(default=10, ge=0, le=50)
    limits: dict[str, int | float] = Field(default_factory=dict)
    crawl: bool = False
    max_pages: int = Field(default=25, ge=0, le=25_000)
    render: bool = False
    ga_property: str | None = None
    gsc_site: str | None = None


class MobileRequest(BaseModel):
    urls: list[str] = Field(min_length=1)
    language: Literal["en", "ru"] = "en"
    render: bool = False
    timeout: float = Field(default=5.0, ge=1.0, le=30.0)
    recommendation_limit: int = Field(default=10, ge=0, le=50)


class ProviderMetricInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    value: int | float | str | None = None
    unit: str | None = Field(default=None, max_length=32)
    source: str = Field(default="cached-fixture", min_length=1, max_length=120)
    version: str = Field(default="unknown", min_length=1, max_length=80)
    observed_at: str = Field(min_length=1, max_length=80)
    url_key: str | None = Field(default=None, max_length=2048)


class ProviderEnrichmentRequest(BaseModel):
    provider: Literal["pagespeed", "ga4", "gsc", "url-inspection"]
    sample_urls: list[str] = Field(default_factory=list, max_length=100)
    cached_metrics: list[ProviderMetricInput] = Field(default_factory=list, max_length=500)


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
    existing = next((item for item in _load_prompts() if item.get("id") == prompt_id), None)
    localized = dict(existing.get("title", {}) if existing else {})
    localized_prompt = dict(existing.get("prompt", {}) if existing else {})
    localized[request.language] = request.title
    localized_prompt[request.language] = request.prompt
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
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", request.name).strip("-").lower()[:60] or "chat"
    path = _chats_dir() / f"{stamp}-{slug}.json"
    payload = request.model_dump()
    payload["created_at"] = datetime.now(UTC).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("Saved AI chat path=%s messages=%d", path, len(request.messages))
    return {"file": path.name, "name": request.name}


@app.post("/ai/providers")
def ai_provider_save_endpoint(request: AIProviderRequest, http_request: Request) -> dict:
    """Save a provider profile and optionally its key in local configuration/vault."""
    _require_loopback(http_request)
    from .ai_credentials import store_api_key
    from .ai_provider import validate_base_url
    from .config import (
        AI_PROVIDER_ID,
        ai_provider_profiles,
        load_config,
        save_ai_enablement,
        save_ai_provider_config,
    )

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
    from .config import ai_provider_profiles, load_config, save_ai_provider_profiles

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


def _run_v2_scan(request: V2AuditRequest, *, parent_run_id: str | None = None, progress_callback=None) -> dict:
    fields_set = getattr(request, "model_fields_set", None)
    if fields_set is None:
        fields_set = getattr(request, "__fields_set__", set())
    max_pages = request.max_pages
    if "max_pages" not in fields_set and "max_pages" in request.limits:
        max_pages = int(request.limits["max_pages"])
    if not 0 <= max_pages <= HARD_CAPS.max_pages:
        raise ValueError(f"max_pages must be between 0 and {HARD_CAPS.max_pages}")
    if max_pages == 0:
        max_pages = HARD_CAPS.max_pages
    effective_parent = parent_run_id if parent_run_id is not None else request.rescan_of
    selected_urls, selection_hash, selection_meta = _resolve_rescan_selection(request, effective_parent)
    store = _serve_sqlite_store() or MemorySiteStore()
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
            parent_run_id=effective_parent,
            selected_urls=tuple(selected_urls),
            discovery_kind=request.discovery_kind,
            discovery_urls=tuple(request.discovery_urls),
            discovery_sitemap_xml=request.discovery_sitemap_xml,
            discovery_sitemap_urls=tuple(request.discovery_sitemap_urls),
            discovery_limit=request.discovery_limit,
            store=store,
            progress_callback=progress_callback,
        )
    )
    run = getattr(result, "run", None)
    run_id = getattr(getattr(run, "context", None), "run_id", None)
    if run_id is not None:
        report = getattr(result, "report", None)
        for finding in getattr(report, "findings", ()):
            store.put_finding(run_id, finding.id, finding.to_dict())
        coverage = getattr(report, "coverage", None)
        if coverage is not None:
            store.put_coverage(run_id, coverage.to_dict())
        _V2_RUNS.put(run_id, store)
    payload = result.to_dict()
    if effective_parent is not None:
        payload["rescan"] = {"parent_run_id": effective_parent, "selection_hash": selection_hash, "selected_count": len(selected_urls), "selected_urls": list(selected_urls), "selected_finding_ids": list(selection_meta), "remediation": _rescan_remediation(effective_parent, selection_meta)}
    return payload


def _rescan_remediation(parent_run_id: str, finding_ids: tuple[str, ...]) -> list[dict[str, object]]:
    if not finding_ids:
        return []
    try:
        records = {item.finding_id: item.payload for item in _V2_RUNS.get(parent_run_id).iter_findings(parent_run_id)}
    except KeyError:
        return []
    return [{"finding_id": finding_id, "evidence": list(records[finding_id].get("evidence", ())), "agent_prompt": f"Fix finding {finding_id} using only the supplied evidence."} for finding_id in finding_ids if finding_id in records]


def _resolve_rescan_selection(request: V2AuditRequest, parent_run_id: str | None) -> tuple[list[str], str | None, tuple[str, ...]]:
    """Resolve and authenticate a bounded child-run selection against its parent."""
    finding_ids = tuple(sorted(set(item.strip() for item in request.selected_finding_ids if item.strip())))
    explicit_urls = tuple(dict.fromkeys(item.strip() for item in request.selected_urls if item.strip()))
    if not finding_ids and not explicit_urls:
        return [], None, ()
    if parent_run_id is None:
        if finding_ids:
            raise ValueError("selected finding rescan requires parent run")
        return list(explicit_urls), None, ()
    if not request.confirm:
        raise ValueError("selected rescan requires explicit confirmation")
    try:
        parent_store = _V2_RUNS.get(parent_run_id)
    except KeyError as exc:
        raise ValueError("parent run not found") from exc
    known_urls = {item.url_key for item in parent_store.iter_run_urls(parent_run_id)} | {item.url_key for item in parent_store.iter_pages(parent_run_id)}
    urls = set(explicit_urls)
    if any(url not in known_urls for url in urls):
        raise ValueError("selected URL is stale or not part of the parent run")
    if finding_ids:
        records = {item.finding_id: item.payload for item in parent_store.iter_findings(parent_run_id)}
        missing = sorted(set(finding_ids) - set(records))
        if missing:
            raise ValueError("selected finding is stale or not part of the parent run")
        for finding_id in finding_ids:
            payload = records[finding_id]
            for key in ("affected_urls", "urls"):
                values = payload.get(key, ()) if isinstance(payload, Mapping) else ()
                urls.update(item for item in values if isinstance(item, str) and item in known_urls)
            for evidence in payload.get("evidence", ()) if isinstance(payload, Mapping) else ():
                if isinstance(evidence, Mapping) and isinstance(evidence.get("url"), str) and evidence["url"] in known_urls:
                    urls.add(evidence["url"])
    ordered_urls = sorted(urls)
    if not ordered_urls:
        raise ValueError("selected findings have no affected URLs in the parent run")
    digest = hashlib.sha256(json.dumps({"parent_run_id": parent_run_id, "finding_ids": finding_ids, "urls": ordered_urls}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if request.selection_hash is not None and request.selection_hash != digest:
        raise ValueError("selection is stale; selection hash does not match parent evidence")
    logger.info("rescan selection parent_run_id=%s selection_hash=%s finding_count=%d url_count=%d", parent_run_id, digest[:16], len(finding_ids), len(ordered_urls))
    return ordered_urls, digest, finding_ids


def _render_v2_dashboard(payload: dict) -> str:
    """Render a bounded HTML projection of the canonical v2 report."""
    language = normalize_language(payload.get("request", {}).get("language", "en"))
    labels = {
        "en": {"title": "AgentReady v2 audit", "target": "Target", "coverage": "Coverage", "fetched": "fetched", "finding": "Finding", "status": "Status", "summary": "Summary"},
        "ru": {"title": "Аудит AgentReady v2", "target": "Проверяемый адрес", "coverage": "Покрытие", "fetched": "загружено", "finding": "Проверка", "status": "Статус", "summary": "Описание"},
    }[language]
    status_labels = {
        "pass": "пройдено" if language == "ru" else "pass",
        "fail": "ошибка" if language == "ru" else "fail",
        "warn": "предупреждение" if language == "ru" else "warning",
        "error": "ошибка" if language == "ru" else "error",
        "skip": "не применимо" if language == "ru" else "not applicable",
    }
    findings = payload.get("findings", [])
    coverage = payload.get("coverage", {})
    rows = "".join(
        "<tr><td>"
        + html.escape(str(item.get("id", "")))
        + " <span class='check-help' tabindex='0' title='"
        + html.escape(check_hint(str(item.get("id", "")), str(item.get("title", "")), str(item.get("category", "")), language))
        + "'>?</span>"
        + "</td><td>"
        + html.escape(status_labels.get(str(item.get("status", "")), str(item.get("status", ""))))
        + "</td><td>"
        + html.escape(
            crawl_classification_label(item.get("summary"), language)
            if str(item.get("summary", "")) in {"complete_within_scope", "partial_limit", "partial_error"}
            else str(item.get("summary", item.get("title", "")))
        )
        + "</td></tr>"
        for item in findings
        if isinstance(item, dict)
    )
    report_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    status_counts = {status: sum(1 for item in findings if isinstance(item, dict) and item.get("status") == status) for status in ("fail", "warn", "pass", "skip", "error")}
    summary_label = "Сводка для печати" if language == "ru" else "Print summary"
    summary_text = (
        f"Ошибки: {status_counts['fail'] + status_counts['error']} · предупреждения: {status_counts['warn']} · пройдено: {status_counts['pass']}"
        if language == "ru"
        else f"Errors: {status_counts['fail'] + status_counts['error']} · warnings: {status_counts['warn']} · passed: {status_counts['pass']}"
    )
    return (
        "<!doctype html><html lang='"
        + html.escape(language)
        + "'><head><meta charset='utf-8'><title>"
        + html.escape(labels["title"])
        + "</title>"
        + "<style>body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}"
        + "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd;padding:.5rem;text-align:left}"
        + "@media print{body{max-width:none;margin:0;padding:0;font-size:11pt}.check-help{display:none}.print-note{border:1px solid #ccd;padding:.4rem;margin:.8rem 0}table{font-size:10pt;page-break-inside:auto}tr{page-break-inside:avoid}h1{font-size:18pt}}"
        + "code{background:#f3f4f6;padding:.1rem .25rem}.check-help{display:inline-flex;align-items:center;justify-content:center;width:1.1em;height:1.1em;border:1px solid #9e2f0b;border-radius:50%;font-size:.75em;color:#9e2f0b;cursor:help}.check-help:focus::after,.check-help:hover::after{content:attr(title);position:absolute;z-index:2;background:#24130d;color:#fff;padding:.4rem;border-radius:.3rem;max-width:22rem}</style></head><body>"
        + "<main id='report-content'><h1>"
        + html.escape(labels["title"])
        + "</h1><p>"
        + html.escape(labels["target"])
        + ": <code>"
        + html.escape(str(payload.get("target", "")))
        + "</code></p><p>"
        + html.escape(labels["coverage"])
        + ": "
        + html.escape(crawl_classification_label(coverage.get("classification"), payload.get("request", {}).get("language", "en")))
        + ", "
        + html.escape(labels["fetched"])
        + " "
        + html.escape(str(coverage.get("urls_fetched", 0)))
        + " URL(s).</p><section class='print-note'><strong>"
        + html.escape(summary_label)
        + "</strong><br>"
        + html.escape(summary_text)
        + "</section><table><thead><tr><th>"
        + html.escape(labels["finding"])
        + "</th><th>"
        + html.escape(labels["status"])
        + "</th><th>"
        + html.escape(labels["summary"])
        + "</th></tr></thead><tbody>"
        + rows
        + "</tbody></table></main><script id='agentready-v2-report' type='application/json'>"
        + report_json
        + "</script></body></html>"
    )


def _run_and_save_v2_job(request: V2AuditRequest, progress_callback: object) -> dict:
    """Run a background audit and persist standalone JSON and HTML artifacts."""
    payload = _run_v2_scan(request, progress_callback=progress_callback)
    json_path = save_report(payload, target=request.url, surface="job-v2", fmt="json")
    html_path = save_report(_render_v2_dashboard(payload), target=request.url, surface="job-v2", fmt="html")
    logger.info("background v2 report saved json=%s html=%s", json_path, html_path)
    return payload


def _robots_diff_payload(run_id: str, request: RobotsSimulationRequest) -> dict:
    try:
        store = _V2_RUNS.get(run_id)
    except KeyError as exc:
        raise ValueError("run not found") from exc
    query = QueryService(store)
    first_page = query.run_urls(RunUrlQuery(run_id, limit=1))
    if not first_page.items and not request.origin:
        raise ValueError("origin is required when the run has no stored URLs")
    origin = request.origin or f"{urlsplit(first_page.items[0].url_key).scheme}://{urlsplit(first_page.items[0].url_key).netloc}"
    live = parse_robots(request.live_robots, origin)
    simulated = parse_robots(request.proposed_robots, origin)
    interpretation = RobotsInterpretation(request.interpretation)
    service = RobotsSimulationService(query)
    per_bot: dict[str, dict] = {}
    for user_agent in dict.fromkeys(request.user_agents):
        diff = service.simulate(
            run_id,
            live,
            simulated,
            user_agent=user_agent,
            observed_search_pages=request.observed_search_pages,
            interpretation=interpretation,
        )
        per_bot[user_agent] = {
            "newly_allowed": list(diff.newly_allowed_urls),
            "newly_blocked": list(diff.newly_blocked_urls),
            "sitemap_conflicts": list(diff.sitemap_urls_affected),
            "important_page_conflicts": list(diff.observed_search_pages_affected),
        }
    primary = per_bot[request.user_agents[0]]
    live_hash = hashlib.sha256(request.live_robots.encode("utf-8")).hexdigest()
    proposed_hash = hashlib.sha256(request.proposed_robots.encode("utf-8")).hexdigest()
    logger.info(
        "[FIX:robots-simulation] run_id=%s interpretation=%s bots=%d live_hash=%s proposed_hash=%s affected=%d",
        run_id,
        request.interpretation,
        len(per_bot),
        live_hash[:12],
        proposed_hash[:12],
        sum(len(item["newly_allowed"]) + len(item["newly_blocked"]) for item in per_bot.values()),
    )
    return {
        "schema": "agentready.robots-simulation.v2",
        "run_id": run_id,
        "origin": origin,
        "interpretation": request.interpretation,
        "live_policy_hash": live_hash,
        "proposed_policy_hash": proposed_hash,
        "newly_allowed": primary["newly_allowed"],
        "newly_blocked": primary["newly_blocked"],
        "sitemap_conflicts": primary["sitemap_conflicts"],
        "important_page_conflicts": primary["important_page_conflicts"],
        "per_bot_diff": per_bot,
        "label": "SIMULATION - site not changed",
    }


@app.post("/v2/runs/{run_id}/robots/simulate")
def robots_simulate_endpoint(run_id: str, request: RobotsSimulationRequest) -> dict:
    """Compare supplied robots policies against stored inventory without refetching."""
    try:
        return _robots_diff_payload(run_id, request)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/runs/{run_id}/sitemap/reconcile")
def sitemap_reconcile_endpoint(run_id: str, request: SitemapReconciliationRequest) -> object:
    """Reconcile supplied sitemap XML with the stored run inventory."""
    try:
        store = _V2_RUNS.get(run_id)
        records = {
            page.url_key: {
                "status_code": page.status_code,
                "canonical": page.canonical,
                "noindex": page.locally_indexable is False,
                "blocked": False,
            }
            for page in store.iter_pages(run_id)
        }
        report = build_reconciliation_report(
            request.documents, records, origin=request.origin, sitemap_id=request.sitemap_id
        )
        if request.format == "csv":
            return {"run_id": run_id, "sitemap_id": report.sitemap_id, "category": request.category, "format": "csv", "content": report.export(request.category, "csv")}
        page = report.page(request.category, cursor=request.cursor, limit=request.limit)
        return {"run_id": run_id, "sitemap_id": report.sitemap_id, "source_count": report.source_count, "sitemap_urls": list(report.sitemap_urls), "classifications": {key: len(value) for key, value in report.classifications.categories.items()}, **page}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/custom-rules/validate")
def custom_rules_validate_endpoint(request: CustomRulesRequest) -> dict[str, object]:
    try:
        return validate_rules(request.rules)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/custom-rules/debug")
def custom_rules_debug_endpoint(request: CustomRulesRequest) -> dict[str, object]:
    try:
        document = compile_rules(request.rules)
        return apply_rules(document, url=request.url, text=request.text, headers=request.headers, structured_data=request.structured_data, links=request.links, resources=request.resources, css_matches=request.css_matches)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/custom-rules/apply")
def custom_rules_apply_endpoint(request: CustomRulesRequest) -> dict[str, object]:
    """Apply declarative rules to a supplied representation; no crawl is started."""
    try:
        document = compile_rules(request.rules)
        result = apply_rules(document, url=request.url, text=request.text, headers=request.headers, structured_data=request.structured_data, links=request.links, resources=request.resources, css_matches=request.css_matches)
        if request.run_id:
            store = _V2_RUNS.get(request.run_id)
            affected_url = request.url_key or request.url
            for item in result["matches"]:
                if item["count"]:
                    finding_id = f"custom-rule:{item['rule_id']}"
                    store.put_finding(request.run_id, finding_id, {"id": finding_id, "status": "fail", "rule_version": document.version, "rule_hash": document.rule_hash, "affected_urls": [affected_url] if affected_url else [], "match_count": item["count"]})
            logger.info("custom rules findings persisted run_id=%s rule_hash=%s", request.run_id, document.rule_hash[:16])
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/audit")
def audit_v2_endpoint(request: V2AuditRequest) -> dict:
    """Run the canonical v2 report through the shared audit service."""
    try:
        payload = _run_v2_scan(request)
        saved_path = save_report(payload, target=request.url, surface="api-v2", fmt="json")
        logger.info("API report saved path=%s", saved_path)
        return payload
    except (TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/projects")
def create_project_endpoint(request: ProjectCreateRequest) -> dict[str, object]:
    try:
        project = ProjectService(_project_store()).create(ProjectRecord(request.project_id, request.name, request.target, request.default_profile, request.default_ruleset, retention_policy=request.retention_policy))
        return project_to_dict(project)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v2/projects")
def list_projects_endpoint() -> list[dict[str, object]]:
    return [project_to_dict(project) for project in ProjectService(_project_store()).list()]


@app.get("/v2/projects/{project_id}")
def get_project_endpoint(project_id: str) -> dict[str, object]:
    try:
        return project_to_dict(ProjectService(_project_store()).get(project_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc


@app.patch("/v2/projects/{project_id}")
def update_project_endpoint(project_id: str, request: ProjectUpdateRequest) -> dict[str, object]:
    try:
        project = ProjectService(_project_store()).update(project_id, name=request.name, default_profile=request.default_profile, default_ruleset=request.default_ruleset, retention_policy=request.retention_policy)
        return project_to_dict(project)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/v2/projects/{project_id}")
def delete_project_endpoint(project_id: str) -> dict[str, object]:
    try:
        service = ProjectService(_project_store())
        service.get(project_id)
        service.delete_metadata(project_id)
        return {"project_id": project_id, "deleted": True, "runs_retained": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc


@app.post("/v2/projects/{project_id}/runs")
def start_project_run_endpoint(project_id: str, request: ProjectRunRequest) -> dict[str, object]:
    try:
        service = ProjectService(_project_store())
        project = service.get(project_id)
        audit_request = V2AuditRequest(url=project.target, preset=request.preset, profile=request.profile or project.default_profile, language=request.language, max_pages=request.max_pages, rescan_of=request.parent_run_id)
        payload = _run_v2_scan(audit_request, parent_run_id=request.parent_run_id)
        run_id = str(payload.get("run", {}).get("id", ""))
        if not run_id:
            raise ValueError("audit did not return a run id")
        relation = service.attach_run(project_id, run_id, target=project.target, parent_run_id=request.parent_run_id, baseline_run_id=request.baseline_run_id, trigger=request.trigger)
        return {"project": project_to_dict(project), "run": project_run_to_dict(relation), "audit": payload}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project or run not found") from exc
    except (TargetError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v2/projects/{project_id}/runs")
def project_history_endpoint(project_id: str, cursor: str | None = None, limit: int = Query(default=100, ge=1, le=1000)) -> dict[str, object]:
    try:
        service = ProjectService(_project_store())
        rows = service.history(project_id, limit=1000)
        if cursor:
            rows = tuple(item for item in rows if f"{item.created_at}:{item.run_id}" < cursor)
        selected = rows[: limit + 1]
        items = selected[:limit]
        return {"project_id": project_id, "items": [project_run_to_dict(item) for item in items], "next_cursor": f"{items[-1].created_at}:{items[-1].run_id}" if len(selected) > limit else None, "total": len(rows)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc


@app.post("/v2/projects/{project_id}/baseline")
def project_baseline_endpoint(project_id: str, payload: dict) -> dict[str, object]:
    run_id = str(payload.get("run_id", ""))
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id is required")
    try:
        relation = ProjectService(_project_store()).set_baseline(project_id, run_id)
        return project_run_to_dict(relation)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="project run not found") from exc


@app.post("/v2/audit/dashboard", response_class=HTMLResponse)
def audit_v2_dashboard_endpoint(request: V2AuditRequest) -> HTMLResponse:
    """Render the canonical AuditService result for dashboard projections."""
    try:
        payload = _run_v2_scan(request)
        html_report = _render_v2_dashboard(payload)
        saved_path = save_report(html_report, target=request.url, surface="dashboard-v2", fmt="html")
        logger.info("dashboard report saved path=%s", saved_path)
        return HTMLResponse(html_report)
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
        job_ref: dict[str, str] = {}
        def update_job_progress(values: dict) -> None:
            if job_ref.get("id"):
                _V2_JOBS.update_progress(job_ref["id"], **values)

        job_id = _V2_JOBS.submit(lambda: _run_and_save_v2_job(request, progress_callback=update_job_progress))
        job_ref["id"] = job_id
    except (RuntimeError, TargetError, ValueError) as exc:
        raise HTTPException(status_code=429 if isinstance(exc, RuntimeError) else 400, detail=str(exc)) from exc
    return {"job_id": job_id, "status": "running"}


@app.get("/v2/jobs/{job_id}")
def audit_v2_job_status_endpoint(job_id: str) -> dict:
    try:
        payload = _V2_JOBS.get(job_id).to_dict()
        if payload.get("status") == "completed" and isinstance(payload.get("result"), dict):
            payload["html"] = _render_v2_dashboard(payload["result"])
        return payload
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


@app.post("/v2/runs/{run_id}/provider-enrichment")
def provider_enrichment_endpoint(run_id: str, request: ProviderEnrichmentRequest) -> dict:
    """Project cached external measurements into the canonical metric inventory."""
    try:
        return _run_provider_enrichment(run_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404 if "run not found" in str(exc) else 400, detail=str(exc)) from exc


@app.post("/v2/runs/{run_id}/provider-jobs")
def provider_job_endpoint(run_id: str, request: ProviderEnrichmentRequest) -> dict:
    """Queue bounded provider enrichment; credentials are never accepted here."""
    try:
        _V2_RUNS.get(run_id)
        job_id = _V2_JOBS.submit(lambda: _run_provider_enrichment(run_id, request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    logger.info("provider enrichment job submitted run_id=%s job_id=%s provider=%s", run_id, job_id, request.provider)
    return {"job_id": job_id, "status": "running", "provider": request.provider}


@app.post("/v2/diff")
def audit_v2_diff_endpoint(payload: dict) -> dict:
    try:
        request = V2AuditRequest.model_validate(payload["request"])
        current = _run_v2_scan(request)
        baseline = payload["baseline"]
        result = semantic_diff(current, baseline)
        legacy = diff_reports(report_from_dict(current), baseline).to_dict() if result.comparable else {}
        return {**legacy, **result.to_dict()}
    except (KeyError, TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/export")
def audit_v2_export_endpoint(payload: dict) -> dict:
    format_name = payload.get("format", "jsonl")
    try:
        return {"format": format_name, "content": export_inventory(payload.get("items", []), format=format_name)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _inventory_item(item: object) -> dict:
    """Serialize one allowlisted store record without exposing store internals."""
    if is_dataclass(item):
        value = asdict(item)
    elif isinstance(item, dict):
        value = dict(item)
    else:
        raise TypeError(f"unsupported inventory record: {type(item).__name__}")
    return _json_safe(value)


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value


def _inventory_response(run_id: str, query: object) -> dict:
    try:
        store = _V2_RUNS.get(run_id)
        page = QueryService(store).execute(query)  # type: ignore[arg-type]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    assert isinstance(page, QueryPage)
    return {
        "run_id": run_id,
        "items": [_inventory_item(item) for item in page.items],
        "next_cursor": page.next_cursor,
        "total": page.total,
    }


def _build_inventory_query(run_id: str, kind: str, payload: dict) -> object:
    """Build one allowlisted QuerySpec from a bounded saved-view payload."""
    common = {
        "cursor": payload.get("cursor"),
        "limit": int(payload.get("limit", 100)),
    }
    if kind == "pages":
        return PageQuery(
            run_id,
            status_code=payload.get("status_code"),
            locally_indexable=payload.get("locally_indexable"),
            min_depth=payload.get("min_depth"),
            max_depth=payload.get("max_depth"),
            title_contains=payload.get("title_contains"),
            canonical=payload.get("canonical"),
            sort_by=payload.get("sort_by", "url"),
            descending=bool(payload.get("descending", False)),
            **common,
        )
    if kind in {"run-urls", "urls"}:
        state = payload.get("state")
        return RunUrlQuery(run_id, state=RunUrlState(state) if state else None, **common)
    if kind == "links":
        return LinkQuery(run_id, source_key=payload.get("source_key"), target_key=payload.get("target_key"), rel=payload.get("rel"), anchor_contains=payload.get("anchor_contains"), internal=payload.get("internal"), sort_by=payload.get("sort_by", "source"), descending=bool(payload.get("descending", False)), **common)
    if kind == "resources":
        return ResourceQuery(run_id, page_key=payload.get("page_key"), resource_type=payload.get("resource_type"), status_code=payload.get("status_code"), sort_by=payload.get("sort_by", "page"), descending=bool(payload.get("descending", False)), **common)
    if kind == "redirects":
        return RedirectQuery(
            run_id,
            from_url=payload.get("from_url"),
            status_code=payload.get("status_code"),
            to_url=payload.get("to_url"),
            sort_by=payload.get("sort_by", "from_url"),
            descending=bool(payload.get("descending", False)),
            **common,
        )
    if kind == "findings":
        return FindingQuery(
            run_id,
            finding_id=payload.get("finding_id"),
            status=payload.get("status"),
            affected_url=payload.get("affected_url"),
            sort_by=payload.get("sort_by", "finding_id"),
            descending=bool(payload.get("descending", False)),
            **common,
        )
    if kind == "metrics":
        return MetricQuery(
            run_id,
            provider=payload.get("provider"),
            name=payload.get("name"),
            min_value=payload.get("min_value"),
            max_value=payload.get("max_value"),
            sort_by=payload.get("sort_by", "url"),
            descending=bool(payload.get("descending", False)),
            **common,
        )
    raise ValueError(f"unsupported inventory kind: {kind}")


@app.post("/v2/saved-views")
def create_v2_saved_view(payload: dict) -> dict:
    try:
        view_id = str(payload["id"])
        name = str(payload["name"])
        run_id = str(payload["run_id"])
        query = _build_inventory_query(run_id, str(payload["kind"]), payload)
        view = _V2_SAVED_VIEWS.save(SavedView(view_id, name, query))
        _persist_saved_views()
        return {"id": view.id, "name": view.name, "query": type(view.query).__name__}
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v2/saved-views")
def list_v2_saved_views() -> list[dict]:
    return [view.to_dict() for view in _V2_SAVED_VIEWS.list()]


@app.delete("/v2/saved-views/{view_id}")
def delete_v2_saved_view(view_id: str) -> dict:
    try:
        view = _V2_SAVED_VIEWS.get(view_id)
        _V2_SAVED_VIEWS.delete(view_id)
        _persist_saved_views()
        return {"id": view.id, "deleted": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="saved view not found") from exc


@app.get("/v2/saved-views/{view_id}")
def execute_v2_saved_view(view_id: str, limit: int = Query(default=100, ge=1, le=1000)) -> dict:
    try:
        view = _V2_SAVED_VIEWS.get(view_id)
        query = replace(view.query, limit=limit)
        payload = _inventory_response(query.run_id, query)
        payload["query"] = view.to_dict()
        return payload
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="saved view not found") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v2/saved-views/{view_id}/export")
def export_v2_saved_view(view_id: str, format: str = Query(default="json")) -> dict:
    try:
        view = _V2_SAVED_VIEWS.get(view_id)
        store = _V2_RUNS.get(view.query.run_id)
        content = export_query(QueryService(store), view.query, format=format)
        return {"id": view.id, "format": format, "content": content}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="saved view or run not found") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v2/runs/{run_id}/pages")
def audit_v2_pages_endpoint(
    run_id: str,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    status_code: int | None = Query(default=None, ge=100, le=599),
) -> dict:
    return _inventory_response(run_id, PageQuery(run_id, status_code=status_code, cursor=cursor, limit=limit))


@app.get("/v2/runs/{run_id}/overview")
def audit_v2_overview_endpoint(run_id: str) -> dict:
    """Return bounded run metadata and counts for the dashboard inventory view."""
    try:
        store = _V2_RUNS.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    service = QueryService(store)
    queries = {
        "pages": PageQuery(run_id, limit=1),
        "run_urls": RunUrlQuery(run_id, limit=1),
        "links": LinkQuery(run_id, limit=1),
        "resources": ResourceQuery(run_id, limit=1),
        "redirects": RedirectQuery(run_id, limit=1),
        "findings": FindingQuery(run_id, limit=1),
        "metrics": MetricQuery(run_id, limit=1),
    }
    return {
        "run_id": run_id,
        "inventory": {name: service.count(query) for name, query in queries.items()},
    }


@app.get("/v2/runs/{run_id}/graph")
def audit_v2_graph_endpoint(
    run_id: str,
    origin: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    dead_end: bool | None = None,
    disconnected: bool | None = None,
) -> dict:
    """Return the cached bounded link graph node projection."""
    try:
        projection = _link_graph_projection(run_id, origin)
        nodes = tuple(item for item in projection.nodes if (dead_end is None or item.dead_end is dead_end) and (disconnected is None or item.disconnected is disconnected))
        if cursor:
            nodes = tuple(item for item in nodes if item.url > cursor)
        selected = nodes[: limit + 1]
        items = selected[:limit]
        return {"run_id": run_id, "version": projection.version, "fingerprint": projection.fingerprint, "algorithm_version": projection.graph.algorithm_version, "items": [{"url": item.url, "inlinks": item.inlinks, "outlinks": item.outlinks, "unique_inlinks": item.unique_inlinks, "unique_outlinks": item.unique_outlinks, "depth": item.depth, "dead_end": item.dead_end, "disconnected": item.disconnected, "nofollow_inlinks": item.nofollow_inlinks, "redirect_inlinks": item.redirect_inlinks, "authority": item.authority} for item in items], "next_cursor": items[-1].url if len(selected) > limit else None, "total": len(nodes)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v2/runs/{run_id}/graph/node")
def audit_v2_graph_node_endpoint(run_id: str, url: str, origin: str | None = None) -> dict:
    try:
        projection = _link_graph_projection(run_id, origin)
        node = projection.node(url)
        return {"run_id": run_id, "version": projection.version, "algorithm_version": projection.graph.algorithm_version, "node": {"url": node.url, "inlinks": node.inlinks, "outlinks": node.outlinks, "unique_inlinks": node.unique_inlinks, "unique_outlinks": node.unique_outlinks, "depth": node.depth, "dead_end": node.dead_end, "disconnected": node.disconnected, "nofollow_inlinks": node.nofollow_inlinks, "redirect_inlinks": node.redirect_inlinks, "authority": node.authority}, "inbound": [edge.source for edge in projection.graph.edges if edge.target == url], "outbound": [edge.target for edge in projection.graph.edges if edge.source == url]}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run or graph node not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v2/runs/{run_id}/duplicates")
def audit_v2_duplicates_endpoint(
    run_id: str,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    kind: Literal["all", "exact", "near"] = "all",
    threshold: int = Query(default=3, ge=0, le=64),
) -> dict:
    try:
        analysis = _duplicate_analysis(run_id, threshold)
        clusters = tuple(item for item in analysis.clusters if kind == "all" or (kind == "near") is item.near_duplicate)
        if cursor:
            clusters = tuple(item for item in clusters if item.cluster_id > cursor)
        selected = clusters[: limit + 1]
        items = selected[:limit]
        return {"run_id": run_id, "algorithm_version": analysis.algorithm_version, "threshold": analysis.threshold, "fingerprint": analysis.fingerprint, "candidate_comparisons": analysis.candidate_comparisons, "items": [{"cluster_id": item.cluster_id, "near_duplicate": item.near_duplicate, "members": [{"url": member.url, "kind": member.kind, "similarity": member.similarity, "exact_hash": member.exact_hash} for member in item.members]} for item in items], "next_cursor": items[-1].cluster_id if len(selected) > limit else None, "total": len(clusters)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v2/runs/{run_id}/duplicates/{cluster_id}")
def audit_v2_duplicate_cluster_endpoint(run_id: str, cluster_id: str, threshold: int = Query(default=3, ge=0, le=64)) -> dict:
    try:
        analysis = _duplicate_analysis(run_id, threshold)
        cluster = next(item for item in analysis.clusters if item.cluster_id == cluster_id)
        return {"run_id": run_id, "algorithm_version": analysis.algorithm_version, "threshold": analysis.threshold, "cluster": {"cluster_id": cluster.cluster_id, "near_duplicate": cluster.near_duplicate, "members": [{"url": member.url, "kind": member.kind, "similarity": member.similarity, "exact_hash": member.exact_hash} for member in cluster.members]}}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run or cluster not found") from exc
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="duplicate cluster not found") from exc


@app.get("/v2/runs/{run_id}/run-urls")
@app.get("/v2/runs/{run_id}/urls")
def audit_v2_run_urls_endpoint(
    run_id: str,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    state: RunUrlState | None = None,
) -> dict:
    return _inventory_response(run_id, RunUrlQuery(run_id, state=state, cursor=cursor, limit=limit))


@app.get("/v2/runs/{run_id}/inventory/{kind}")
def audit_v2_inventory_endpoint(
    run_id: str,
    kind: Literal["pages", "run-urls", "links", "resources", "redirects", "findings", "metrics"],
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    search: str | None = None,
    sort_by: str | None = None,
    descending: bool = False,
) -> dict:
    """Dispatch only to the fixed, typed inventory projections."""
    try:
        store = _V2_RUNS.get(run_id)
        response = _AUDIT_SERVICE.query_inventory(
            InventoryRequest(run_id, kind=kind, limit=limit, cursor=cursor, search=search, sort_by=sort_by, descending=descending),
            store=store,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run_id": response.run_id, "kind": response.kind, "items": [_inventory_item(item) for item in response.items], "next_cursor": response.next_cursor, "total": response.total}


@app.get("/v2/runs/{run_id}/links")
def audit_v2_links_endpoint(
    run_id: str,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    source_key: str | None = None,
) -> dict:
    return _inventory_response(run_id, LinkQuery(run_id, source_key=source_key, cursor=cursor, limit=limit))


@app.get("/v2/runs/{run_id}/resources")
def audit_v2_resources_endpoint(
    run_id: str,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    page_key: str | None = None,
) -> dict:
    return _inventory_response(run_id, ResourceQuery(run_id, page_key=page_key, cursor=cursor, limit=limit))


@app.get("/v2/runs/{run_id}/redirects")
def audit_v2_redirects_endpoint(
    run_id: str,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    from_url: str | None = None,
    status_code: int | None = Query(default=None, ge=300, le=399),
) -> dict:
    return _inventory_response(
        run_id,
        RedirectQuery(run_id, from_url=from_url, status_code=status_code, cursor=cursor, limit=limit),
    )


@app.get("/v2/runs/{run_id}/findings")
def audit_v2_findings_endpoint(
    run_id: str,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    finding_id: str | None = None,
    status: Literal["pass", "fail", "warn", "skip", "unavailable"] | None = None,
) -> dict:
    return _inventory_response(
        run_id,
        FindingQuery(run_id, finding_id=finding_id, status=status, cursor=cursor, limit=limit),
    )


@app.get("/v2/runs/{run_id}/metrics")
def audit_v2_metrics_endpoint(
    run_id: str,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    provider: str | None = None,
    name: str | None = None,
) -> dict:
    return _inventory_response(
        run_id,
        MetricQuery(run_id, provider=provider, name=name, cursor=cursor, limit=limit),
    )


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


@app.post("/v2/mobile/audit")
def mobile_audit_endpoint(request: MobileRequest) -> dict:
    """Run a mobile-friendliness audit for one or more public pages."""
    try:
        payload = _run_mobile(request).to_dict()
        saved_path = save_report(payload, target=request.urls[0], surface="api-mobile", fmt="json")
        logger.info("API report saved path=%s", saved_path)
        return payload
    except (TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/mobile/audit/dashboard", response_class=HTMLResponse)
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
    from .ai_models import AssistantRequest, ConversationMessage
    from .ai_provider import AIProviderError, OpenAICompatibleProvider
    from .config import load_config

    cfg, _ = load_config()
    ai_cfg = cfg["ai"]
    if not ai_cfg["enabled"] or not ai_cfg["transport_enabled"]:
        raise HTTPException(status_code=404, detail="AI assistant transport is disabled")
    if request.report is None:
        if not request.target:
            raise HTTPException(status_code=400, detail="target or report is required")
        report = _run_v2_scan(V2AuditRequest(url=request.target, language=request.language))
        report_object = report
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
    known = set(SEO_CHECKS_BY_ID) | set(CRAWL_CHECKS_BY_ID)
    selected = tuple(request.checks or ())
    unknown = [check_id for check_id in selected if check_id not in known]
    if unknown:
        raise ValueError(f"Unknown SEO check(s): {', '.join(unknown)}")
    logger.info("[FIX:seo-canonical] HTTP SEO request checks=%d providers=%s", len(selected), bool(request.ga_property or request.gsc_site))
    return audit_seo(
        request.url,
        profile=request.profile,
        timeout=request.timeout,
        allow_private=False,
        recommendation_limit=request.recommendation_limit,
        limits=request.limits,
        language=request.language,
        crawl=request.crawl or bool(selected),
        max_pages=request.max_pages,
        render=request.render,
        checks=tuple(SEO_CHECKS_BY_ID[check_id] for check_id in selected if check_id in SEO_CHECKS_BY_ID),
        crawl_checks=tuple(CRAWL_CHECKS_BY_ID[check_id] for check_id in selected if check_id in CRAWL_CHECKS_BY_ID),
        ga_property=request.ga_property,
        gsc_site=request.gsc_site,
    )


@app.post("/v2/seo/audit")
def seo_audit_endpoint(request: SeoRequest) -> dict:
    """Run the independent SEO audit against one public page and discovery resources."""
    try:
        payload = _run_seo(request).to_dict()
        saved_path = save_report(payload, target=request.url, surface="api-seo", fmt="json")
        logger.info("API report saved path=%s", saved_path)
        return payload
    except (TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v2/seo/audit/dashboard", response_class=HTMLResponse)
def seo_audit_dashboard(request: SeoRequest) -> HTMLResponse:
    """Return the independent SEO audit as a self-contained HTML report."""
    try:
        report = _run_seo(request)
        html_report = render_seo_html(report, request.language)
        saved_path = save_report(html_report, target=request.url, surface="dashboard-seo", fmt="html")
        logger.info("dashboard report saved path=%s", saved_path)
        return HTMLResponse(html_report)
    except (TargetError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
