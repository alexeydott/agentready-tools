"""Small reusable HTML components for static reports and dashboard embeds."""

from __future__ import annotations

import html
import logging


logger = logging.getLogger(__name__)


_STATUS_MARKERS = {
    "pass": "✓",
    "warn": "!",
    "fail": "×",
    "error": "!",
    "skip": "–",
}


def render_status_badge(status: str, label: str) -> str:
    """Render an escaped, non-color-only status badge."""
    safe_status = html.escape(status, quote=True)
    marker = _STATUS_MARKERS.get(status, "•")
    return (
        f"<span class='status-badge status-{safe_status}'>"
        f"<span class='status-marker' aria-hidden='true'>{marker}</span>"
        f"<span class='status-label'>{html.escape(label)}</span></span>"
    )


def render_status_cell(status: str, label: str) -> str:
    """Render a shared status table cell with a textual and symbolic badge."""
    safe_status = html.escape(status, quote=True)
    return f"<td class='status-cell {safe_status}'>{render_status_badge(status, label)}</td>"


def render_check_cell(title: str, check_id: str, hint: str) -> str:
    """Render the shared check-name cell used by every report profile."""
    safe_title = html.escape(title)
    safe_id = html.escape(check_id)
    safe_hint = html.escape(hint, quote=True)
    return (
        "<td class='check-cell'><span class='check-name'>"
        f"{safe_title}</span> <span class='check-help' tabindex='0' role='img' "
        f"aria-label='{safe_hint}' data-tooltip='{safe_hint}'>?</span>"
        f"<small><code>{safe_id}</code></small></td>"
    )


def render_score_meter(score: int, label: str, *, title_id: str = "report-score-title") -> str:
    """Render a bounded semantic score meter with a visible text value."""
    bounded_score = max(0, min(100, score))
    safe_label = html.escape(label)
    safe_title_id = html.escape(title_id, quote=True)
    return (
        f"<div class='score-panel' aria-labelledby='{safe_title_id}'>"
        f"<span id='{safe_title_id}' class='score-label'>{safe_label}</span>"
        f"<meter min='0' max='100' value='{bounded_score}' aria-label='{safe_label}'>{bounded_score}/100</meter>"
        f"<strong class='score'>{bounded_score}/100</strong></div>"
    )


def render_progress_bar(value: int, label: str) -> str:
    """Render a bounded progressbar for a scored category."""
    bounded_value = max(0, min(100, value))
    return (
        f"<div class='bar' role='progressbar' aria-valuemin='0' aria-valuemax='100' "
        f"aria-valuenow='{bounded_value}' aria-label='{html.escape(label)}'>"
        f"<span style='width:{bounded_value}%'></span></div>"
    )


def render_category_card(
    name: str,
    hint: str,
    label: str,
    score: int | None,
) -> str:
    """Render a localized category summary card using shared progress semantics."""
    safe_name = html.escape(name)
    safe_hint = html.escape(hint)
    progress = (
        render_progress_bar(score, name)
        if score is not None
        else "<div class='bar bar-na' aria-hidden='true'></div>"
    )
    return (
        f"<div class='card'><b>{safe_name} "
        f"<span class='category-help check-help' tabindex='0' role='img' "
        f"aria-label='{safe_hint}' data-tooltip='{safe_hint}'>?</span></b>"
        f"{progress}<small>{html.escape(label)}</small></div>"
    )


def render_report_table(
    table_id: str,
    caption: str,
    headers: tuple[str, ...],
    rendered_rows: str,
    *,
    table_class: str = "check-table",
) -> str:
    """Render a responsive table; row markup is trusted renderer output."""
    logger.debug(
        "[FIX:report-ui] Rendering report table: id=%s class=%s columns=%d",
        table_id,
        table_class,
        len(headers),
    )
    safe_id = html.escape(table_id, quote=True)
    safe_class = html.escape(table_class, quote=True)
    header_cells = "".join(f"<th scope='col'>{html.escape(header)}</th>" for header in headers)
    rendered = (
        f"<div class='table-wrap'><table id='{safe_id}' class='{safe_class}'><caption>{html.escape(caption)}</caption>"
        f"<thead><tr>{header_cells}</tr></thead><tbody>{rendered_rows}</tbody></table></div>"
    )
    logger.debug("[FIX:report-ui] Report table rendered successfully: id=%s", table_id)
    return rendered


def render_recommendation_list(rendered_items: str, empty_label: str) -> str:
    """Render the prioritized recommendation list with a safe empty state."""
    content = rendered_items or f"<li>{html.escape(empty_label)}</li>"
    return f"<ol class='recommendation-list'>{content}</ol>"


def render_remediation_block(rendered_sections: str, empty_label: str) -> str:
    """Render remediation sections with an escaped localized empty state."""
    return rendered_sections or f"<p>{html.escape(empty_label)}</p>"


def render_report_navigation(
    links: tuple[tuple[str, str], ...],
    aria_label: str,
) -> str:
    """Render escaped in-document report navigation links."""
    rendered_links = "".join(
        f"<a href='#{html.escape(target, quote=True)}'>{html.escape(label)}</a>"
        for target, label in links
    )
    return f"<nav class='report-nav' aria-label='{html.escape(aria_label)}'>{rendered_links}</nav>"


def render_report_toolbar(label: str, options: str) -> str:
    """Render the localized report language selector shell."""
    return (
        f"<div class='toolbar'><label for='lang'>{html.escape(label)}:</label>"
        f"<select id='lang'>{options}</select></div>"
    )


def render_section(section_id: str, title: str, content: str, *, level: int = 2) -> str:
    """Wrap trusted rendered content in an explicitly labelled section."""
    safe_id = html.escape(section_id, quote=True)
    safe_title = html.escape(title)
    return (
        f"<section id='{safe_id}' aria-labelledby='{safe_id}-title'>"
        f"<h{level} id='{safe_id}-title'>{safe_title}</h{level}>{content}</section>"
    )


def render_disclosure(disclosure_id: str, title: str, content: str) -> str:
    """Render a collapsed, keyboard-accessible disclosure section."""
    safe_id = html.escape(disclosure_id, quote=True)
    return (
        f"<details class='report-section'><summary id='{safe_id}'><h3>{html.escape(title)}</h3></summary>"
        f"{content}</details>"
    )
