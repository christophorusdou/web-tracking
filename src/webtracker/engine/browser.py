"""Browser engine using Playwright for JavaScript-heavy pages."""

from __future__ import annotations

from pathlib import Path

from webtracker.auth.cookies import cookies_as_playwright_list, load_cookies_file
from webtracker.config import ActionType, AuthType, BrowserSettings, PageAction, TrackerConfig
from webtracker.engine.base import Engine, FetchResult


class BrowserEngine(Engine):
    """Fetches pages using a headless browser (Playwright) for JS rendering."""

    def __init__(self, settings: BrowserSettings) -> None:
        self._settings = settings
        self._playwright = None
        self._contexts: dict[str, object] = {}

    def _resolve_data_dir(self, tracker: TrackerConfig) -> str:
        """Determine the user data dir for a tracker's auth config."""
        if tracker.auth and tracker.auth.type == AuthType.BROWSER_PROFILE and tracker.auth.profile:
            profile_dir = Path("./browser_profiles") / tracker.auth.profile
            profile_dir.mkdir(parents=True, exist_ok=True)
            return str(profile_dir)
        return self._settings.user_data_dir

    async def _ensure_context(self, tracker: TrackerConfig):
        """Lazy-init Playwright and get/create a cached browser context."""
        from playwright.async_api import async_playwright

        if self._playwright is None:
            self._playwright = await async_playwright().start()

        data_dir = self._resolve_data_dir(tracker)
        if data_dir not in self._contexts:
            self._contexts[data_dir] = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=data_dir,
                headless=self._settings.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
        return self._contexts[data_dir]

    async def fetch(self, tracker: TrackerConfig) -> FetchResult:
        context = await self._ensure_context(tracker)

        page = await context.new_page()
        try:
            # Load cookies if using cookie-based auth
            if tracker.auth and tracker.auth.type == AuthType.COOKIES and tracker.auth.file:
                cookies = cookies_as_playwright_list(load_cookies_file(tracker.auth.file))
                if cookies:
                    await context.add_cookies(cookies)

            await page.goto(tracker.url, timeout=self._settings.default_timeout)

            # Wait for specific element if configured
            if tracker.wait_for:
                await page.wait_for_selector(
                    tracker.wait_for.selector,
                    timeout=tracker.wait_for.timeout,
                )

            # Perform configured actions
            for action in tracker.actions:
                await _perform_action(page, action)

            html = await page.content()
            url = page.url

            return FetchResult(html=html, status_code=200, url=url)
        finally:
            await page.close()

    async def close(self) -> None:
        for context in self._contexts.values():
            try:
                await context.close()
            except Exception:
                pass
        self._contexts.clear()
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


async def _perform_action(page: object, action: PageAction) -> None:
    """Execute a page action (click, scroll, wait, type)."""
    if action.type == ActionType.CLICK:
        if action.selector:
            await page.click(action.selector)
    elif action.type == ActionType.SCROLL:
        amount = action.amount or 500
        await page.evaluate(f"window.scrollBy(0, {amount})")
    elif action.type == ActionType.WAIT:
        timeout = action.timeout or 1000
        await page.wait_for_timeout(timeout)
    elif action.type == ActionType.TYPE:
        if action.selector and action.text:
            await page.fill(action.selector, action.text)
