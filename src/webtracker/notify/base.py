"""Abstract base class for notification channels."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Notifier(ABC):
    """Base class for all notification channels."""

    @abstractmethod
    async def send(self, message: str, title: str = "", priority: str = "default") -> bool:
        """Send a notification. Returns True if successful."""

    async def close(self) -> None:
        """Clean up resources."""
