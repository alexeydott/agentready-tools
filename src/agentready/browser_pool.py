"""Optional async Playwright pool sharing one browser process per audit run."""
from __future__ import annotations

import logging
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from .egress import EgressPolicy, EgressPolicyError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BrowserPoolConfig:
    max_contexts: int = 4
    max_pages_per_context: int = 1
    block_service_workers: bool = True

    def __post_init__(self) -> None:
        if self.max_contexts <= 0 or self.max_pages_per_context <= 0:
            raise ValueError("browser pool limits must be positive")


class BrowserPool:
    """Own browser lifecycle and enforce egress before every browser request."""

    def __init__(self, policy: EgressPolicy, *, config: BrowserPoolConfig | None = None) -> None:
        self.policy = policy
        self.config = config or BrowserPoolConfig()
        self._playwright: Any = None
        self._browser: Any = None
        self._slots = asyncio.Semaphore(self.config.max_contexts)
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        try:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("BrowserPool requires the optional browser extra (playwright)") from exc
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            await self._playwright.stop()
            self._playwright = None
            raise RuntimeError(
                "BrowserPool requires the Chromium browser binary; run "
                "'python -m playwright install chromium'"
            ) from exc
        self._started = True
        logger.info("[WP4.3] browser pool started max_contexts=%d", self.config.max_contexts)

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._browser = None
        self._playwright = None
        self._started = False

    async def __aenter__(self) -> "BrowserPool":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    @asynccontextmanager
    async def page(self, *, user_agent: str | None = None) -> AsyncIterator[Any]:
        if not self._started or self._browser is None:
            raise RuntimeError("BrowserPool must be started before acquiring a page")
        async with self._slots:
            context = await self._browser.new_context(
                user_agent=user_agent,
                service_workers="block" if self.config.block_service_workers else "allow",
            )
            await context.route("**/*", self._route_request)
            try:
                page = await context.new_page()
                yield page
            finally:
                await context.close()

    async def _route_request(self, route: Any) -> None:
        request = route.request
        try:
            self.policy.validate_browser_request(request.url, resource_type=request.resource_type)
        except EgressPolicyError:
            await route.abort("blockedbyclient")
            logger.warning("[WP4.3] blocked browser request url=%s type=%s", request.url, request.resource_type)
        else:
            await route.continue_()

    async def goto(self, page: Any, url: str, **kwargs: Any) -> Any:
        self.policy.validate_browser_request(url)
        logger.debug("[WP4.3] browser navigation url=%s", url)
        return await page.goto(url, **kwargs)
