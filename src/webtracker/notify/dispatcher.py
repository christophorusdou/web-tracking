"""Notification dispatcher — routes messages to channels with cooldown/dedup."""

from __future__ import annotations

import asyncio
import logging

from webtracker.config import (
    ChannelConfig,
    EmailConfig,
    NotificationSettings,
    NtfyConfig,
    PushoverConfig,
    TelegramConfig,
    WebhookConfig,
)
from webtracker.notify.base import Notifier
from webtracker.notify.email import EmailNotifier
from webtracker.notify.ntfy import NtfyNotifier
from webtracker.notify.pushover import PushoverNotifier
from webtracker.notify.telegram import TelegramNotifier
from webtracker.notify.webhook import WebhookNotifier
from webtracker.state.store import StateStore

logger = logging.getLogger(__name__)


def _create_notifier(config: ChannelConfig) -> Notifier:
    """Create a notifier instance from its config."""
    if isinstance(config, NtfyConfig):
        return NtfyNotifier(config)
    if isinstance(config, PushoverConfig):
        return PushoverNotifier(config)
    if isinstance(config, TelegramConfig):
        return TelegramNotifier(config)
    if isinstance(config, EmailConfig):
        return EmailNotifier(config)
    if isinstance(config, WebhookConfig):
        return WebhookNotifier(config)
    raise ValueError(f"Unknown channel config type: {type(config)}")


class NotificationDispatcher:
    """Routes notifications to configured channels with cooldown enforcement."""

    def __init__(self, settings: NotificationSettings, store: StateStore) -> None:
        self._settings = settings
        self._store = store
        self._notifiers: dict[str, Notifier] = {}

        # Pre-create notifier instances
        for name, config in settings.channels.items():
            self._notifiers[name] = _create_notifier(config)

    async def dispatch(
        self,
        tracker_id: str,
        rule_index: int,
        message: str,
        channels: list[str] | None = None,
        priority: str | None = None,
        title: str = "",
    ) -> list[str]:
        """Send notification to specified channels (or defaults).

        Returns list of channel names that were successfully notified.
        """
        channel_names = channels or self._settings.defaults.channels
        cooldown = self._settings.defaults.cooldown

        # Check cooldown
        if self._store.is_in_cooldown(tracker_id, rule_index, cooldown):
            logger.debug(
                "Notification for %s rule %d is in cooldown, skipping",
                tracker_id,
                rule_index,
            )
            return []

        notification_title = title or f"WebTracker: {tracker_id}"

        # Resolve valid notifiers
        valid: list[tuple[str, Notifier]] = []
        for name in channel_names:
            notifier = self._notifiers.get(name)
            if notifier is None:
                logger.warning("Channel '%s' not found, skipping", name)
            else:
                valid.append((name, notifier))

        if not valid:
            return []

        # Send to all channels concurrently
        results = await asyncio.gather(
            *(n.send(message=message, title=notification_title, priority=priority or "default")
              for _, n in valid),
            return_exceptions=True,
        )

        sent_to: list[str] = []
        for (name, _), result in zip(valid, results):
            if isinstance(result, Exception):
                logger.error("Channel '%s' raised: %s", name, result)
            elif result:
                sent_to.append(name)
                self._store.record_notification(tracker_id, rule_index, name, message)

        return sent_to

    async def send_test(self, channel_name: str, message: str) -> bool:
        """Send a test message to a specific channel."""
        notifier = self._notifiers.get(channel_name)
        if notifier is None:
            logger.error("Channel '%s' not found", channel_name)
            return False
        return await notifier.send(message=message, title="WebTracker Test")

    async def notify_error(self, tracker_id: str, error: str) -> None:
        """Send an error notification if threshold is exceeded."""
        if not self._settings.defaults.on_error_notify:
            return

        error_count = self._store.consecutive_error_count(tracker_id)
        if error_count >= self._settings.defaults.error_threshold:
            msg = f"Tracker '{tracker_id}' has failed {error_count} times.\nLatest error: {error}"
            notifiers = [
                self._notifiers[name]
                for name in self._settings.defaults.channels
                if name in self._notifiers
            ]
            if notifiers:
                await asyncio.gather(
                    *(n.send(message=msg, title=f"WebTracker Error: {tracker_id}", priority="high")
                      for n in notifiers),
                    return_exceptions=True,
                )

    async def close(self) -> None:
        for notifier in self._notifiers.values():
            await notifier.close()
