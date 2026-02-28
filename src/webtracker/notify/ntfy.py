"""Ntfy.sh notification channel."""

from __future__ import annotations

import logging

import httpx

from webtracker.config import NtfyConfig
from webtracker.notify.base import Notifier

logger = logging.getLogger(__name__)

_PRIORITY_MAP = {
    "min": "1",
    "low": "2",
    "default": "3",
    "high": "4",
    "urgent": "5",
    "emergency": "5",
}


class NtfyNotifier(Notifier):
    """Send notifications via ntfy.sh or self-hosted ntfy server."""

    def __init__(self, config: NtfyConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def send(self, message: str, title: str = "", priority: str = "") -> bool:
        client = await self._get_client()
        url = f"{self._config.server.rstrip('/')}/{self._config.topic}"

        prio = priority or self._config.priority
        ntfy_priority = _PRIORITY_MAP.get(prio, "3")

        headers = {
            "Priority": ntfy_priority,
        }
        if title:
            headers["Title"] = title

        try:
            resp = await client.post(url, content=message, headers=headers)
            resp.raise_for_status()
            logger.info("Ntfy notification sent to topic '%s'", self._config.topic)
            return True
        except httpx.HTTPError as e:
            logger.error("Failed to send ntfy notification: %s", e)
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
