"""CSS selector-based data extraction from HTML."""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from webtracker.config import ExtractConfig
from webtracker.extract.transforms import apply_transforms


def extract_fields(html: str, extracts: list[ExtractConfig]) -> dict[str, str | None]:
    """Extract all configured fields from HTML content."""
    soup = BeautifulSoup(html, "lxml")
    results: dict[str, str | None] = {}

    for ext in extracts:
        raw = _extract_single(soup, ext)
        results[ext.name] = apply_transforms(raw, ext.transform)

    return results


def _extract_single(soup: BeautifulSoup, ext: ExtractConfig) -> str | None:
    """Extract a single field value using CSS selector."""
    element = soup.select_one(ext.selector)
    if element is None:
        return None

    if ext.attribute == "text":
        return element.get_text(separator=" ")
    elif ext.attribute == "html":
        return str(element)
    elif ext.attribute == "inner_html":
        return element.decode_contents()
    else:
        # Treat as HTML attribute name
        val = element.get(ext.attribute)
        if isinstance(val, list):
            return " ".join(val)
        return val
