"""GA4 Data API and Search Console API clients for analytics-based SEO checks.

Both Google APIs authenticate with OAuth2 service accounts. Client libraries
are imported lazily so the base install does not require them; install the
``analytics`` extra to enable these checks. All logging redacts credentials
and reports only counts and property/site identifiers.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from .credentials import load_service_account_info

logger = logging.getLogger(__name__)

GA_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

DEFAULT_RANGE_DAYS = 28


class AnalyticsError(RuntimeError):
    pass


def _credentials(scopes: list[str]):
    info = load_service_account_info()
    if info is None:
        raise AnalyticsError(
            "GA/GSC credentials are not configured. Store a service account with "
            "'agentready credentials set <file.json>' or set GOOGLE_APPLICATION_CREDENTIALS."
        )
    try:
        from google.oauth2 import service_account
    except ImportError as exc:
        raise AnalyticsError("Install analytics extras: pip install 'agentready-tools[analytics]'") from exc
    return service_account.Credentials.from_service_account_info(info, scopes=scopes)


def _ga_client():
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
    except ImportError as exc:
        raise AnalyticsError("Install analytics extras: pip install 'agentready-tools[analytics]'") from exc
    return BetaAnalyticsDataClient(credentials=_credentials(GA_SCOPES))


def _gsc_client():
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise AnalyticsError("Install analytics extras: pip install 'agentready-tools[analytics]'") from exc
    return build("searchconsole", "v1", credentials=_credentials(GSC_SCOPES), cache_discovery=False)


def ga_pages_without_traffic(ga_property: str, days: int = DEFAULT_RANGE_DAYS) -> list[dict[str, Any]]:
    """GA4: pages with zero sessions in the last ``days`` days window.

    Returns rows with zero-session pagePaths derived from the page report.
    """
    client = _ga_client()
    try:
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            RunReportRequest,
        )
    except ImportError as exc:
        raise AnalyticsError("Install analytics extras: pip install 'agentready-tools[analytics]'") from exc
    request = RunReportRequest(
        property=f"properties/{ga_property}",
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="sessions")],
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
    )
    response = client.run_report(request)
    logger.info("GA4 report fetched: property=%s rows=%d", ga_property, len(response.rows))
    return [
        {"page": row.dimension_values[0].value, "sessions": int(row.metric_values[0].value)}
        for row in response.rows
        if int(row.metric_values[0].value) == 0
    ]


def ga_bounce_rate(ga_property: str, page: str, days: int = DEFAULT_RANGE_DAYS) -> float | None:
    """GA4: bounce rate for one page path, or None when there is no data."""
    client = _ga_client()
    try:
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Filter,
            FilterExpression,
            Metric,
            RunReportRequest,
        )
    except ImportError as exc:
        raise AnalyticsError("Install analytics extras: pip install 'agentready-tools[analytics]'") from exc
    request = RunReportRequest(
        property=f"properties/{ga_property}",
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="bounceRate")],
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        dimension_filter=FilterExpression(
            filter=Filter(field_name="pagePath", string_filter=Filter.StringFilter(value=page))
        ),
    )
    response = client.run_report(request)
    if not response.rows:
        logger.debug("GA4 bounce rate: no data for page=%s", page)
        return None
    value = float(response.rows[0].metric_values[0].value)
    logger.debug("GA4 bounce rate: page=%s value=%.3f", page, value)
    return value


def gsc_pages_without_clicks(site_url: str, days: int = DEFAULT_RANGE_DAYS) -> list[dict[str, Any]]:
    """Search Console: pages with impressions but zero clicks."""
    return _gsc_page_query(site_url, days, require_clicks_zero=True)


def gsc_pages_without_impressions(site_url: str, days: int = DEFAULT_RANGE_DAYS) -> list[str]:
    """Search Console: page report is empty for URLs known to the site (checked per URL upstream)."""
    service = _gsc_client()
    body = _gsc_body(site_url, days)
    response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    logger.info("GSC report fetched: site=%s rows=%d", site_url, len(response.get("rows", [])))
    return [row["keys"][0] for row in response.get("rows", [])]


def _gsc_body(site_url: str, days: int) -> dict[str, Any]:
    end = datetime.now(UTC).date()
    start = end - timedelta(days=days)
    return {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["page"],
        "rowLimit": 1000,
    }


def _gsc_page_query(site_url: str, days: int, *, require_clicks_zero: bool) -> list[dict[str, Any]]:
    service = _gsc_client()
    body = _gsc_body(site_url, days)
    response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    rows = response.get("rows", [])
    logger.info("GSC report fetched: site=%s rows=%d clicks_zero=%s", site_url, len(rows), require_clicks_zero)
    out = []
    for row in rows:
        clicks = row.get("clicks", 0)
        impressions = row.get("impressions", 0)
        if require_clicks_zero and clicks == 0 and impressions > 0:
            out.append({"page": row["keys"][0], "impressions": impressions, "clicks": clicks})
    return out
