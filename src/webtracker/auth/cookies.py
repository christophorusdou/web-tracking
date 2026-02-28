"""Cookie import/export utilities."""

from __future__ import annotations

import json
from pathlib import Path


def load_cookies_file(path: str | Path) -> list[dict]:
    """Load cookies from a JSON file. Supports both flat dict and list-of-dicts formats.

    Returns a canonical list of cookie dicts with at least 'name' and 'value'.
    """
    path = Path(path)
    if not path.exists():
        return []

    with open(path) as f:
        data = json.load(f)

    if isinstance(data, dict):
        # Flat {name: value} format
        return [{"name": k, "value": v, "domain": "", "path": "/"} for k, v in data.items()]
    if isinstance(data, list):
        return [c for c in data if "name" in c and "value" in c]
    return []


def cookies_as_httpx_dict(cookies: list[dict]) -> dict[str, str]:
    """Convert canonical cookie list to a flat {name: value} dict for httpx."""
    return {c["name"]: c["value"] for c in cookies}


def cookies_as_playwright_list(cookies: list[dict]) -> list[dict]:
    """Convert canonical cookie list to Playwright-compatible format."""
    result = []
    for c in cookies:
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


def save_cookies_file(cookies: list[dict], path: str | Path) -> None:
    """Save cookies to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(cookies, f, indent=2)
