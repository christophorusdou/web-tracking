"""Email (SMTP) notification channel."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText

from webtracker.config import EmailConfig
from webtracker.notify.base import Notifier

logger = logging.getLogger(__name__)


class EmailNotifier(Notifier):
    """Send notifications via SMTP email."""

    def __init__(self, config: EmailConfig) -> None:
        self._config = config

    async def send(self, message: str, title: str = "", priority: str = "") -> bool:
        subject = title or "Web Tracker Alert"

        msg = MIMEText(message)
        msg["Subject"] = subject
        msg["From"] = self._config.from_addr
        msg["To"] = self._config.to

        try:
            await asyncio.to_thread(self._send_smtp, msg)
            logger.info("Email notification sent to %s", self._config.to)
            return True
        except Exception as e:
            logger.error("Failed to send email notification: %s", e)
            return False

    def _send_smtp(self, msg: MIMEText) -> None:
        if self._config.smtp_port == 465:
            with smtplib.SMTP_SSL(self._config.smtp_host, self._config.smtp_port, timeout=10) as server:
                server.login(self._config.username, self._config.password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self._config.username, self._config.password)
                server.send_message(msg)
