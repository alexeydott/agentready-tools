"""Static mobile-friendliness checks based on HTML/CSS signals.

These checks inspect the page source without a browser engine. They detect the
viewport declaration, responsive CSS signals, and content patterns that Google
Mobile-Friendly guidance treats as core usability signals.
"""
from __future__ import annotations

import logging
import re
import time
from html.parser import HTMLParser

from .http import FetchError, HttpClient
from .mobile_models import MobileCheckResult
from .models import Evidence, Remediation

logger = logging.getLogger(__name__)

_GOOGLE_MOBILE = "https://developers.google.com/search/docs/appearance/mobile-friendly"
_GOOGLE_VIEWPORT = "https://developer.chrome.com/docs/lighthouse/best-practices/viewport"
_GOOGLE_FONT = "https://developers.google.com/speed/docs/insights/AvoidSmallFonts"
_GOOGLE_TAP = "https://developers.google.com/speed/docs/insights/SizeTapTargetsAppropriately"


class MobileHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.viewport = ""
        self.meta_robots: list[str] = []
        self.font_size_meta = ""
        self.style_blocks: list[str] = []
        self.inline_styles: list[str] = []
        self.img_tags = 0
        self.table_tags = 0
        self.fixed_width_attrs = 0
        self.input_tags = 0
        self.anchor_tags = 0
        self.button_tags = 0
        self.link_like_tags = 0
        self.base_font_px: float | None = None
        self._in_style = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_map = {key.lower(): (value or "").strip() for key, value in attrs}
        if tag == "meta":
            name = attrs_map.get("name", "").lower()
            if name == "viewport":
                self.viewport = attrs_map.get("content", "")
            elif name in {"robots", "googlebot"}:
                self.meta_robots.append(attrs_map.get("content", ""))
        elif tag == "style":
            self._in_style, self._buf = True, []
        elif tag == "img":
            self.img_tags += 1
            if attrs_map.get("width", "").isdigit():
                self.fixed_width_attrs += 1
        elif tag == "table":
            self.table_tags += 1
        elif tag == "input":
            self.input_tags += 1
            self.link_like_tags += 1
        elif tag == "a":
            self.anchor_tags += 1
            self.link_like_tags += 1
        elif tag == "button":
            self.button_tags += 1
            self.link_like_tags += 1
        style = attrs_map.get("style", "")
        if style:
            self.inline_styles.append(style)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style" and self._in_style:
            self.style_blocks.append("".join(self._buf))
            self._in_style = False
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self._buf.append(data)


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


def _fetch_page(url: str, client: HttpClient) -> tuple[MobileHtmlParser | None, object, str | None]:
    response = client.get(url)
    if response.status_code != 200:
        return None, response, f"HTTP {response.status_code}"
    if response.content_type not in {"text/html", "application/xhtml+xml"}:
        return None, response, f"expected HTML content type, got {response.content_type or 'missing'}"
    parser = MobileHtmlParser()
    parser.feed(response.text)
    parser.close()
    return parser, response, None


def check_viewport_meta(url: str, client: HttpClient) -> MobileCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        logger.error("Mobile viewport fetch failed: %s", exc)
        return _result("viewport-meta", "Viewport meta tag", "configuration", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect viewport meta")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("viewport-meta", "Viewport meta tag", "configuration", "error", True, error or "page parser unavailable", started, evidence)
    vp = parser.viewport.lower()
    has_device_width = "width=device-width" in vp
    has_initial_scale = "initial-scale=" in vp
    ok = has_device_width and has_initial_scale
    detail = "viewport meta declares width=device-width and initial-scale" if ok else "viewport meta missing or incomplete (need width=device-width and initial-scale)"
    remediation = _remediation(
        "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> to the page <head>.",
        f"agentready mobile audit {url!r}",
        [_GOOGLE_VIEWPORT, _GOOGLE_MOBILE],
    ) if not ok else None
    return _result("viewport-meta", "Viewport meta tag", "configuration", "pass" if ok else "fail", True, detail, started, evidence, remediation)


def check_responsive_css(url: str, client: HttpClient) -> MobileCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("responsive-css", "Responsive CSS signals", "layout", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect CSS signals")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("responsive-css", "Responsive CSS signals", "layout", "error", True, error or "page parser unavailable", started, evidence)
    css_text = " ".join(parser.style_blocks).lower()
    has_media_queries = "@media" in css_text
    has_relative_units = any(unit in css_text for unit in ("rem", "em", "%", "vw", "vh"))
    has_flex_grid = "display:flex" in css_text or "display:grid" in css_text or "flexbox" in css_text or "grid-template" in css_text
    ok = has_media_queries and (has_relative_units or has_flex_grid)
    detail = "responsive CSS signals found (media queries, relative units/flex/grid)" if ok else "no clear responsive CSS signals (media queries, relative units, flex/grid) detected"
    remediation = _remediation(
        "Use media queries, relative units (rem/em/%/vw) and flex/grid layouts instead of fixed pixel widths.",
        f"agentready mobile audit {url!r}",
        [_GOOGLE_MOBILE],
    ) if not ok else None
    return _result("responsive-css", "Responsive CSS signals", "layout", "pass" if ok else "fail", True, detail, started, evidence, remediation)


def check_fixed_width_elements(url: str, client: HttpClient) -> MobileCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("fixed-width-elements", "Fixed-width elements", "layout", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect element sizing")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("fixed-width-elements", "Fixed-width elements", "layout", "error", True, error or "page parser unavailable", started, evidence)
    issues = []
    if parser.fixed_width_attrs:
        issues.append(f"{parser.fixed_width_attrs} image(s) with fixed width attributes")
    if parser.table_tags:
        issues.append(f"{parser.table_tags} table(s) detected (tables often force horizontal scrolling)")
    ok = not issues
    detail = "no obvious fixed-width/table layout issues" if ok else "; ".join(issues)
    remediation = _remediation(
        "Avoid fixed pixel widths on images and table-based layouts; use max-width:100% and responsive tables.",
        f"agentready mobile audit {url!r}",
        [_GOOGLE_MOBILE],
    ) if not ok else None
    return _result("fixed-width-elements", "Fixed-width elements", "layout", "pass" if ok else "warn", True, detail, started, evidence, remediation)


def check_touch_targets(url: str, client: HttpClient) -> MobileCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("touch-targets", "Touch target count", "usability", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect interactive elements")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("touch-targets", "Touch target count", "usability", "error", True, error or "page parser unavailable", started, evidence)
    interactive = parser.link_like_tags
    if interactive == 0:
        return _result("touch-targets", "Touch target count", "usability", "skip", False, "no interactive elements detected", started, evidence)
    dense = interactive > 60
    detail = f"{interactive} interactive elements detected; keep spacing and size adequate for touch"
    status = "warn" if dense else "pass"
    remediation = _remediation(
        "Ensure links, buttons and inputs are at least 48×48 CSS px with at least 8 px spacing between adjacent targets.",
        f"agentready mobile audit {url!r}",
        [_GOOGLE_TAP, _GOOGLE_MOBILE],
    ) if dense else None
    return _result("touch-targets", "Touch target count", "usability", status, True, detail, started, evidence, remediation)


def check_font_readability(url: str, client: HttpClient) -> MobileCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("font-readability", "Font readability", "content", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect font signals")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("font-readability", "Font readability", "content", "error", True, error or "page parser unavailable", started, evidence)
    css_text = " ".join(parser.style_blocks + parser.inline_styles).lower()
    small_font = bool(re.search(r"font-size\s*:\s*(?:[0-9]|1[0-2])(?:\.\d+)?px", css_text))
    has_zoom_block = "user-scalable=no" in parser.viewport.lower() or "maximum-scale=1" in parser.viewport.lower()
    issues = []
    if small_font:
        issues.append("inline/style font-size below 12px detected")
    if has_zoom_block:
        issues.append("viewport disables user scaling")
    ok = not issues
    detail = "font sizes appear readable and user scaling is allowed" if ok else "; ".join(issues)
    remediation = _remediation(
        "Use a base font size of at least 16 CSS px and allow user scaling (avoid user-scalable=no and maximum-scale=1).",
        f"agentready mobile audit {url!r}",
        [_GOOGLE_FONT, _GOOGLE_MOBILE],
    ) if not ok else None
    return _result("font-readability", "Font readability", "content", "pass" if ok else "fail", True, detail, started, evidence, remediation)


def check_mobile_indexability(url: str, client: HttpClient) -> MobileCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("mobile-indexability", "Mobile indexability", "configuration", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect indexability")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("mobile-indexability", "Mobile indexability", "configuration", "error", True, error or "page parser unavailable", started, evidence)
    directives = ",".join(parser.meta_robots).lower()
    blocked = any(token in directives for token in ("noindex", "none"))
    detail = "no mobile-blocking robots directives detected" if not blocked else "noindex/none directive detected"
    remediation = _remediation(
        "Remove noindex/none directives so the page can be indexed for mobile search.",
        f"agentready mobile audit {url!r}",
        [_GOOGLE_MOBILE],
    ) if blocked else None
    return _result("mobile-indexability", "Mobile indexability", "configuration", "fail" if blocked else "pass", True, detail, started, evidence, remediation)


MOBILE_STATIC_CHECKS = (
    check_viewport_meta,
    check_responsive_css,
    check_fixed_width_elements,
    check_touch_targets,
    check_font_readability,
    check_mobile_indexability,
)

MOBILE_STATIC_CHECKS_BY_ID = {
    "viewport-meta": check_viewport_meta,
    "responsive-css": check_responsive_css,
    "fixed-width-elements": check_fixed_width_elements,
    "touch-targets": check_touch_targets,
    "font-readability": check_font_readability,
    "mobile-indexability": check_mobile_indexability,
}

MOBILE_CHECK_METADATA = (
    {
        "id": "viewport-meta",
        "title": {"en": "Viewport meta tag", "ru": "Мета-тег viewport"},
        "category": {"en": "Configuration", "ru": "Конфигурация"},
        "description": {
            "en": "Checks that the page declares width=device-width and initial-scale.",
            "ru": "Проверяет наличие width=device-width и initial-scale в meta viewport.",
        },
    },
    {
        "id": "responsive-css",
        "title": {"en": "Responsive CSS signals", "ru": "Сигналы адаптивного CSS"},
        "category": {"en": "Layout", "ru": "Вёрстка"},
        "description": {
            "en": "Checks for media queries, relative units, and flex/grid layouts.",
            "ru": "Проверяет наличие медиа-запросов, относительных единиц и flex/grid.",
        },
    },
    {
        "id": "fixed-width-elements",
        "title": {"en": "Fixed-width elements", "ru": "Фиксированные элементы"},
        "category": {"en": "Layout", "ru": "Вёрстка"},
        "description": {
            "en": "Detects fixed pixel widths and table layouts that force horizontal scrolling.",
            "ru": "Обнаруживает фиксированную ширину в px и табличную вёрстку, вызывающую горизонтальную прокрутку.",
        },
    },
    {
        "id": "touch-targets",
        "title": {"en": "Touch target count", "ru": "Количество интерактивных элементов"},
        "category": {"en": "Usability", "ru": "Удобство"},
        "description": {
            "en": "Counts interactive elements and flags excessive density that harms touch accuracy.",
            "ru": "Считает интерактивные элементы и отмечает чрезмерную плотность, мешающую точному касанию.",
        },
    },
    {
        "id": "font-readability",
        "title": {"en": "Font readability", "ru": "Читаемость шрифта"},
        "category": {"en": "Content", "ru": "Контент"},
        "description": {
            "en": "Checks base font size and user scaling permissions for comfortable reading.",
            "ru": "Проверяет базовый размер шрифта и возможность масштабирования для удобного чтения.",
        },
    },
    {
        "id": "mobile-indexability",
        "title": {"en": "Mobile indexability", "ru": "Индексирование для мобильных"},
        "category": {"en": "Configuration", "ru": "Конфигурация"},
        "description": {
            "en": "Checks that no noindex/none directives block mobile search indexing.",
            "ru": "Проверяет отсутствие noindex/none директив, блокирующих мобильную индексацию.",
        },
    },
)
