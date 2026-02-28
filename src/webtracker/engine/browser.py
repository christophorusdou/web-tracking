"""Browser engine using Playwright for JavaScript-heavy pages."""

from __future__ import annotations

import json
from pathlib import Path

from webtracker.config import ActionType, AuthType, BrowserSettings, TrackerConfig
from webtracker.engine.base import Engine, FetchResult


class BrowserEngine(Engine):
    """Fetches pages using a headless browser (Playwright) for JS rendering."""

    def __init__(self, settings: BrowserSettings) -> None:
        self._settings = settings
        self._playwright = None
        self._browser = None

    async def _ensure_browser(self, tracker: TrackerConfig):
        """Lazy-init Playwright and browser with the right profile."""
        from playwright.async_api import async_playwright

        if self._playwright is None:
            self._playwright = await async_playwright().start()

        # Determine user data dir based on auth config
        user_data_dir = self._settings.user_data_dir
        if tracker.auth and tracker.auth.type == AuthType.BROWSER_PROFILE and tracker.auth.profile:
            profile_dir = Path("./browser_profiles") / tracker.auth.profile
            profile_dir.mkdir(parents=True, exist_ok=True)
            user_data_dir = str(profile_dir)

        # Use persistent context for profile-based auth
        context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=self._settings.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        return context

    async def fetch(self, tracker: TrackerConfig) -> FetchResult:
        context = await self._ensure_browser(tracker)

        try:
            page = await context.new_page()

            # Load cookies if using cookie-based auth
            if tracker.auth and tracker.auth.type == AuthType.COOKIES and tracker.auth.file:
                cookies = _load_browser_cookies(tracker.auth.file)
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

            await page.close()

            return FetchResult(html=html, status_code=200, url=url)
        finally:
            await context.close()

    async def close(self) -> None:
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


async def _perform_action(page, action) -> None:
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


def _load_browser_cookies(path: str) -> list[dict]:
    """Load cookies in Playwright format from a JSON file."""
    cookie_path = Path(path)
    if not cookie_path.exists():
        return []

    with open(cookie_path) as f:
        data = json.load(f)

    if isinstance(data, list):
        # Ensure each cookie has required fields for Playwright
        result = []
        for c in data:
            if "name" in c and "value" in c:
                cookie = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ""),
                    "path": c.get("path", "/"),
                }
                if "expires" in c:
                    cookie["expires"] = c["expires"]
                result.append(cookie)
        return result
    return []
