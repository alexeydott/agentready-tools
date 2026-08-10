from __future__ import annotations

import html
from datetime import datetime
import json
import logging
from typing import Any

from .i18n import (
    SUPPORTED_LANGUAGES,
    category_name,
    category_hint,
    check_hint,
    check_title,
    detail_text,
    effort_label,
    impact_label,
    level_name,
    localized_report_dict,
    normalize_language,
    requirement_label,
    status_label,
    tr,
)
from .models import ScanReport
from .report_styles import BASE_REPORT_CSS

logger = logging.getLogger(__name__)


def render_json(report: ScanReport, lang: str | None = None) -> str:
    lang = normalize_language(lang or report.language)
    return json.dumps(localized_report_dict(report, lang), indent=2, ensure_ascii=False)


def _kind(row: Any, lang: str) -> str:
    if row.supplemental:
        return tr(lang, "supplemental")
    if row.experimental:
        return tr(lang, "experimental")
    return tr(lang, "core")


def render_console(report: ScanReport, lang: str | None = None) -> str:
    lang = normalize_language(lang or report.language)
    lines = [
        f"{tr(lang, 'report_title')}: {report.target}",
        f"{tr(lang, 'score')}: {report.score}/100 | {tr(lang, 'level')} {report.level}: {level_name(report.level, report.level_name, lang)}",
        f"{tr(lang, 'language')}: {lang}",
    ]
    if report.ai_search_score is not None:
        lines.append(
            f"{tr(lang, 'ai_search_score')}: {report.ai_search_score}/100 "
            f"({report.ai_search_applicable} {tr(lang, 'applicable_checks')})"
        )
    if report.config_source:
        lines.append(f"{tr(lang, 'config')}: {report.config_source}")
    lines.append("")
    current = None
    for row in report.checks:
        cat = category_name(row.category, lang)
        if cat != current:
            current = cat
            lines.extend([current, "-" * max(3, len(current))])
        marker = status_label(row.status, lang)
        scoring = tr(lang, "scanned") if row.scored else tr(lang, "info")
        tags: list[str] = []
        if row.experimental:
            tags.append(tr(lang, "experimental"))
        if row.supplemental:
            tags.append(tr(lang, "supplemental"))
        extra = (", " + ", ".join(tags)) if tags else ""
        title = check_title(row.id, row.title, lang)
        details = detail_text(row.id, row.details, lang)
        lines.append(f"[{marker}] {title} ({scoring}{extra}) — {details}")
    lines.append("")
    lines.append(f"{tr(lang, 'categories')}:")
    for cat in report.categories:
        value = tr(lang, "n_a") if cat.score is None else f"{cat.score}/100 ({cat.passed}/{cat.applicable})"
        lines.append(f"  {category_name(cat.category, lang)}: {value}")
    if report.next_level:
        reqs = [requirement_label(x, lang) for x in report.next_level.requirements]
        lines.append(
            f"{tr(lang, 'next')}: {tr(lang, 'level')} {report.next_level.target} "
            f"{level_name(report.next_level.target, report.next_level.name, lang)} "
            f"({report.next_level.current}/{report.next_level.needed}; {report.next_level.remaining} {tr(lang, 'more_needed')}): "
            + "; ".join(reqs)
        )
    if report.recommendations:
        lines.extend(["", f"{tr(lang, 'prioritized_recommendations')}:"])
        for rec in report.recommendations:
            title = check_title(rec.check_id, rec.title, lang)
            action = localized_report_dict(report, lang)["recommendations"][report.recommendations.index(rec)]["action"]
            lines.append(
                f"  [{impact_label(rec.impact, lang)} / {effort_label(rec.effort, lang)}] "
                f"{title}: {action}"
            )
    return "\n".join(lines) + "\n"


def render_markdown(report: ScanReport, lang: str | None = None) -> str:
    lang = normalize_language(lang or report.language)
    localized = localized_report_dict(report, lang)
    lines = [
        f"# {tr(lang, 'report_title')}",
        "",
        f"- {tr(lang, 'generated_by')}: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- {tr(lang, 'target')}: `{report.target}`",
        f"- {tr(lang, 'score')}: **{report.score}/100**",
        f"- {tr(lang, 'maturity')}: **{tr(lang, 'level')} {report.level} — {level_name(report.level, report.level_name, lang)}**",
        f"- {tr(lang, 'level_model')}: `{localized['level_model']}`",
        f"- {tr(lang, 'preset')}: `{report.preset}`",
        f"- {tr(lang, 'language')}: `{lang}`",
    ]
    if report.ai_search_score is not None:
        lines.append(
            f"- {tr(lang, 'ai_search_score')}: **{report.ai_search_score}/100** "
            f"({report.ai_search_applicable} {tr(lang, 'applicable_checks')})"
        )
    if report.config_source:
        lines.append(f"- {tr(lang, 'config')}: `{report.config_source}`")
    lines.extend([
        "",
        f"## {tr(lang, 'checks')}",
        "",
        f"| {tr(lang, 'status')} | {tr(lang, 'category')} | {tr(lang, 'check')} | {tr(lang, 'scored')} | {tr(lang, 'type')} | {tr(lang, 'result')} |",
        "|---|---|---|---:|---|---|",
    ])
    for r in report.checks:
        details = detail_text(r.id, r.details, lang).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {status_label(r.status, lang)} | {category_name(r.category, lang)} | `{r.id}` | "
            f"{tr(lang, 'yes') if r.scored else tr(lang, 'no')} | {_kind(r, lang)} | {details} |"
        )
    lines.extend(["", f"## {tr(lang, 'prioritized_recommendations')}", ""])
    if not report.recommendations:
        lines.append(tr(lang, "no_recommendations"))
    else:
        lines.extend([
            f"| {tr(lang, 'impact')} | {tr(lang, 'effort')} | {tr(lang, 'check')} | {tr(lang, 'action')} | {tr(lang, 'why')} |",
            "|---|---|---|---|---|",
        ])
        for idx, rec in enumerate(report.recommendations):
            loc = localized["recommendations"][idx]
            action = str(loc["action"]).replace("|", "\\|").replace("\n", " ")
            reason = str(loc["reason"]).replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {impact_label(rec.impact, lang)} | {effort_label(rec.effort, lang)} | `{rec.check_id}` | {action} | {reason} |"
            )
    lines.extend(["", f"## {tr(lang, 'remediation_prompts')}", ""])
    actionable = [r for r in report.checks if r.status in {"fail", "warn", "error"} and r.remediation]
    localized_checks = {x["id"]: x for x in localized["checks"]}
    if not actionable:
        lines.append(tr(lang, "no_remediation"))
    for r in actionable:
        rem = localized_checks[r.id]["remediation"]
        lines.extend([
            f"### {check_title(r.id, r.title, lang)}",
            "",
            rem["summary"],
            "",
            f"{tr(lang, 'rerun')}: `{rem['rerun_command']}`",
        ])
        if rem["references"]:
            lines.append(f"{tr(lang, 'references')}: " + ", ".join(f"<{x}>" for x in rem["references"]))
        if rem.get("agent_prompt"):
            lines.extend(["", "```text", rem["agent_prompt"], "```"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_html_body(report: ScanReport, lang: str, generated: str) -> str:
    localized = localized_report_dict(report, lang)
    rows: list[str] = []
    localized_checks = {x["id"]: x for x in localized["checks"]}
    for r in report.checks:
        loc = localized_checks[r.id]
        title = check_title(r.id, r.title, lang)
        hint = check_hint(r.id, r.title, r.category, lang)
        rows.append(
            "<tr>"
            f"<td class='{html.escape(r.status)}'>{html.escape(status_label(r.status, lang))}</td>"
            f"<td>{html.escape(category_name(r.category, lang))}</td>"
            f"<td class='check-cell'><span class='check-name'>{html.escape(title)}</span>"
            f" <span class='check-help' tabindex='0' role='img' aria-label='{html.escape(hint)}' data-tooltip='{html.escape(hint)}'>?</span>"
            f"<small><code>{html.escape(r.id)}</code></small></td>"
            f"<td>{html.escape(tr(lang, 'yes') if r.scored else tr(lang, 'no'))}</td>"
            f"<td>{html.escape(_kind(r, lang))}</td>"
            f"<td>{html.escape(str(loc['details']))}</td>"
            "</tr>"
        )
    category_cards: list[str] = []
    for cat in report.categories:
        pct = cat.score or 0
        label = tr(lang, "n_a") if cat.score is None else f"{cat.score}%"
        name = category_name(cat.category, lang)
        hint = category_hint(cat.category, lang)
        category_cards.append(
            f"<div class='card'><b>{html.escape(name)} <span class='category-help check-help' tabindex='0' role='img' aria-label='{html.escape(hint)}' data-tooltip='{html.escape(hint)}'>?</span></b>"
            f"<div class='bar'><span style='width:{pct}%'></span></div><small>{html.escape(label)}</small></div>"
        )
    recs: list[str] = []
    for idx, rec in enumerate(report.recommendations):
        loc = localized["recommendations"][idx]
        recs.append(
            f"<li><b>{html.escape(str(loc['title']))}</b> "
            f"<span class='pill'>{html.escape(str(loc['impact_label']))} {html.escape(tr(lang, 'impact_suffix'))} / "
            f"{html.escape(str(loc['effort_label']))} {html.escape(tr(lang, 'effort_suffix'))}</span>"
            f"<br>{html.escape(str(loc['action']))}<br><small>{html.escape(str(loc['reason']))}</small></li>"
        )
    remediation: list[str] = []
    for r in report.checks:
        if r.status not in {"fail", "warn", "error"} or not r.remediation:
            continue
        rem = localized_checks[r.id]["remediation"]
        refs = " ".join(f"<a href='{html.escape(u)}'>{html.escape(u)}</a>" for u in rem["references"])
        prompt = f"<pre>{html.escape(rem.get('agent_prompt') or '')}</pre>" if rem.get("agent_prompt") else ""
        remediation.append(
            f"<section><h3>{html.escape(check_title(r.id, r.title, lang))}</h3><p>{html.escape(rem['summary'])}</p>"
            f"<code>{html.escape(rem['rerun_command'])}</code><p>{refs}</p>{prompt}</section>"
        )
    next_html = ""
    if report.next_level:
        reqs = "; ".join(requirement_label(x, lang) for x in report.next_level.requirements)
        next_html = (
            f"<p><b>{html.escape(tr(lang, 'next'))}:</b> {html.escape(tr(lang, 'level'))} {report.next_level.target} — "
            f"{html.escape(level_name(report.next_level.target, report.next_level.name, lang))}; "
            f"{report.next_level.current}/{report.next_level.needed}, {report.next_level.remaining} {html.escape(tr(lang, 'more_needed'))}. "
            f"{html.escape(reqs)}</p>"
        )
    logger.debug(
        "Rendering report sections collapsed by default: language=%s recommendations=%d remediation=%d",
        lang,
        len(recs),
        len(remediation),
    )
    return (
        f"<h1>{html.escape(tr(lang, 'report_title'))}</h1>"
        f"<p class='report-generated'><small>{html.escape(tr(lang, 'generated_by'))}: {html.escape(generated)}</small></p>"
        f"<p><b>{html.escape(tr(lang, 'target'))}:</b> {html.escape(report.target)}<br>"
        f"<b>{html.escape(tr(lang, 'score'))}:</b> {report.score}/100<br>"
        + (f"<b>{html.escape(tr(lang, 'ai_search_score'))}:</b> {report.ai_search_score}/100 "
           f"({report.ai_search_applicable} {html.escape(tr(lang, 'applicable_checks'))})<br>" if report.ai_search_score is not None else "")
        + f"<b>{html.escape(tr(lang, 'level'))}:</b> {report.level} — {html.escape(level_name(report.level, report.level_name, lang))}</p>"
        f"<p><small>{html.escape(str(localized['level_model']))}</small></p>{next_html}"
        f"<h2>{html.escape(tr(lang, 'category_scores'))}</h2><div class='grid'>{''.join(category_cards)}</div>"
        f"<h2>{html.escape(tr(lang, 'checks'))}</h2><table><thead><tr>"
        f"<th>{html.escape(tr(lang, 'status'))}</th><th>{html.escape(tr(lang, 'category'))}</th>"
        f"<th>{html.escape(tr(lang, 'check'))}</th><th>{html.escape(tr(lang, 'scored'))}</th>"
        f"<th>{html.escape(tr(lang, 'type'))}</th><th>{html.escape(tr(lang, 'result'))}</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        f"<details class='report-section'><summary>{html.escape(tr(lang, 'prioritized_recommendations'))}</summary>"
        f"<ol>{''.join(recs) or '<li>' + html.escape(tr(lang, 'none')) + '</li>'}</ol></details>"
        f"<details class='report-section'><summary>{html.escape(tr(lang, 'remediation_prompts_short'))}</summary>"
        f"{''.join(remediation) or '<p>' + html.escape(tr(lang, 'no_remediation')) + '</p>'}</details>"
    )


def render_html(report: ScanReport, lang: str | None = None) -> str:
    selected = normalize_language(lang or report.language)
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    bodies = {language: _render_html_body(report, language, generated) for language in SUPPORTED_LANGUAGES}
    options = "".join(
        f"<option value='{code}'{' selected' if code == selected else ''}>{html.escape(tr(code, 'english' if code == 'en' else 'russian'))}</option>"
        for code in SUPPORTED_LANGUAGES
    )
    mains = "".join(
        f"<main data-lang='{code}'{' hidden' if code != selected else ''}>{body}</main>" for code, body in bodies.items()
    )
    return f"""<!doctype html>
<html lang='{selected}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{html.escape(tr(selected, 'report_title'))} — {html.escape(report.target)}</title>
<style>{BASE_REPORT_CSS}.toolbar{{display:flex;justify-content:flex-end;align-items:center;gap:8px;margin-bottom:16px}}.pass,.fail,.error,.warn{{font-weight:400}}code,pre{{background:#f4f4f4;padding:2px 4px}}pre{{padding:12px;overflow:auto;white-space:pre-wrap}}.bar{{height:8px;background:#eee;margin:8px 0;border-radius:8px;overflow:hidden}}.bar span{{display:block;height:100%;background:currentColor}}.pill{{font-size:.8em;border:1px solid #ccc;border-radius:20px;padding:2px 8px}}details.report-section{{margin:20px 0;border:1px solid #ddd;border-radius:8px;padding:0 12px}}details.report-section>summary{{cursor:pointer;font-weight:700;padding:12px 0}}li{{margin:12px 0}}select{{font:inherit;padding:5px 8px}}</style></head>
<body><div class='toolbar'><label for='lang'>{html.escape(tr(selected, 'language_selector'))}:</label><select id='lang'>{options}</select></div>{mains}
<script>(function(){{const s=document.getElementById('lang');function setLang(v){{document.documentElement.lang=v;document.querySelectorAll('main[data-lang]').forEach(x=>x.hidden=x.dataset.lang!==v);const label=document.querySelector('.toolbar label');label.textContent=(v==='ru'?'Язык отчёта':'Report language')+':';localStorage.setItem('agentready-report-lang',v)}};const saved=localStorage.getItem('agentready-report-lang');if(saved&&['en','ru'].includes(saved)){{s.value=saved;setLang(saved)}}s.addEventListener('change',()=>setLang(s.value));window.addEventListener('beforeprint',()=>document.querySelectorAll('details').forEach(d=>d.open=true));}})();</script></body></html>"""


def render(report: ScanReport, fmt: str, lang: str | None = None) -> str:
    lang = normalize_language(lang or report.language)
    if fmt == "json":
        return render_json(report, lang)
    if fmt in {"md", "markdown"}:
        return render_markdown(report, lang)
    if fmt == "html":
        return render_html(report, lang)
    if fmt in {"console", "text"}:
        return render_console(report, lang)
    raise ValueError(f"unknown format: {fmt}")
