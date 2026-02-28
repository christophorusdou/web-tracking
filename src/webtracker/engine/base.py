"""Abstract base class for page-fetching engines."""

from __future__ import annotations

from abc import ABC, abstractmethod

from webtracker.config import TrackerConfig


class FetchResult:
    """Result of fetching a page."""

    def __init__(self, html: str, status_code: int = 200, url: str = "") -> None:
        self.html = html
        self.status_code = status_code
        self.url = url


class Engine(ABC):
    """Base class for page-fetching engines."""

    @abstractmethod
    async def fetch(self, tracker: TrackerConfig) -> FetchResult:
        """Fetch a page and return its HTML content."""

    async def close(self) -> None:
        """Clean up resources."""
