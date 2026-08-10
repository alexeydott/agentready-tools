from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import __version__
from .checks import CheckContext, run_check
from .http import FetchError, HttpClient
from .i18n import normalize_language
from .models import ScanReport, utc_now_iso
from .recommendations import generate_recommendations
from .registry import selected_checks
from .scoring import LEVEL_MODEL, ai_search_score, category_scores, maturity_level, overall_score
from .target import ensure_public_url, normalize_url, parse_target


def detect_commerce(html: str) -> list[str]:
    signals: list[str] = []
    lower = html.lower()
    patterns = {
        "schema.org Product/Offer": r'"@type"\s*:\s*"(?:product|offer)"',
        "cart/checkout link": r'href\s*=\s*["\'][^"\']*(?:cart|checkout|basket)[^"\']*["\']',
        "commerce vocabulary": r"\b(?:add to cart|buy now|checkout|shopping cart)\b",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, lower, flags=re.I):
            signals.append(label)
    return signals


def scan(
    target_url: str,
    *,
    preset: str = "all",
    only: list[str] | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    content_url: str | None = None,
    commerce_url: str | None = None,
    verify_skill_digests: bool = False,
    timeout: float = 5.0,
    verify_tls: bool = True,
    allow_private: bool = True,
    workers: int = 8,
    level_threshold: float = 0.8,
    recommendation_limit: int = 10,
    config_source: str | None = None,
    language: str = "en",
) -> ScanReport:
    started = utc_now_iso()
    language = normalize_language(language)
    target = parse_target(target_url)
    content = normalize_url(content_url) if content_url else target.url
    commerce = normalize_url(commerce_url) if commerce_url else None
    if not allow_private:
        ensure_public_url(target.url)
        if content != target.url:
            ensure_public_url(content)
        if commerce:
            ensure_public_url(commerce)
    specs = selected_checks(preset, only, include, exclude)

    with HttpClient(timeout=timeout, verify=verify_tls, allow_private=allow_private) as client:
        ctx = CheckContext(
            target=target,
            client=client,
            content_url=content,
            commerce_url=commerce,
            verify_skill_digests=verify_skill_digests,
        )
        results_by_id = {}
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 24))) as pool:
            future_map = {pool.submit(run_check, ctx, spec): spec for spec in specs}
            for future in as_completed(future_map):
                spec = future_map[future]
                results_by_id[spec.id] = future.result()
        results = [results_by_id[s.id] for s in specs]

        commerce_signals: list[str] = []
        if commerce:
            commerce_signals.append("explicit --commerce-url")
        try:
            homepage = client.get(target.url)
            if homepage.status_code == 200 and "html" in homepage.content_type:
                commerce_signals.extend(detect_commerce(homepage.text))
        except FetchError:
            pass

    score = overall_score(results)
    geo_score, geo_applicable = ai_search_score(results)
    level, level_name, next_level = maturity_level(results, threshold=level_threshold)
    recommendations = generate_recommendations(results, level, limit=recommendation_limit)
    return ScanReport(
        target=target.url,
        origin=target.origin,
        preset=preset,
        checks=results,
        score=score,
        level=level,
        level_name=level_name,
        level_model=LEVEL_MODEL.replace("80%", f"{round(level_threshold * 100)}%"),
        categories=category_scores(results),
        next_level=next_level,
        recommendations=recommendations,
        is_commerce=bool(commerce_signals),
        commerce_signals=sorted(set(commerce_signals)),
        started_at=started,
        finished_at=utc_now_iso(),
        selected_check_ids=[s.id for s in specs],
        config_source=config_source,
        language=language,
        ai_search_score=geo_score,
        ai_search_applicable=geo_applicable,
        tool_version=__version__,
    )


def compare_baseline(previous: dict, current: ScanReport) -> tuple[list[str], list[str], list[str]]:
    prev_rows = {r.get("id"): r for r in previous.get("checks", []) if isinstance(r, dict) and r.get("id")}
    cur_rows = {r.id: r for r in current.checks}
    regressions: list[str] = []
    improvements: list[str] = []
    warnings: list[str] = []
    if previous.get("target") and previous.get("target") != current.target:
        raise ValueError(f"baseline target mismatch: {previous.get('target')} != {current.target}")
    for cid, cur in cur_rows.items():
        old = prev_rows.get(cid)
        if old is None:
            if cur.status == "fail" and cur.scored:
                regressions.append(f"new failing check: {cid}")
            elif cur.status == "pass":
                improvements.append(f"new passing check: {cid}")
            continue
        old_status = old.get("status")
        if old_status == "pass" and cur.status == "fail":
            regressions.append(f"{cid}: pass -> fail")
        elif old_status == "fail" and cur.status == "pass":
            improvements.append(f"{cid}: fail -> pass")
    for cid in prev_rows.keys() - cur_rows.keys():
        warnings.append(f"check removed/not selected: {cid}")
    if previous.get("score") is not None and current.score < int(previous["score"]):
        warnings.append(f"score decreased: {previous['score']} -> {current.score}")
    if previous.get("level") is not None and current.level < int(previous["level"]):
        regressions.append(f"maturity level decreased: {previous['level']} -> {current.level}")
    prev_geo = previous.get("ai_search_score")
    if prev_geo is not None and current.ai_search_score is not None and current.ai_search_score < int(prev_geo):
        warnings.append(f"AI Search / GEO score decreased: {prev_geo} -> {current.ai_search_score}")
    return regressions, improvements, warnings
