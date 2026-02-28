"""Pushover notification channel."""

from __future__ import annotations

import logging

import httpx

from webtracker.config import PushoverConfig
from webtracker.notify.base import Notifier

logger = logging.getLogger(__name__)

_PUSHOVER_API = "https://api.pushover.net/1/messages.json"

_PRIORITY_MAP = {
    "low": -1,
    "default": 0,
    "high": 1,
    "emergency": 2,
}


class PushoverNotifier(Notifier):
    """Send notifications via Pushover."""

    def __init__(self, config: PushoverConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def send(self, message: str, title: str = "", priority: str = "") -> bool:
        client = await self._get_client()

        prio_str = priority or "default"
        prio_val = _PRIORITY_MAP.get(prio_str, self._config.priority)

        data = {
            "token": self._config.api_token,
            "user": self._config.user_key,
            "message": message,
            "priority": prio_val,
            "sound": self._config.sound,
        }
        if title:
            data["title"] = title

        # Emergency priority requires retry and expire params
        if prio_val == 2:
            data["retry"] = 60  # retry every 60s
            data["expire"] = 3600  # expire after 1 hour

        try:
            resp = await client.post(_PUSHOVER_API, data=data)
            resp.raise_for_status()
            logger.info("Pushover notification sent")
            return True
        except httpx.HTTPError as e:
            logger.error("Failed to send Pushover notification: %s", e)
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
