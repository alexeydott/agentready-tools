"""Bounded factual exports for QueryService projections."""
from __future__ import annotations

import csv
import io
import json
import html
from dataclasses import replace
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable

from .query_service import QueryService, QuerySpec


def export_json(rows: Iterable[Any], *, limit: int = 100_000) -> str:
    values = _bounded(rows, limit)
    return json.dumps([_row(item) for item in values], ensure_ascii=True, sort_keys=True)


def export_jsonl(rows: Iterable[Any], *, limit: int = 100_000) -> str:
    values = _bounded(rows, limit)
    return "\n".join(json.dumps(_row(item), ensure_ascii=True, sort_keys=True) for item in values)


def export_csv(rows: Iterable[Any], *, limit: int = 100_000) -> str:
    values = [_row(item) for item in _bounded(rows, limit)]
    if not values:
        return ""
    fields = sorted({key for row in values for key in row})
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(values)
    return output.getvalue()


def export_markdown(rows: Iterable[Any], *, limit: int = 100_000) -> str:
    values = [_row(item) for item in _bounded(rows, limit)]
    if not values:
        return ""
    fields = sorted({key for row in values for key in row})
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    lines.extend(
        "| " + " | ".join(str(row.get(field, "")).replace("|", "\\|") for field in fields) + " |"
        for row in values
    )
    return "\n".join(lines) + "\n"


def export_html(rows: Iterable[Any], *, limit: int = 100_000) -> str:
    values = [_row(item) for item in _bounded(rows, limit)]
    fields = sorted({key for row in values for key in row})
    header = "".join(f"<th>{html.escape(str(field))}</th>" for field in fields)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in fields) + "</tr>"
        for row in values
    )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def brand_html(content: str, *, name: str = "AgentReady Tools", accent: str = "#2563eb") -> str:
    """Apply presentation-only branding around factual rendered content."""
    if not name.strip() or not accent.strip():
        raise ValueError("brand name and accent are required")
    return (
        f'<div class="agentready-report" data-brand="{html.escape(name)}" '
        f'style="--agentready-accent:{html.escape(accent, quote=True)}">'
        f"<header><strong>{html.escape(name)}</strong></header>{content}</div>"
    )


def export_query(
    query_service: QueryService,
    query: QuerySpec,
    *,
    format: str = "json",
    limit: int = 100_000,
) -> str:
    """Export a bounded complete result set from a typed QuerySpec."""
    if limit <= 0 or limit > 100_000:
        raise ValueError("query export limit must be between 1 and 100000")
    rows: list[Any] = []
    cursor: str | None = query.cursor
    while len(rows) < limit:
        page = query_service.execute(replace(query, cursor=cursor, limit=min(query.limit, limit - len(rows))))
        rows.extend(page.items)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    exporters = {
        "json": export_json,
        "jsonl": export_jsonl,
        "csv": export_csv,
        "markdown": export_markdown,
        "html": export_html,
    }
    try:
        exporter = exporters[format]
    except KeyError as exc:
        raise ValueError(f"unsupported query export format: {format}") from exc
    return exporter(rows, limit=limit)


def _bounded(rows: Iterable[Any], limit: int) -> list[Any]:
    if limit <= 0 or limit > 100_000:
        raise ValueError("export limit must be between 1 and 100000")
    values = []
    for item in rows:
        values.append(item)
        if len(values) >= limit:
            break
    return values


def _row(item: Any) -> dict[str, Any]:
    if is_dataclass(item):
        return asdict(item)
    if isinstance(item, dict):
        return dict(item)
    raise TypeError(f"unsupported export row: {type(item).__name__}")
