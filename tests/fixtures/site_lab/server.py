from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Self
from urllib.parse import parse_qs, urlparse

MANIFEST_PATH = Path(__file__).with_name("manifest.json")


class _SiteLabHandler(BaseHTTPRequestHandler):
    server_version = "AgentReadySiteLab/1.0"

    def log_message(self, format: str, *args: object) -> None:
        # Fixture traffic is intentionally silent unless a test adds its own logger.
        return

    @property
    def fixture(self) -> SiteLabServer:
        return self.server.fixture  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        request = urlparse(self.path)
        path = request.path
        query = parse_qs(request.query)
        self.fixture.log_request(self.command, path, query)

        if path == "/slow":
            delay = min(float(query.get("seconds", ["0.1"])[0]), 2.0)
            time.sleep(max(delay, 0.0))
            self._send_html(200, "<title>Slow page</title><p>delayed</p>")
            return
        if path in {"/redirect", "/redirect-chain-1", "/redirect-chain-2"}:
            target = {
                "/redirect": "/",
                "/redirect-chain-1": "/redirect-chain-2",
                "/redirect-chain-2": "/",
            }[path]
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()
            return
        if path in {"/redirect-loop-a", "/redirect-loop-b"}:
            target = "/redirect-loop-b" if path.endswith("a") else "/redirect-loop-a"
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()
            return
        if path == "/missing":
            self._send_html(404, "<title>Missing</title><p>not found</p>")
            return
        if path == "/gone":
            self._send_html(410, "<title>Gone</title><p>removed</p>")
            return
        if path == "/error":
            self._send_html(500, "<title>Error</title><p>server error</p>")
            return
        if path == "/robots.txt":
            self._send_text(
                200,
                "User-agent: *\nDisallow: /blocked\nSitemap: "
                f"{self.fixture.base_url}/sitemap-index.xml\n",
                "text/plain",
            )
            return
        if path == "/sitemap-index.xml":
            self._send_text(
                200,
                '<?xml version="1.0"?><sitemapindex>'
                f"<sitemap><loc>{self.fixture.base_url}/sitemap-child.xml</loc></sitemap>"
                "</sitemapindex>",
                "application/xml",
            )
            return
        if path == "/sitemap-child.xml":
            self._send_text(
                200,
                '<?xml version="1.0"?><urlset>'
                f"<url><loc>{self.fixture.base_url}/</loc></url>"
                f"<url><loc>{self.fixture.base_url}/orphan</loc></url>"
                "</urlset>",
                "application/xml",
            )
            return
        if path == "/auth":
            expected = "Basic " + base64.b64encode(b"fixture:secret").decode("ascii")
            if self.headers.get("Authorization") != expected:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="site-lab"')
                self.end_headers()
                return
            self._send_html(200, "<title>Authenticated</title><p>private</p>")
            return
        if path == "/resource.css":
            self._send_text(200, "body { color: #123456; }", "text/css")
            return

        pages = {
            "/": '<title>Site Lab</title><a href="/redirect">redirect</a>'
            '<a href="/missing">missing</a><a href="/orphan">orphan</a>',
            "/foo": "<title>Foo</title><p>same path variant</p>",
            "/foo/": "<title>Foo</title><p>same path variant</p>",
            "/noindex": '<meta name="robots" content="noindex"><title>Noindex</title>',
            "/canonical": '<link rel="canonical" href="/"><title>Canonical</title>',
            "/hreflang": '<link rel="alternate" hreflang="en" href="/">'
            '<link rel="alternate" hreflang="ru" href="/ru"><title>Languages</title>',
            "/duplicate-a": "<title>Duplicate</title><p>identical content</p>",
            "/duplicate-b": "<title>Duplicate</title><p>identical content</p>",
            "/near-duplicate": "<title>Duplicate</title><p>identical content with one change</p>",
            "/orphan": "<title>Orphan</title><p>only in sitemap</p>",
            "/js-links": '<title>JS links</title><script>'
            'window.location="/orphan"</script><a href="/foo">foo</a>',
            "/mixed-content": '<title>Mixed</title><img src="http://insecure.example/image.png">',
            "/repeated-links": '<title>Repeated</title><a href="/foo">one</a>'
            '<a href="/foo">two</a><a href="/foo">three</a>',
            "/blocked": "<title>Blocked</title><p>robots disallow</p>",
        }
        if path in pages:
            body = pages[path]
            if path in {"/", "/canonical", "/noindex"}:
                body += '<link rel="stylesheet" href="/resource.css">'
            self._send_html(200, body)
            return
        self._send_html(404, "<title>Unknown</title><p>not found</p>")

    def _send_html(self, status: int, body: str) -> None:
        self._send_text(status, f"<!doctype html><html><head>{body}</head></html>", "text/html")

    def _send_text(self, status: int, body: str, content_type: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class SiteLabServer:
    """Random-port, same-origin fixture server with deterministic audit scenarios."""

    def __init__(self, request_logger: Callable[[str], None] | None = None) -> None:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _SiteLabHandler)
        self._httpd.fixture = self  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None
        self._request_logger = request_logger

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address
        return f"http://{host}:{port}"

    def start(self) -> SiteLabServer:
        if self._thread is not None:
            raise RuntimeError("site-lab server is already started")
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="agentready-site-lab",
            daemon=True,
        )
        self._thread.start()
        return self

    def close(self) -> None:
        if self._thread is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=2)
        self._thread = None

    def log_request(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        if self._request_logger is None:
            return
        query_keys = "&".join(f"{key}=<redacted>" for key in sorted(query))
        suffix = f"?{query_keys}" if query_keys else ""
        self._request_logger(f"{method} {path}{suffix}")

    def __enter__(self) -> Self:
        return self.start()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @staticmethod
    def manifest() -> dict[str, object]:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
