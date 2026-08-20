"""Deterministic, explainable page-priority ranking for v2 runs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import math
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit

from .audit_core.store import FindingRecord, MetricRecord, PageRecord

PRIORITY_MODEL_VERSION = "page-priority-v1"
_WEIGHTS = {
    "severity": 0.35,
    "url-state": 0.20,
    "authority": 0.15,
    "traffic": 0.10,
    "recurrence": 0.10,
    "confidence": 0.05,
    "freshness": 0.05,
}
_SEVERITY = {"critical": 1.0, "error": 0.9, "high": 0.8, "fail": 0.7, "warn": 0.6, "warning": 0.6, "medium": 0.55, "low": 0.3, "info": 0.15, "pass": 0.0, "skip": 0.0, "unavailable": 0.0}
_TRAFFIC_NAMES = {"traffic", "visits", "sessions", "clicks", "impressions", "search_clicks", "search_impressions", "ai_crawler_visits"}


@dataclass(frozen=True, slots=True)
class PriorityFactor:
    code: str
    value: float
    weight: float
    available: bool
    source: str

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "value": round(self.value, 6), "weight": self.weight, "available": self.available, "source": self.source}


@dataclass(frozen=True, slots=True)
class PagePriority:
    url: str
    score: float
    factors: tuple[PriorityFactor, ...]

    def to_dict(self) -> dict[str, object]:
        return {"url": self.url, "score": round(self.score, 6), "model_version": PRIORITY_MODEL_VERSION, "factors": [factor.to_dict() for factor in self.factors]}


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _url_keys(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _severity(payload: Mapping[str, Any]) -> float:
    raw = str(payload.get("severity") or payload.get("priority") or payload.get("status") or "info").lower()
    return _SEVERITY.get(raw, 0.15 if raw not in {"pass", "skip"} else 0.0)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        return None


def _freshness(observed: Iterable[str], now: datetime) -> tuple[float, bool]:
    dates = [item for value in observed if (item := _parse_time(value)) is not None]
    if not dates:
        return 0.0, False
    age_days = max(0.0, (now - max(dates)).total_seconds() / 86400)
    return 1.0 / (1.0 + age_days / 30.0), True


def rank_pages(
    pages: Iterable[PageRecord],
    findings: Iterable[FindingRecord] = (),
    *,
    authorities: Mapping[str, float] | None = None,
    metrics: Iterable[MetricRecord] = (),
    now: datetime | None = None,
) -> tuple[PagePriority, ...]:
    """Rank pages using only available canonical facts; absent optional data is neutral."""
    page_rows = tuple(sorted(pages, key=lambda item: item.url_key))[:100_000]
    finding_rows = tuple(findings)
    metric_rows = tuple(metrics)
    by_url: dict[str, list[FindingRecord]] = {page.url_key: [] for page in page_rows}
    for finding in finding_rows:
        payload = finding.payload
        urls = _url_keys(payload.get("affected_urls")) or _url_keys(payload.get("urls"))
        for url in urls:
            if url in by_url:
                by_url[url].append(finding)
    metric_values: dict[str, list[MetricRecord]] = {page.url_key: [] for page in page_rows}
    for metric in metric_rows:
        if metric.url_key in metric_values and metric.name.lower() in _TRAFFIC_NAMES:
            metric_values[metric.url_key].append(metric)
    reference = (now or datetime.now(UTC)).astimezone(UTC)
    result: list[PagePriority] = []
    for page in page_rows:
        page_findings = by_url[page.url_key]
        severity = max((_severity(item.payload) for item in page_findings), default=0.0)
        state = 0.0
        if page.status_code is not None:
            state = 1.0 if page.status_code >= 500 else 0.8 if page.status_code >= 400 else 0.45 if page.status_code >= 300 else 0.0
        if page.locally_indexable is False:
            state = max(state, 0.75)
        recurrence = _bounded((len(page_findings) - 1) / 4) if page_findings else 0.0
        confidence_values = [float(item.payload["confidence"]) for item in page_findings if isinstance(item.payload.get("confidence"), (int, float))]
        confidence = _bounded(sum(confidence_values) / len(confidence_values)) if confidence_values else 0.0
        traffic_rows = metric_values[page.url_key]
        traffic_values = []
        for item in traffic_rows:
            try:
                traffic_values.append(math.log1p(max(float(item.value), 0.0)) / math.log1p(1_000_000))
            except (TypeError, ValueError):
                continue
        traffic = _bounded(max(traffic_values)) if traffic_values else 0.0
        authority = _bounded((authorities or {}).get(page.url_key, 0.0)) if authorities and page.url_key in authorities else 0.0
        observed = [item.observed_at for item in traffic_rows] + [str(item.payload["observed_at"]) for item in page_findings if item.payload.get("observed_at")]
        freshness, fresh_available = _freshness(observed, reference)
        values = (("severity", severity, True, "finding.severity"), ("url-state", state, True, "page.status/indexability"), ("authority", authority, authorities is not None and page.url_key in authorities, "link-graph.authority"), ("traffic", traffic, bool(traffic_rows), "metric"), ("recurrence", recurrence, bool(page_findings), "finding.count"), ("confidence", confidence, bool(confidence_values), "finding.confidence"), ("freshness", freshness, fresh_available, "observed_at"))
        factors = tuple(PriorityFactor(code, value, _WEIGHTS[code], available, source) for code, value, available, source in values)
        available_weight = sum(item.weight for item in factors if item.available)
        score = sum(item.value * item.weight for item in factors if item.available) / available_weight if available_weight else 0.0
        result.append(PagePriority(page.url_key, round(score, 6), factors))
    return tuple(sorted(result, key=lambda item: (-item.score, item.url)))
