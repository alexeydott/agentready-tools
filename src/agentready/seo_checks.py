from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .http import FetchError, HttpClient
from .models import Evidence, Remediation
from .seo_models import SeoCheckResult
from .structured_data import extract_jsonld_nodes, node_types

logger = logging.getLogger(__name__)

_GOOGLE_SEO = "https://developers.google.com/search/docs/fundamentals/seo-starter-guide"
_GOOGLE_SITEMAP = "https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview"
_GOOGLE_STRUCTURED = "https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data"
_YANDEX = "https://yandex.ru/support/webmaster/ru/diagnosis/recommendations"


class SeoHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.title = ""
        self.description = ""
        self.titles: list[str] = []
        self.descriptions: list[str] = []
        self.h1: list[str] = []
        self.headings: list[str] = []
        self.canonicals: list[str] = []
        self.favicons: list[str] = []
        self.meta_robots: list[str] = []
        self.x_robots = ""
        self.meta_refresh = ""
        self.hreflangs: list[tuple[str, str]] = []
        self.links: list[tuple[str, str, str]] = []  # (href, rel, anchor_text)
        self.images: list[tuple[str, str, str]] = []  # (src, alt, title)
        self.resource_urls: list[str] = []
        self.text_length = 0
        self.has_itemscope = False
        self.has_flash = False
        self.has_lorem = False
        self._title = False
        self._heading = False
        self._heading_tag = ""
        self._anchor_href = ""
        self._anchor_rel = ""
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_map = {key.lower(): (value or "").strip() for key, value in attrs}
        if tag == "html":
            self.lang = attrs_map.get("lang", "")
        elif tag == "title":
            self._title, self._buf = True, []
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading, self._heading_tag, self._buf = True, tag, []
        elif tag == "meta":
            name = attrs_map.get("name", "").lower()
            if name == "description":
                content = attrs_map.get("content", "")
                self.description = self.description or content
                self.descriptions.append(content)
            elif name in {"robots", "googlebot"}:
                self.meta_robots.append(attrs_map.get("content", ""))
            elif attrs_map.get("http-equiv", "").lower() == "refresh":
                self.meta_refresh = attrs_map.get("content", "")
        elif tag == "link":
            rels = set(attrs_map.get("rel", "").lower().split())
            href = attrs_map.get("href", "")
            if "canonical" in rels and href:
                self.canonicals.append(href)
            if "alternate" in rels and attrs_map.get("hreflang") and href:
                self.hreflangs.append((attrs_map["hreflang"].lower(), href))
            if rels & {"icon", "shortcut"} and href:
                self.favicons.append(href)
            if rels & {"stylesheet", "preload", "modulepreload"} and href:
                self.resource_urls.append(href)
        elif tag == "a":
            self._anchor_href = attrs_map.get("href", "")
            self._anchor_rel = attrs_map.get("rel", "")
            self._buf = []
        elif tag == "img":
            src = attrs_map.get("src", "") or attrs_map.get("data-src", "")
            self.images.append((src, attrs_map.get("alt", ""), attrs_map.get("title", "")))
            if src:
                self.resource_urls.append(src)
        elif tag in {"script", "source", "video", "audio", "iframe", "embed", "track"}:
            src = attrs_map.get("src", "")
            if src:
                self.resource_urls.append(src)
            if tag in {"embed", "object"}:
                self.has_flash = True
        elif tag == "object":
            self.has_flash = True
        if "itemscope" in attrs_map or any(key == "itemscope" for key, _ in attrs):
            self.has_itemscope = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title" and self._title:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self.title = self.title or text
            self.titles.append(text)
            self._title = False
            self._buf = []
        elif tag == self._heading_tag and self._heading:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self.headings.append(text)
            if tag == "h1":
                self.h1.append(text)
            self._heading = False
            self._buf = []
        elif tag == "a" and self._anchor_href:
            anchor = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self.links.append((self._anchor_href, self._anchor_rel, anchor))
            self._anchor_href = ""
            self._anchor_rel = ""
            self._buf = []

    def handle_data(self, data: str) -> None:
        self.text_length += len(data.strip())
        if "lorem ipsum" in data.lower():
            self.has_lorem = True
        if self._title or self._heading or self._anchor_href:
            self._buf.append(data)


def _remediation(summary: str, command: str, references: list[str]) -> Remediation:
    return Remediation(summary=summary, rerun_command=command, references=references)


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
) -> SeoCheckResult:
    return SeoCheckResult(
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


def _add_evidence_metrics(evidence: list[Evidence], **metrics: object) -> list[Evidence]:
    if evidence:
        attached = {key: value for key, value in metrics.items() if value is not None}
        evidence[0].metrics.update(attached)
        logger.debug("[FIX] SEO evidence locations attached: fields=%s", sorted(attached))
    return evidence


def _fetch_page(url: str, client: HttpClient) -> tuple[SeoHtmlParser | None, object, str | None]:
    response = client.get(url)
    if response.status_code != 200:
        return None, response, f"HTTP {response.status_code}"
    if response.content_type not in {"text/html", "application/xhtml+xml"}:
        return None, response, f"expected HTML content type, got {response.content_type or 'missing'}"
    parser = SeoHtmlParser()
    parser.feed(response.text)
    parser.close()
    parser.x_robots = response.headers.get("x-robots-tag", "")
    return parser, response, None


def check_page_available(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        logger.error("SEO page fetch failed: %s", exc)
        return _result("page-available", "HTML page availability", "technical", "error", True, str(exc), started, [])
    evidence = [response.evidence("fetch selected SEO page")]  # type: ignore[attr-defined]
    if error:
        return _result("page-available", "HTML page availability", "technical", "fail", True, error, started, evidence)
    return _result("page-available", "HTML page availability", "technical", "pass", True, "selected page returned HTTP 200 HTML", started, evidence)


def check_metadata(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("page-metadata", "Title, description and headings", "metadata", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect page metadata")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("page-metadata", "Title, description and headings", "metadata", "error", True, error or "page parser unavailable", started, evidence)
    _add_evidence_metrics(
        evidence,
        titles=parser.titles,
        descriptions=parser.descriptions,
        h1=parser.h1,
    )
    issues = []
    if not parser.title:
        issues.append("missing title")
    if not parser.description:
        issues.append("missing meta description")
    if len(parser.h1) != 1:
        issues.append(f"expected one H1, found {len(parser.h1)}")
    status = "fail" if issues else "pass"
    detail = "title, meta description and exactly one H1 are present" if not issues else "; ".join(issues)
    remediation = _remediation("Add a unique descriptive title, meta description and one clear H1.", f"agentready seo audit {url!r}", [_GOOGLE_SEO, _YANDEX]) if issues else None
    return _result("page-metadata", "Title, description and headings", "metadata", status, True, detail, started, evidence, remediation)


def check_indexability(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("page-indexability", "Page indexability directives", "indexability", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect indexability directives")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("page-indexability", "Page indexability directives", "indexability", "error", True, error or "page parser unavailable", started, evidence)
    directives = ",".join(parser.meta_robots + [parser.x_robots]).lower()
    blocked = any(token in directives for token in ("noindex", "none"))
    remediation = _remediation("Remove unintended noindex directives and keep the page publicly crawlable.", f"agentready seo audit {url!r}", [_GOOGLE_SEO]) if blocked else None
    return _result("page-indexability", "Page indexability directives", "indexability", "fail" if blocked else "pass", True, "noindex directive detected" if blocked else "no noindex directive detected", started, evidence, remediation)


def check_canonical(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("canonical", "Canonical URL", "indexability", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect canonical link")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("canonical", "Canonical URL", "indexability", "error", True, error or "page parser unavailable", started, evidence)
    canonical = urljoin(url, parser.canonicals[0]) if parser.canonicals else ""
    expected = urlsplit(url)._replace(fragment="", query="").geturl()
    valid = len(parser.canonicals) == 1 and canonical.rstrip("/") == expected.rstrip("/")
    remediation = _remediation("Publish one canonical link matching the selected public URL unless a deliberate duplicate strategy applies.", f"agentready seo audit {url!r}", [_GOOGLE_SEO, _YANDEX]) if not valid else None
    return _result("canonical", "Canonical URL", "indexability", "pass" if valid else "fail", True, "one canonical matches the selected URL" if valid else "canonical is missing, duplicated or points elsewhere", started, evidence, remediation)


def check_robots_and_sitemap(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    robots_url = urljoin(origin, "/robots.txt")
    try:
        robots = client.get(robots_url)
    except FetchError as exc:
        return _result("robots-sitemap", "Robots policy and sitemap", "crawlability", "error", True, str(exc), started, [])
    evidence = [robots.evidence("fetch robots.txt")]
    lines = robots.text.splitlines()
    has_agent = any(line.strip().lower().startswith("user-agent:") for line in lines)
    sitemap_urls = [line.split(":", 1)[1].strip() for line in lines if line.lower().startswith("sitemap:")]
    candidates = sitemap_urls or [urljoin(origin, "/sitemap.xml")]
    valid_sitemap = False
    for sitemap_url in candidates[:3]:
        try:
            sitemap = client.get(urljoin(origin, sitemap_url))
            evidence.append(sitemap.evidence("fetch sitemap", preview=False))
            ET.fromstring(sitemap.body)
            valid_sitemap = sitemap.status_code == 200
            if valid_sitemap:
                break
        except (FetchError, ET.ParseError) as exc:
            logger.debug("SEO sitemap candidate rejected: url=%s error=%s", sitemap_url, exc)
    ok = robots.status_code == 200 and has_agent and valid_sitemap
    detail = "robots.txt and a valid XML sitemap are available" if ok else "robots.txt must be HTTP 200 with User-agent and a valid XML sitemap must be discoverable"
    remediation = _remediation("Publish a valid robots.txt and discoverable XML sitemap.", f"agentready seo audit {url!r}", [_GOOGLE_SITEMAP, _YANDEX]) if not ok else None
    return _result("robots-sitemap", "Robots policy and sitemap", "crawlability", "pass" if ok else "fail", True, detail, started, evidence, remediation)


def check_favicon(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
        if error or parser is None:
            return _result("favicon", "Favicon reachability", "metadata", "warn", False, error or "page unavailable", started, [])
        favicon = urljoin(url, parser.favicons[0]) if parser.favicons else urljoin(url, "/favicon.ico")
        icon = client.get(favicon)
        evidence = [icon.evidence("fetch favicon", preview=False)]
        ok = icon.status_code == 200 and bool(icon.body)
        return _result("favicon", "Favicon reachability", "metadata", "pass" if ok else "warn", False, "favicon is reachable" if ok else "favicon was not found", started, evidence)
    except (FetchError, ValueError) as exc:
        logger.warning("[FIX] Ignoring malformed favicon URL: url=%s error=%s", url, exc)
        return _result("favicon", "Favicon reachability", "metadata", "warn", False, str(exc), started, [])


def check_jsonld(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("jsonld", "JSON-LD validity and applicability", "structured-data", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect JSON-LD", preview=False)]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("jsonld", "JSON-LD validity and applicability", "structured-data", "error", True, error or "page parser unavailable", started, evidence)
    nodes, errors, block_count = extract_jsonld_nodes(response.text)  # type: ignore[attr-defined]
    if errors:
        return _result("jsonld", "JSON-LD validity and applicability", "structured-data", "fail", True, f"{len(errors)} invalid JSON-LD block(s)", started, evidence, _remediation("Fix invalid JSON-LD syntax and validate the resulting structured data.", f"agentready seo audit {url!r}", [_GOOGLE_STRUCTURED]))
    if block_count == 0:
        return _result("jsonld", "JSON-LD validity and applicability", "structured-data", "warn", False, "no JSON-LD blocks found; structured data is optional and depends on page type", started, evidence)
    types = sorted({item for node in nodes for item in node_types(node)})
    return _result("jsonld", "JSON-LD validity and applicability", "structured-data", "pass", True, f"valid JSON-LD found ({', '.join(types) or 'untyped nodes'})", started, evidence)


_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️←-⇿]")
_GOOGLE_TITLES = "https://developers.google.com/search/docs/appearance/title-link"
_GOOGLE_SNIPPETS = "https://developers.google.com/search/docs/appearance/snippet"
_GOOGLE_IMAGES = "https://developers.google.com/search/docs/appearance/google-images"
_GOOGLE_HREFLANG = "https://developers.google.com/search/docs/specialty/international/localized-versions"
_GOOGLE_HTTPS = "https://developers.google.com/search/docs/crawling-indexing/https-as-ranking-signal"
_GOOGLE_CRAWL = "https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl"


def _check_title_length(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("title-length", "Title length", "metadata", "error", True, str(exc), started, [])
    evidence = [response.evidence("measure title length")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("title-length", "Title length", "metadata", "error", True, error or "page parser unavailable", started, evidence)
    length = len(parser.title)
    _add_evidence_metrics(evidence, page=url, resource=url, title=parser.title, length=length)
    if not parser.title:
        return _result("title-length", "Title length", "metadata", "skip", False, "no title tag", started, evidence)
    if length < 30:
        detail = f"title is too short ({length} chars; recommended 30-60)"
        status = "warn"
    elif length > 60:
        detail = f"title is too long ({length} chars; recommended 30-60)"
        status = "warn"
    else:
        return _result("title-length", "Title length", "metadata", "pass", True, f"title length is {length} chars", started, evidence)
    remediation = _remediation("Keep the title between 30 and 60 characters so it is not truncated or too vague in search results.", f"agentready seo audit {url!r}", [_GOOGLE_TITLES])
    return _result("title-length", "Title length", "metadata", status, True, detail, started, evidence, remediation)


def _check_description_length(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("description-length", "Meta description length", "metadata", "error", True, str(exc), started, [])
    evidence = [response.evidence("measure description length")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("description-length", "Meta description length", "metadata", "error", True, error or "page parser unavailable", started, evidence)
    if not parser.description:
        return _result("description-length", "Meta description length", "metadata", "skip", False, "no meta description", started, evidence)
    length = len(parser.description)
    if length < 70:
        detail = f"meta description is too short ({length} chars; recommended 70-160)"
        status = "warn"
    elif length > 160:
        detail = f"meta description is too long ({length} chars; recommended 70-160)"
        status = "warn"
    else:
        return _result("description-length", "Meta description length", "metadata", "pass", True, f"meta description length is {length} chars", started, evidence)
    remediation = _remediation("Write a meta description between 70 and 160 characters that summarizes the page value.", f"agentready seo audit {url!r}", [_GOOGLE_SNIPPETS])
    return _result("description-length", "Meta description length", "metadata", status, True, detail, started, evidence, remediation)


def _check_multiple_metadata(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("multiple-metadata", "Duplicate metadata tags", "metadata", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect metadata tag counts")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("multiple-metadata", "Duplicate metadata tags", "metadata", "error", True, error or "page parser unavailable", started, evidence)
    issues = []
    if len(parser.titles) > 1:
        issues.append(f"{len(parser.titles)} title tags")
    if len(parser.descriptions) > 1:
        issues.append(f"{len(parser.descriptions)} meta description tags")
    ok = not issues
    detail = "exactly one title and one meta description tag" if ok else "multiple " + " and ".join(issues) + " found"
    remediation = _remediation("Keep exactly one <title> and one meta description tag; duplicates confuse search engines.", f"agentready seo audit {url!r}", [_GOOGLE_TITLES]) if not ok else None
    return _result("multiple-metadata", "Duplicate metadata tags", "metadata", "pass" if ok else "fail", True, detail, started, evidence, remediation)


def _check_metadata_collisions(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("metadata-collisions", "Metadata collisions", "metadata", "error", True, str(exc), started, [])
    evidence = [response.evidence("compare title/description/H1")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("metadata-collisions", "Metadata collisions", "metadata", "error", True, error or "page parser unavailable", started, evidence)
    issues = []
    if parser.title and parser.h1 and parser.title.strip().lower() == parser.h1[0].strip().lower():
        issues.append("title is identical to H1")
    if parser.title and parser.description and parser.title.strip().lower() == parser.description.strip().lower():
        issues.append("title is identical to meta description")
    ok = not issues
    detail = "title, H1 and description are distinct" if ok else "; ".join(issues)
    remediation = _remediation("Make title, H1 and meta description distinct: title for search snippets, H1 for the on-page heading, description as a summary.", f"agentready seo audit {url!r}", [_GOOGLE_TITLES]) if not ok else None
    return _result("metadata-collisions", "Metadata collisions", "metadata", "pass" if ok else "warn", True, detail, started, evidence, remediation)


def _check_metadata_special_chars(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("metadata-special-chars", "Emoji in metadata", "metadata", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect metadata characters")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("metadata-special-chars", "Emoji in metadata", "metadata", "error", True, error or "page parser unavailable", started, evidence)
    issues = []
    if _EMOJI_RE.search(parser.title):
        issues.append("emoji/special symbols in title")
    if _EMOJI_RE.search(parser.description):
        issues.append("emoji/special symbols in meta description")
    ok = not issues
    detail = "no emoji or unusual special characters in metadata" if ok else "; ".join(issues)
    remediation = _remediation("Remove emoji and decorative special characters from title and meta description; they can be stripped or misrendered in search results.", f"agentready seo audit {url!r}", [_GOOGLE_TITLES]) if not ok else None
    return _result("metadata-special-chars", "Emoji in metadata", "metadata", "pass" if ok else "warn", True, detail, started, evidence, remediation)


def _check_image_attributes(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("image-alt", "Image alt attributes", "content", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect image attributes")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("image-alt", "Image alt attributes", "content", "error", True, error or "page parser unavailable", started, evidence)
    if not parser.images:
        return _result("image-alt", "Image alt attributes", "content", "skip", False, "no images on the page", started, evidence)
    missing = sum(1 for src, alt, _ in parser.images if not alt)
    missing_images = [
        {
            "page": url,
            "resource": urljoin(url, src) if src else None,
            "url": urljoin(url, src) if src else None,
            "alt": alt,
            "title": title,
        }
        for src, alt, title in parser.images
        if not alt
    ]
    _add_evidence_metrics(
        evidence,
        image_count=len(parser.images),
        missing_count=missing,
        images=missing_images,
    )
    ok = missing == 0
    detail = f"all {len(parser.images)} images have alt text" if ok else f"{missing} of {len(parser.images)} images missing alt text"
    remediation = _remediation("Add descriptive alt attributes to content images; leave alt empty only for purely decorative images.", f"agentready seo audit {url!r}", [_GOOGLE_IMAGES]) if not ok else None
    return _result("image-alt", "Image alt attributes", "content", "pass" if ok else "warn", True, detail, started, evidence, remediation)


def _check_mixed_content(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("mixed-content", "Mixed HTTP/HTTPS content", "technical", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect resource schemes")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("mixed-content", "Mixed HTTP/HTTPS content", "technical", "error", True, error or "page parser unavailable", started, evidence)
    if urlsplit(url).scheme != "https":
        return _result("mixed-content", "Mixed HTTP/HTTPS content", "technical", "skip", False, "page is not served over HTTPS", started, evidence)
    insecure = [res for res in parser.resource_urls if res.startswith("http://")]
    _add_evidence_metrics(
        evidence,
        resource_count=len(parser.resource_urls),
        insecure_count=len(insecure),
        insecure_resources=insecure,
    )
    ok = not insecure
    detail = "all subresources use HTTPS" if ok else f"{len(insecure)} insecure http:// subresource(s), e.g. {insecure[0][:80]}"
    remediation = _remediation("Load all images, scripts and styles over HTTPS; browsers block or flag mixed content.", f"agentready seo audit {url!r}", [_GOOGLE_HTTPS]) if not ok else None
    return _result("mixed-content", "Mixed HTTP/HTTPS content", "technical", "pass" if ok else "fail", True, detail, started, evidence, remediation)


def _check_https_scheme(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    evidence: list[Evidence] = []
    if urlsplit(url).scheme == "https":
        return _result("https-scheme", "HTTPS scheme", "technical", "pass", True, "page is served over HTTPS", started, evidence)
    detail = "page is not served over HTTPS"
    remediation = _remediation("Serve the site over HTTPS with a valid certificate; HTTPS is a baseline security and ranking signal.", f"agentready seo audit {url!r}", [_GOOGLE_HTTPS])
    return _result("https-scheme", "HTTPS scheme", "technical", "fail", True, detail, started, evidence, remediation)


def _check_url_format(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    path = urlsplit(url).path
    issues = []
    if any(char.isupper() for char in path):
        issues.append("URL contains uppercase letters")
    if len(url) > 115:
        issues.append(f"URL is very long ({len(url)} chars)")
    if re.search(r"%[0-9A-Fa-f]{2}", path):
        issues.append("URL contains percent-encoded characters")
    ok = not issues
    detail = "URL format is clean (lowercase, reasonable length, no encoding)" if ok else "; ".join(issues)
    remediation = _remediation("Use short lowercase URLs without percent-encoding; avoid mixed case and unnecessary parameters.", f"agentready seo audit {url!r}", [_GOOGLE_CRAWL]) if not ok else None
    return _result("url-format", "URL format", "technical", "pass" if ok else "warn", True, detail, started, [], remediation)


def _check_meta_refresh(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("meta-refresh", "Meta refresh redirect", "technical", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect meta refresh")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("meta-refresh", "Meta refresh redirect", "technical", "error", True, error or "page parser unavailable", started, evidence)
    ok = not parser.meta_refresh
    detail = "no meta refresh redirect" if ok else f"meta refresh found: {parser.meta_refresh[:80]}"
    remediation = _remediation("Replace meta refresh redirects with server-side 301 redirects; meta refresh is slower and weakens link signals.", f"agentready seo audit {url!r}", [_GOOGLE_CRAWL]) if not ok else None
    return _result("meta-refresh", "Meta refresh redirect", "technical", "pass" if ok else "fail", True, detail, started, evidence, remediation)


def _check_insecure_links(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("insecure-links", "HTTPS to HTTP links", "technical", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect link schemes")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("insecure-links", "HTTPS to HTTP links", "technical", "error", True, error or "page parser unavailable", started, evidence)
    if urlsplit(url).scheme != "https":
        return _result("insecure-links", "HTTPS to HTTP links", "technical", "skip", False, "page is not served over HTTPS", started, evidence)
    insecure = [href for href, _, _ in parser.links if href.startswith("http://")]
    _add_evidence_metrics(
        evidence,
        link_count=len(parser.links),
        insecure_count=len(insecure),
        insecure_links=[
            {"url": urljoin(url, href), "rel": rel, "text": anchor}
            for href, rel, anchor in parser.links
            if href.startswith("http://")
        ],
    )
    ok = not insecure
    detail = "no HTTPS→HTTP links" if ok else f"{len(insecure)} link(s) point from HTTPS to HTTP, e.g. {insecure[0][:80]}"
    remediation = _remediation("Update links to HTTPS versions; linking from HTTPS pages to HTTP targets weakens security signals.", f"agentready seo audit {url!r}", [_GOOGLE_HTTPS]) if not ok else None
    return _result("insecure-links", "HTTPS to HTTP links", "technical", "pass" if ok else "warn", True, detail, started, evidence, remediation)


def _check_content_size(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("content-size", "Content size", "content", "error", True, str(exc), started, [])
    evidence = [response.evidence("measure content size")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("content-size", "Content size", "content", "error", True, error or "page parser unavailable", started, evidence)
    html_bytes = len(response.body)  # type: ignore[attr-defined]
    text_chars = parser.text_length
    issues = []
    if text_chars < 300:
        issues.append(f"very little text content ({text_chars} chars)")
    if html_bytes > 512 * 1024:
        issues.append(f"HTML is very large ({html_bytes // 1024} KB)")
    if html_bytes and text_chars / html_bytes < 0.05:
        issues.append(f"low text/HTML ratio ({text_chars / html_bytes:.1%})")
    ok = not issues
    detail = "content size, HTML weight and text ratio are reasonable" if ok else "; ".join(issues)
    remediation = _remediation("Publish substantive text content, keep HTML lean, and aim for a healthy text-to-markup ratio.", f"agentready seo audit {url!r}", [_GOOGLE_SEO]) if not ok else None
    return _result("content-size", "Content size", "content", "pass" if ok else "warn", True, detail, started, evidence, remediation)


def _check_response_time(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        response = client.get(url)
    except FetchError as exc:
        return _result("response-time", "Server response time", "technical", "error", True, str(exc), started, [])
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    evidence = [response.evidence("measure response time", preview=False)]
    threshold_ms = 800
    ok = elapsed_ms <= threshold_ms
    detail = f"server responded in {elapsed_ms} ms"
    if not ok:
        detail += f" (above {threshold_ms} ms)"
    remediation = _remediation("Reduce server response time below ~800 ms with caching, faster backends and CDN delivery.", f"agentready seo audit {url!r}", [_GOOGLE_SEO]) if not ok else None
    return _result("response-time", "Server response time", "technical", "pass" if ok else "warn", True, detail, started, evidence, remediation)


def _check_content_quality(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("content-quality", "Content quality signals", "content", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect content quality")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("content-quality", "Content quality signals", "content", "error", True, error or "page parser unavailable", started, evidence)
    issues = []
    if parser.has_lorem:
        issues.append("lorem ipsum placeholder text found")
    if parser.has_flash:
        issues.append("Flash content (object/embed) found")
    ok = not issues
    detail = "no placeholder text or legacy Flash content" if ok else "; ".join(issues)
    remediation = _remediation("Replace lorem ipsum placeholders with real content and remove Flash; both are unsupported quality signals.", f"agentready seo audit {url!r}", [_GOOGLE_SEO]) if not ok else None
    return _result("content-quality", "Content quality signals", "content", "pass" if ok else "fail", True, detail, started, evidence, remediation)


def _check_microdata(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("microdata", "Structured markup presence", "structured-data", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect structured markup")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("microdata", "Structured markup presence", "structured-data", "error", True, error or "page parser unavailable", started, evidence)
    nodes, _, jsonld_blocks = extract_jsonld_nodes(response.text)  # type: ignore[attr-defined]
    has_markup = parser.has_itemscope or jsonld_blocks > 0
    detail = "structured markup present (microdata itemscope and/or JSON-LD)" if has_markup else "no microdata or JSON-LD structured markup found"
    remediation = _remediation("Add Schema.org structured markup (JSON-LD preferred) describing the page entity.", f"agentready seo audit {url!r}", [_GOOGLE_STRUCTURED]) if not has_markup else None
    return _result("microdata", "Structured markup presence", "structured-data", "pass" if has_markup else "warn", False, detail, started, evidence, remediation)


_HREFLANG_CODE_RE = re.compile(r"^(x-default|[a-z]{2,3}(-[a-zA-Z0-9]{2,8})*)$")


def _check_hreflang(url: str, client: HttpClient) -> SeoCheckResult:
    started = time.perf_counter()
    try:
        parser, response, error = _fetch_page(url, client)
    except FetchError as exc:
        return _result("hreflang", "Hreflang annotations", "indexability", "error", True, str(exc), started, [])
    evidence = [response.evidence("inspect hreflang links")]  # type: ignore[attr-defined]
    if error or parser is None:
        return _result("hreflang", "Hreflang annotations", "indexability", "error", True, error or "page parser unavailable", started, evidence)
    if not parser.hreflangs:
        return _result("hreflang", "Hreflang annotations", "indexability", "skip", False, "no hreflang annotations (single-language page)", started, evidence)
    issues = []
    codes = [code for code, _ in parser.hreflangs]
    invalid = [code for code in codes if not _HREFLANG_CODE_RE.match(code)]
    if invalid:
        issues.append(f"invalid language code(s): {', '.join(invalid[:3])}")
    if len(codes) != len(set(codes)):
        issues.append("duplicate language codes")
    relative = [href for _, href in parser.hreflangs if not href.startswith("http")]
    if relative:
        issues.append(f"{len(relative)} relative hreflang link(s)")
    normalized = urlsplit(url)._replace(fragment="", query="").geturl().rstrip("/")
    if not any(urlsplit(href)._replace(fragment="", query="").geturl().rstrip("/") == normalized for _, href in parser.hreflangs):
        issues.append("no hreflang link to the current URL")
    ok = not issues
    detail = f"valid hreflang set with {len(parser.hreflangs)} annotation(s)" if ok else "; ".join(issues)
    remediation = _remediation("Fix hreflang annotations: valid ISO codes, absolute URLs, no duplicates, and a self-referencing entry.", f"agentready seo audit {url!r}", [_GOOGLE_HREFLANG]) if not ok else None
    return _result("hreflang", "Hreflang annotations", "indexability", "pass" if ok else "warn", True, detail, started, evidence, remediation)


SEO_CHECKS = (
    check_page_available,
    check_metadata,
    check_indexability,
    check_canonical,
    check_robots_and_sitemap,
    check_favicon,
    check_jsonld,
    _check_title_length,
    _check_description_length,
    _check_multiple_metadata,
    _check_metadata_collisions,
    _check_metadata_special_chars,
    _check_image_attributes,
    _check_mixed_content,
    _check_https_scheme,
    _check_url_format,
    _check_meta_refresh,
    _check_insecure_links,
    _check_content_size,
    _check_response_time,
    _check_content_quality,
    _check_microdata,
    _check_hreflang,
)
SEO_CHECKS_BY_ID = {
    "page-available": check_page_available,
    "page-metadata": check_metadata,
    "page-indexability": check_indexability,
    "canonical": check_canonical,
    "robots-sitemap": check_robots_and_sitemap,
    "favicon": check_favicon,
    "jsonld": check_jsonld,
    "title-length": _check_title_length,
    "description-length": _check_description_length,
    "multiple-metadata": _check_multiple_metadata,
    "metadata-collisions": _check_metadata_collisions,
    "metadata-special-chars": _check_metadata_special_chars,
    "image-alt": _check_image_attributes,
    "mixed-content": _check_mixed_content,
    "https-scheme": _check_https_scheme,
    "url-format": _check_url_format,
    "meta-refresh": _check_meta_refresh,
    "insecure-links": _check_insecure_links,
    "content-size": _check_content_size,
    "response-time": _check_response_time,
    "content-quality": _check_content_quality,
    "microdata": _check_microdata,
    "hreflang": _check_hreflang,
}

SEO_CHECK_METADATA = (
    {
        "id": "page-available",
        "title": {"en": "HTML page availability", "ru": "Доступность HTML-страницы"},
        "category": {"en": "Technical", "ru": "Техническая доступность"},
        "description": {
            "en": "Confirms that the selected URL returns HTTP 200 HTML.",
            "ru": "Проверяет, что выбранный URL возвращает HTML с HTTP 200.",
        },
    },
    {
        "id": "page-metadata",
        "title": {"en": "Title, description and headings", "ru": "Title, description и заголовки"},
        "category": {"en": "Metadata", "ru": "Метаданные"},
        "description": {
            "en": "Checks a unique title, meta description and exactly one H1.",
            "ru": "Проверяет уникальные title, meta description и ровно один H1.",
        },
    },
    {
        "id": "page-indexability",
        "title": {"en": "Page indexability directives", "ru": "Директивы индексирования"},
        "category": {"en": "Indexability", "ru": "Индексирование"},
        "description": {
            "en": "Detects accidental noindex directives in meta robots and X-Robots-Tag.",
            "ru": "Ищет случайные директивы noindex в meta robots и X-Robots-Tag.",
        },
    },
    {
        "id": "canonical",
        "title": {"en": "Canonical URL", "ru": "Canonical URL"},
        "category": {"en": "Indexability", "ru": "Индексирование"},
        "description": {
            "en": "Checks that exactly one canonical URL matches the audited page.",
            "ru": "Проверяет наличие одного canonical URL, соответствующего проверяемой странице.",
        },
    },
    {
        "id": "robots-sitemap",
        "title": {"en": "Robots policy and sitemap", "ru": "Robots-политика и sitemap"},
        "category": {"en": "Crawlability", "ru": "Обход краулерами"},
        "description": {
            "en": "Checks robots.txt availability, User-agent policy and discoverable XML sitemap.",
            "ru": "Проверяет robots.txt, политику User-agent и доступную XML-карту сайта.",
        },
    },
    {
        "id": "favicon",
        "title": {"en": "Favicon reachability", "ru": "Доступность favicon"},
        "category": {"en": "Metadata", "ru": "Метаданные"},
        "description": {
            "en": "Verifies that the declared or default favicon can be fetched.",
            "ru": "Проверяет доступность указанного или стандартного favicon.",
        },
    },
    {
        "id": "jsonld",
        "title": {"en": "JSON-LD validity and applicability", "ru": "Корректность и применимость JSON-LD"},
        "category": {"en": "Structured data", "ru": "Структурированные данные"},
        "description": {
            "en": "Parses JSON-LD blocks and reports syntax or applicability issues.",
            "ru": "Разбирает блоки JSON-LD и сообщает о синтаксических проблемах и применимости.",
        },
    },
    {
        "id": "title-length",
        "title": {"en": "Title length", "ru": "Длина title"},
        "category": {"en": "Metadata", "ru": "Метаданные"},
        "description": {
            "en": "Checks that the title stays within the recommended 30-60 character range.",
            "ru": "Проверяет, что длина title остаётся в рекомендуемом диапазоне 30-60 символов.",
        },
    },
    {
        "id": "description-length",
        "title": {"en": "Meta description length", "ru": "Длина meta description"},
        "category": {"en": "Metadata", "ru": "Метаданные"},
        "description": {
            "en": "Checks that the meta description stays within the recommended 70-160 character range.",
            "ru": "Проверяет, что длина meta description остаётся в рекомендуемом диапазоне 70-160 символов.",
        },
    },
    {
        "id": "multiple-metadata",
        "title": {"en": "Duplicate metadata tags", "ru": "Дубли тегов метаданных"},
        "category": {"en": "Metadata", "ru": "Метаданные"},
        "description": {
            "en": "Detects multiple title or meta description tags on one page.",
            "ru": "Обнаруживает несколько тегов title или meta description на одной странице.",
        },
    },
    {
        "id": "metadata-collisions",
        "title": {"en": "Metadata collisions", "ru": "Совпадения метаданных"},
        "category": {"en": "Metadata", "ru": "Метаданные"},
        "description": {
            "en": "Detects title identical to H1 or to the meta description.",
            "ru": "Обнаруживает совпадение title с H1 или meta description.",
        },
    },
    {
        "id": "metadata-special-chars",
        "title": {"en": "Emoji in metadata", "ru": "Эмодзи в метаданных"},
        "category": {"en": "Metadata", "ru": "Метаданные"},
        "description": {
            "en": "Detects emoji and decorative special characters in title and meta description.",
            "ru": "Обнаруживает эмодзи и декоративные спецсимволы в title и meta description.",
        },
    },
    {
        "id": "image-alt",
        "title": {"en": "Image alt attributes", "ru": "Атрибуты alt изображений"},
        "category": {"en": "Content", "ru": "Контент"},
        "description": {
            "en": "Counts images without alt text, which harms accessibility and image SEO.",
            "ru": "Считает изображения без alt-текста, что вредит доступности и SEO изображений.",
        },
    },
    {
        "id": "mixed-content",
        "title": {"en": "Mixed HTTP/HTTPS content", "ru": "Смешанный HTTP/HTTPS контент"},
        "category": {"en": "Technical", "ru": "Техническая доступность"},
        "description": {
            "en": "Detects http:// subresources loaded from an HTTPS page.",
            "ru": "Обнаруживает ресурсы http://, загружаемые со страницы HTTPS.",
        },
    },
    {
        "id": "https-scheme",
        "title": {"en": "HTTPS scheme", "ru": "Протокол HTTPS"},
        "category": {"en": "Technical", "ru": "Техническая доступность"},
        "description": {
            "en": "Checks that the page is served over HTTPS.",
            "ru": "Проверяет, что страница отдаётся по HTTPS.",
        },
    },
    {
        "id": "url-format",
        "title": {"en": "URL format", "ru": "Формат URL"},
        "category": {"en": "Technical", "ru": "Техническая доступность"},
        "description": {
            "en": "Flags uppercase letters, excessive length and percent-encoding in URLs.",
            "ru": "Отмечает заглавные буквы, избыточную длину и процентное кодирование в URL.",
        },
    },
    {
        "id": "meta-refresh",
        "title": {"en": "Meta refresh redirect", "ru": "Meta refresh редирект"},
        "category": {"en": "Technical", "ru": "Техническая доступность"},
        "description": {
            "en": "Detects meta refresh redirects, which should be server-side 301 redirects.",
            "ru": "Обнаруживает meta refresh редиректы, которые следует заменить серверным 301.",
        },
    },
    {
        "id": "insecure-links",
        "title": {"en": "HTTPS to HTTP links", "ru": "Ссылки HTTPS → HTTP"},
        "category": {"en": "Technical", "ru": "Техническая доступность"},
        "description": {
            "en": "Detects links pointing from an HTTPS page to HTTP targets.",
            "ru": "Обнаруживает ссылки со страницы HTTPS на цели по HTTP.",
        },
    },
    {
        "id": "content-size",
        "title": {"en": "Content size", "ru": "Объём контента"},
        "category": {"en": "Content", "ru": "Контент"},
        "description": {
            "en": "Checks text volume, HTML weight and the text-to-markup ratio.",
            "ru": "Проверяет объём текста, вес HTML и соотношение текста к разметке.",
        },
    },
    {
        "id": "response-time",
        "title": {"en": "Server response time", "ru": "Время ответа сервера"},
        "category": {"en": "Technical", "ru": "Техническая доступность"},
        "description": {
            "en": "Measures how long the server takes to return the page.",
            "ru": "Измеряет время ответа сервера при загрузке страницы.",
        },
    },
    {
        "id": "content-quality",
        "title": {"en": "Content quality signals", "ru": "Сигналы качества контента"},
        "category": {"en": "Content", "ru": "Контент"},
        "description": {
            "en": "Detects lorem ipsum placeholder text and legacy Flash content.",
            "ru": "Обнаруживает текст-заглушку lorem ipsum и устаревший Flash-контент.",
        },
    },
    {
        "id": "microdata",
        "title": {"en": "Structured markup presence", "ru": "Наличие микроразметки"},
        "category": {"en": "Structured data", "ru": "Структурированные данные"},
        "description": {
            "en": "Checks whether the page carries any Schema.org markup (microdata or JSON-LD).",
            "ru": "Проверяет наличие разметки Schema.org (microdata или JSON-LD) на странице.",
        },
    },
    {
        "id": "hreflang",
        "title": {"en": "Hreflang annotations", "ru": "Аннотации hreflang"},
        "category": {"en": "Indexability", "ru": "Индексирование"},
        "description": {
            "en": "Validates hreflang codes, absolute URLs, duplicates and the self-referencing entry.",
            "ru": "Проверяет коды языков hreflang, абсолютные URL, дубли и ссылку на текущую страницу.",
        },
    },
)
