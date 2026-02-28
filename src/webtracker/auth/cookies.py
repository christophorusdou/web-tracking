"""Cookie import/export utilities."""

from __future__ import annotations

import json
from pathlib import Path


def export_cookies_from_profile(profile_dir: str, output_path: str, domain: str | None = None) -> int:
    """Export cookies from a browser profile's cookie storage.

    This is a helper to convert browser profile cookies to a portable JSON file.
    Returns the number of cookies exported.
    """
    # Playwright stores cookies internally, so we use the Playwright API
    # This function is called from the CLI with a running browser context
    raise NotImplementedError("Use 'webtracker auth export-cookies' CLI command instead")


def load_cookies_file(path: str | Path) -> list[dict]:
    """Load cookies from a JSON file. Supports multiple formats."""
    path = Path(path)
    if not path.exists():
        return []

    with open(path) as f:
        data = json.load(f)

    if isinstance(data, dict):
        # Flat {name: value} format → convert to list
        return [{"name": k, "value": v, "domain": "", "path": "/"} for k, v in data.items()]
    if isinstance(data, list):
        return data
    return []


def save_cookies_file(cookies: list[dict], path: str | Path) -> None:
    """Save cookies to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(cookies, f, indent=2)
