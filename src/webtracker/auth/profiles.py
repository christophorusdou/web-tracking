"""Browser profile management for persistent authentication."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROFILES_DIR = Path("./browser_profiles")


def list_profiles() -> list[str]:
    """List all available browser profiles."""
    if not PROFILES_DIR.exists():
        return []
    return [d.name for d in PROFILES_DIR.iterdir() if d.is_dir()]


async def setup_profile(
    profile_name: str,
    start_url: str = "https://www.google.com",
) -> None:
    """Open a visible browser window for manual login.

    The user logs in manually. When they close the browser, the profile is saved.
    """
    from playwright.async_api import async_playwright

    profile_dir = PROFILES_DIR / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Opening browser for profile '%s'...", profile_name)
    logger.info("Log in to the site, then close the browser window to save.")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,  # must be visible for manual login
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(start_url)

        # Wait for user to close the browser
        try:
            await page.wait_for_event("close", timeout=0)
        except Exception:
            pass

        # Try to wait until the context is closed by the user
        while len(context.pages) > 0:
            try:
                await context.pages[0].wait_for_event("close", timeout=0)
            except Exception:
                break

        await context.close()

    logger.info("Profile '%s' saved to %s", profile_name, profile_dir)


async def export_cookies_from_profile(
    profile_name: str,
    output_path: str,
    url: str | None = None,
) -> int:
    """Export cookies from a browser profile to a JSON file."""
    from playwright.async_api import async_playwright

    profile_dir = PROFILES_DIR / profile_name
    if not profile_dir.exists():
        raise FileNotFoundError(f"Profile '{profile_name}' not found")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=True,
        )

        if url:
            page = await context.new_page()
            await page.goto(url)

        cookies = await context.cookies()
        await context.close()

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(cookies, f, indent=2)

    return len(cookies)
