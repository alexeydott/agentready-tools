from datetime import UTC, datetime

from agentready.audit_core.store import FindingRecord, MetricRecord, PageRecord
from agentready.page_priority import PRIORITY_MODEL_VERSION, rank_pages


def _page(url: str, *, status: int = 200, indexable: bool | None = True) -> PageRecord:
    return PageRecord("run-1", url, url, status_code=status, locally_indexable=indexable)


def test_priority_has_hand_calculable_breakdown_and_stable_tie_order():
    pages = (_page("https://example.test/a"), _page("https://example.test/b"))
    findings = (FindingRecord("run-1", "title", {"status": "fail", "severity": "high", "affected_urls": [pages[1].url_key]}),)
    ranked = rank_pages(pages, findings, authorities={pages[0].url_key: 0.2, pages[1].url_key: 0.2})
    assert ranked[0].url == pages[1].url_key
    assert ranked[0].score == round((0.8 * 0.35 + 0.2 * 0.15) / (0.35 + 0.20 + 0.15 + 0.10), 6)
    assert {factor.code for factor in ranked[0].factors} == {"severity", "url-state", "authority", "traffic", "recurrence", "confidence", "freshness"}
    assert ranked[0].to_dict()["model_version"] == PRIORITY_MODEL_VERSION


def test_missing_external_metrics_do_not_penalize_page_or_randomize_sorting():
    pages = (_page("https://example.test/b"), _page("https://example.test/a"))
    ranked = rank_pages(pages)
    assert [item.url for item in ranked] == ["https://example.test/a", "https://example.test/b"]
    assert all(not factor.available for factor in ranked[0].factors if factor.code in {"traffic", "authority", "freshness"})


def test_sensitivity_to_url_state_and_metric_is_monotonic():
    now = datetime(2026, 8, 18, tzinfo=UTC)
    healthy = _page("https://example.test/healthy")
    broken = _page("https://example.test/broken", status=500)
    metric = MetricRecord("run-1", healthy.url_key, "analytics", "traffic", 1_000_000, "visits", "fixture", "1", now.isoformat())
    ranked = rank_pages((healthy, broken), metrics=(metric,), now=now)
    assert ranked[0].url == broken.url_key
    assert next(item for item in ranked if item.url == healthy.url_key).score > 0
