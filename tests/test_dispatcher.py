"""Tests for the notification dispatcher and individual notification channels."""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from webtracker.config import (
    NotificationDefaults,
    NotificationSettings,
    NtfyConfig,
)
from webtracker.notify.dispatcher import NotificationDispatcher, _create_notifier
from webtracker.notify.ntfy import NtfyNotifier
from webtracker.state.store import StateStore


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    s = StateStore(tmp_path / "test.db")
    yield s
    s.close()


def _make_settings(**overrides) -> NotificationSettings:
    defaults = {
        "channels": {
            "ch1": {"type": "ntfy", "topic": "test-topic"},
            "ch2": {"type": "webhook", "url": "https://example.com/hook"},
        },
        "defaults": NotificationDefaults(
            channels=["ch1"], cooldown=300, on_error_notify=True, error_threshold=3
        ),
    }
    defaults.update(overrides)
    return NotificationSettings(**defaults)


class TestCreateNotifier:
    def test_create_ntfy(self):
        config = NtfyConfig(topic="test")
        notifier = _create_notifier(config)
        assert isinstance(notifier, NtfyNotifier)

    def test_create_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown channel config type"):
            _create_notifier("not_a_config")


class TestDispatcherCooldown:
    @pytest.mark.asyncio
    async def test_dispatch_sends_to_channels(self, store):
        settings = _make_settings()
        dispatcher = NotificationDispatcher(settings, store)

        # Mock the notifier
        mock_notifier = AsyncMock()
        mock_notifier.send.return_value = True
        dispatcher._notifiers["ch1"] = mock_notifier

        try:
            sent = await dispatcher.dispatch("t1", 0, "hello!")
            assert sent == ["ch1"]
            mock_notifier.send.assert_called_once()
        finally:
            await dispatcher.close()

    @pytest.mark.asyncio
    async def test_dispatch_respects_cooldown(self, store):
        settings = _make_settings()
        dispatcher = NotificationDispatcher(settings, store)

        mock_notifier = AsyncMock()
        mock_notifier.send.return_value = True
        dispatcher._notifiers["ch1"] = mock_notifier

        try:
            # First send succeeds
            sent1 = await dispatcher.dispatch("t1", 0, "msg1")
            assert sent1 == ["ch1"]

            # Second send within cooldown is skipped
            sent2 = await dispatcher.dispatch("t1", 0, "msg2")
            assert sent2 == []

            # Only called once
            assert mock_notifier.send.call_count == 1
        finally:
            await dispatcher.close()

    @pytest.mark.asyncio
    async def test_dispatch_zero_cooldown_always_sends(self, store):
        settings = _make_settings(
            defaults=NotificationDefaults(channels=["ch1"], cooldown=0)
        )
        dispatcher = NotificationDispatcher(settings, store)

        mock_notifier = AsyncMock()
        mock_notifier.send.return_value = True
        dispatcher._notifiers["ch1"] = mock_notifier

        try:
            await dispatcher.dispatch("t1", 0, "msg1")
            await dispatcher.dispatch("t1", 0, "msg2")
            assert mock_notifier.send.call_count == 2
        finally:
            await dispatcher.close()

    @pytest.mark.asyncio
    async def test_dispatch_unknown_channel_skipped(self, store):
        settings = _make_settings()
        dispatcher = NotificationDispatcher(settings, store)

        try:
            sent = await dispatcher.dispatch("t1", 0, "msg", channels=["nonexistent"])
            assert sent == []
        finally:
            await dispatcher.close()


class TestDispatcherConcurrency:
    @pytest.mark.asyncio
    async def test_dispatch_multiple_channels_concurrent(self, store):
        settings = _make_settings()
        dispatcher = NotificationDispatcher(settings, store)

        mock1 = AsyncMock()
        mock1.send.return_value = True
        mock2 = AsyncMock()
        mock2.send.return_value = True
        dispatcher._notifiers["ch1"] = mock1
        dispatcher._notifiers["ch2"] = mock2

        try:
            sent = await dispatcher.dispatch("t1", 0, "msg", channels=["ch1", "ch2"])
            assert set(sent) == {"ch1", "ch2"}
            mock1.send.assert_called_once()
            mock2.send.assert_called_once()
        finally:
            await dispatcher.close()

    @pytest.mark.asyncio
    async def test_dispatch_partial_failure(self, store):
        settings = _make_settings()
        dispatcher = NotificationDispatcher(settings, store)

        mock_ok = AsyncMock()
        mock_ok.send.return_value = True
        mock_fail = AsyncMock()
        mock_fail.send.side_effect = ConnectionError("failed")
        dispatcher._notifiers["ch1"] = mock_ok
        dispatcher._notifiers["ch2"] = mock_fail

        try:
            sent = await dispatcher.dispatch("t1", 0, "msg", channels=["ch1", "ch2"])
            assert sent == ["ch1"]
        finally:
            await dispatcher.close()


class TestDispatcherErrorNotification:
    @pytest.mark.asyncio
    async def test_error_notify_below_threshold(self, store):
        settings = _make_settings()
        dispatcher = NotificationDispatcher(settings, store)

        mock_notifier = AsyncMock()
        mock_notifier.send.return_value = True
        dispatcher._notifiers["ch1"] = mock_notifier

        try:
            # 2 errors, threshold is 3
            store.record_error("t1", "err1")
            store.record_error("t1", "err2")
            await dispatcher.notify_error("t1", "err2")
            mock_notifier.send.assert_not_called()
        finally:
            await dispatcher.close()

    @pytest.mark.asyncio
    async def test_error_notify_at_threshold(self, store):
        settings = _make_settings()
        dispatcher = NotificationDispatcher(settings, store)

        mock_notifier = AsyncMock()
        mock_notifier.send.return_value = True
        dispatcher._notifiers["ch1"] = mock_notifier

        try:
            store.record_error("t1", "err1")
            store.record_error("t1", "err2")
            store.record_error("t1", "err3")
            await dispatcher.notify_error("t1", "err3")
            mock_notifier.send.assert_called_once()
            call_kwargs = mock_notifier.send.call_args
            assert "failed 3 times" in call_kwargs.kwargs.get("message", call_kwargs.args[0] if call_kwargs.args else "")
        finally:
            await dispatcher.close()

    @pytest.mark.asyncio
    async def test_error_notify_cooldown_prevents_spam(self, store):
        settings = _make_settings()
        dispatcher = NotificationDispatcher(settings, store)

        mock_notifier = AsyncMock()
        mock_notifier.send.return_value = True
        dispatcher._notifiers["ch1"] = mock_notifier

        try:
            for i in range(5):
                store.record_error("t1", f"err{i}")

            # First error notify sends
            await dispatcher.notify_error("t1", "err0")
            assert mock_notifier.send.call_count == 1

            # Second call within cooldown is suppressed
            await dispatcher.notify_error("t1", "err1")
            assert mock_notifier.send.call_count == 1
        finally:
            await dispatcher.close()

    @pytest.mark.asyncio
    async def test_error_notify_disabled(self, store):
        settings = _make_settings(
            defaults=NotificationDefaults(channels=["ch1"], on_error_notify=False)
        )
        dispatcher = NotificationDispatcher(settings, store)

        mock_notifier = AsyncMock()
        dispatcher._notifiers["ch1"] = mock_notifier

        try:
            for i in range(5):
                store.record_error("t1", f"err{i}")
            await dispatcher.notify_error("t1", "err")
            mock_notifier.send.assert_not_called()
        finally:
            await dispatcher.close()


class TestSendTest:
    @pytest.mark.asyncio
    async def test_send_test_success(self, store):
        settings = _make_settings()
        dispatcher = NotificationDispatcher(settings, store)

        mock_notifier = AsyncMock()
        mock_notifier.send.return_value = True
        dispatcher._notifiers["ch1"] = mock_notifier

        try:
            result = await dispatcher.send_test("ch1", "hello")
            assert result is True
            mock_notifier.send.assert_called_once_with(
                message="hello", title="WebTracker Test"
            )
        finally:
            await dispatcher.close()

    @pytest.mark.asyncio
    async def test_send_test_unknown_channel(self, store):
        settings = _make_settings()
        dispatcher = NotificationDispatcher(settings, store)

        try:
            result = await dispatcher.send_test("nonexistent", "hello")
            assert result is False
        finally:
            await dispatcher.close()


class TestNtfyNotifier:
    @pytest.mark.asyncio
    async def test_ntfy_send_success(self):
        config = NtfyConfig(topic="test-topic", server="https://ntfy.sh")
        notifier = NtfyNotifier(config)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        notifier._client = mock_client

        try:
            result = await notifier.send(message="test", title="Alert", priority="high")
            assert result is True
            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args
            assert "test-topic" in call_kwargs.args[0]
            assert call_kwargs.kwargs["headers"]["Priority"] == "4"  # high = 4
        finally:
            await notifier.close()

    @pytest.mark.asyncio
    async def test_ntfy_send_failure(self):
        config = NtfyConfig(topic="test-topic")
        notifier = NtfyNotifier(config)

        import httpx
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.HTTPError("connection failed")
        notifier._client = mock_client

        try:
            result = await notifier.send(message="test")
            assert result is False
        finally:
            await notifier.close()


class TestStoreCleanup:
    def test_cleanup_removes_old_entries(self, store):
        # Insert old data by manipulating time
        old_time = time.time() - (100 * 86400)  # 100 days ago
        store._conn.execute(
            "INSERT INTO value_history (tracker_id, field_name, value, recorded_at) VALUES (?, ?, ?, ?)",
            ("t1", "price", "100", old_time),
        )
        store._conn.execute(
            "INSERT INTO notification_log (tracker_id, rule_index, channel, message, sent_at) VALUES (?, ?, ?, ?, ?)",
            ("t1", 0, "ntfy", "old msg", old_time),
        )
        store._conn.commit()

        # Insert recent data
        store.set_values("t1", {"price": "90"})
        store.record_notification("t1", 0, "ntfy", "new msg")

        deleted = store.cleanup(max_age_days=90)
        assert deleted == 2  # old history + old notification

        # Recent data still exists
        history = store.get_history("t1")
        assert len(history) == 1
        notifs = store.get_notification_history("t1")
        assert len(notifs) == 1

    def test_double_close_is_safe(self, store):
        store.close()
        store.close()  # Should not raise
