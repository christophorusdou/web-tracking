"""Generic webhook notification channel (supports IFTTT, custom endpoints)."""

from __future__ import annotations

import logging

import httpx

from webtracker.config import WebhookConfig
from webtracker.notify.base import Notifier

logger = logging.getLogger(__name__)


class WebhookNotifier(Notifier):
    """Send notifications via generic HTTP webhook."""

    def __init__(self, config: WebhookConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def send(self, message: str, title: str = "", priority: str = "") -> bool:
        client = await self._get_client()

        payload = {
            "value1": title or "Web Tracker Alert",
            "value2": message,
            "value3": priority or "default",
        }

        headers = dict(self._config.headers)
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        try:
            resp = await client.request(
                method=self._config.method,
                url=self._config.url,
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            logger.info("Webhook notification sent to %s", self._config.url)
            return True
        except httpx.HTTPError as e:
            logger.error("Failed to send webhook notification: %s", e)
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
