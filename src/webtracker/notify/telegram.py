"""Telegram Bot notification channel."""

from __future__ import annotations

import logging

import httpx

from webtracker.config import TelegramConfig
from webtracker.notify.base import Notifier

logger = logging.getLogger(__name__)


class TelegramNotifier(Notifier):
    """Send notifications via Telegram Bot API."""

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def send(self, message: str, title: str = "", priority: str = "") -> bool:
        client = await self._get_client()

        text = f"*{title}*\n\n{message}" if title else message
        url = f"https://api.telegram.org/bot{self._config.bot_token}/sendMessage"

        data = {
            "chat_id": self._config.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        try:
            resp = await client.post(url, json=data)
            resp.raise_for_status()
            logger.info("Telegram notification sent to chat %s", self._config.chat_id)
            return True
        except httpx.HTTPError as e:
            logger.error("Failed to send Telegram notification: %s", e)
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
