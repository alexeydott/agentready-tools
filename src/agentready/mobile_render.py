"""Optional Playwright-rendered mobile checks.

These checks load the page in a headless Chromium with a mobile viewport and
measure layout overflow, tap target size/spacing, and font readability at
runtime. They are only used when the caller passes ``render=True`` and the
playwright extra is installed.
"""
from __future__ import annotations

import logging
import time

from .browser_pool import BrowserPoolBoundary
from .mobile_models import MobileCheckResult
from .models import Evidence, Remediation

logger = logging.getLogger(__name__)

_GOOGLE_MOBILE = "https://developers.google.com/search/docs/appearance/mobile-friendly"
_GOOGLE_TAP = "https://developers.google.com/speed/docs/insights/SizeTapTargetsAppropriately"

_VIEWPORT_WIDTH = 360
_VIEWPORT_HEIGHT = 640


def _result(
    check_id: str,
    title: str,
    category: str,
    status: str,
    scored: bool,
    details: str,
    started: float,
    evidence: list[Evidence],
    remediation: Remediation | None = None,
) -> MobileCheckResult:
    return MobileCheckResult(
        id=check_id,
        title=title,
        category=category,
        status=status,  # type: ignore[arg-type]
        scored=scored,
        details=details,
        duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
        evidence=evidence,
        remediation=remediation,
    )


def _remediation(summary: str, command: str, references: list[str]) -> Remediation:
    return Remediation(summary=summary, rerun_command=command, references=references)


async def check_rendered_layout_overflow_async(url: str, pool: BrowserPoolBoundary) -> MobileCheckResult:
    """Measure horizontal overflow in a mobile viewport."""
    started = time.perf_counter()
    evidence: list[Evidence] = []
    try:
        async with pool.page(viewport={"width": _VIEWPORT_WIDTH, "height": _VIEWPORT_HEIGHT}) as page:
            await pool.goto(page, url, wait_until="networkidle", timeout=30000)
            metrics = await page.evaluate(
                    """() => {
                        const doc = document.documentElement;
                        return {
                            scrollWidth: doc.scrollWidth,
                            clientWidth: doc.clientWidth,
                            innerWidth: window.innerWidth,
                        };
                    }"""
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("Rendered overflow check failed for %s: %s", url, exc)
        return _result("rendered-layout-overflow", "Rendered layout overflow", "layout", "error", True, str(exc), started, evidence)
    overflow = metrics["scrollWidth"] > metrics["clientWidth"] + 1
    detail = (
        f"no horizontal overflow at {_VIEWPORT_WIDTH}px viewport (scrollWidth={metrics['scrollWidth']})"
        if not overflow
        else f"horizontal overflow at {_VIEWPORT_WIDTH}px viewport: scrollWidth={metrics['scrollWidth']} > clientWidth={metrics['clientWidth']}"
    )
    remediation = _remediation(
        "Fix content wider than the mobile viewport so no horizontal scrolling is required.",
        f"agentready mobile audit {url!r} --render",
        [_GOOGLE_MOBILE],
    ) if overflow else None
    return _result("rendered-layout-overflow", "Rendered layout overflow", "layout", "fail" if overflow else "pass", True, detail, started, evidence, remediation)


async def check_rendered_tap_targets_async(url: str, pool: BrowserPoolBoundary) -> MobileCheckResult:
    """Measure tap target size and spacing in a mobile viewport."""
    started = time.perf_counter()
    evidence: list[Evidence] = []
    try:
        async with pool.page(viewport={"width": _VIEWPORT_WIDTH, "height": _VIEWPORT_HEIGHT}) as page:
            await pool.goto(page, url, wait_until="networkidle", timeout=30000)
            metrics = await page.evaluate(
                    """() => {
                        const targets = Array.from(document.querySelectorAll('a, button, input, select, textarea, [role="button"]'))
                            .filter(el => {
                                const r = el.getBoundingClientRect();
                                const style = window.getComputedStyle(el);
                                return r.width > 0 && r.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                            });
                        let tooSmall = 0;
                        for (const el of targets) {
                            const r = el.getBoundingClientRect();
                            if (r.width < 48 || r.height < 48) tooSmall++;
                        }
                        return { total: targets.length, tooSmall };
                    }"""
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("Rendered tap target check failed for %s: %s", url, exc)
        return _result("rendered-tap-targets", "Rendered tap targets", "usability", "error", True, str(exc), started, evidence)
    if metrics["total"] == 0:
        return _result("rendered-tap-targets", "Rendered tap targets", "usability", "skip", False, "no interactive elements rendered", started, evidence)
    too_many_small = metrics["tooSmall"] > max(2, metrics["total"] * 0.1)
    detail = (
        f"{metrics['total']} tap targets, {metrics['tooSmall']} below 48px"
        if too_many_small
        else f"{metrics['total']} tap targets sized adequately"
    )
    remediation = _remediation(
        "Increase tap target size to at least 48×48 CSS px and add spacing between adjacent targets.",
        f"agentready mobile audit {url!r} --render",
        [_GOOGLE_TAP, _GOOGLE_MOBILE],
    ) if too_many_small else None
    return _result("rendered-tap-targets", "Rendered tap targets", "usability", "fail" if too_many_small else "pass", True, detail, started, evidence, remediation)


async def check_rendered_font_readability_async(url: str, pool: BrowserPoolBoundary) -> MobileCheckResult:
    """Measure base font size in a mobile viewport."""
    started = time.perf_counter()
    evidence: list[Evidence] = []
    try:
        async with pool.page(viewport={"width": _VIEWPORT_WIDTH, "height": _VIEWPORT_HEIGHT}) as page:
            await pool.goto(page, url, wait_until="networkidle", timeout=30000)
            metrics = await page.evaluate(
                    """() => {
                        const body = document.body;
                        const p = document.querySelector('p') || body;
                        const size = parseFloat(window.getComputedStyle(p).fontSize);
                        const zoomBlocked = /user-scalable=no|maximum-scale=1/.test(
                            document.querySelector('meta[name="viewport"]')?.content || ''
                        );
                        return { fontSizePx: size, zoomBlocked };
                    }"""
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("Rendered font check failed for %s: %s", url, exc)
        return _result("rendered-font-readability", "Rendered font readability", "content", "error", True, str(exc), started, evidence)
    small_font = metrics["fontSizePx"] < 16
    issues = []
    if small_font:
        issues.append(f"computed body font size {metrics['fontSizePx']:.0f}px is below 16px")
    if metrics["zoomBlocked"]:
        issues.append("viewport blocks user scaling")
    ok = not issues
    detail = "computed font size is readable and user scaling is allowed" if ok else "; ".join(issues)
    remediation = _remediation(
        "Set base font size to at least 16 CSS px and allow user scaling.",
        f"agentready mobile audit {url!r} --render",
        [_GOOGLE_MOBILE],
    ) if not ok else None
    return _result("rendered-font-readability", "Rendered font readability", "content", "pass" if ok else "fail", True, detail, started, evidence, remediation)


check_rendered_layout_overflow = check_rendered_layout_overflow_async
check_rendered_tap_targets = check_rendered_tap_targets_async
check_rendered_font_readability = check_rendered_font_readability_async


MOBILE_RENDER_CHECKS = (
    check_rendered_layout_overflow_async,
    check_rendered_tap_targets_async,
    check_rendered_font_readability_async,
)

MOBILE_RENDER_CHECKS_BY_ID = {
    "rendered-layout-overflow": check_rendered_layout_overflow_async,
    "rendered-tap-targets": check_rendered_tap_targets_async,
    "rendered-font-readability": check_rendered_font_readability_async,
}
