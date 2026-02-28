"""Tests for retry with exponential backoff."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from webtracker.config import (
    AppConfig,
    ConditionConfig,
    EngineType,
    ExtractConfig,
    GlobalSettings,
    NotificationDefaults,
    NotificationSettings,
    Operator,
    RuleConfig,
    ScheduleConfig,
    TrackerConfig,
)
from webtracker.engine.base import FetchResult
from webtracker.scheduler import TrackerRunner


def _make_config(retry_count: int = 0, retry_delay: int = 1) -> AppConfig:
    """Create a minimal AppConfig for testing."""
    return AppConfig(
        settings=GlobalSettings(state_db=":memory:"),
        notifications=NotificationSettings(
            channels={"test": {"type": "ntfy", "topic": "test"}},
            defaults=NotificationDefaults(channels=["test"]),
        ),
        trackers={
            "t1": TrackerConfig(
                name="Test",
                engine=EngineType.HTTP,
                url="https://example.com",
                schedule=ScheduleConfig(
                    interval=300,
                    retry_count=retry_count,
                    retry_delay=retry_delay,
                ),
                extract=[ExtractConfig(name="title", selector="h1")],
                rules=[RuleConfig(
                    condition=ConditionConfig(field="title", operator=Operator.EXISTS),
                    message="found",
                )],
            )
        },
    )


@pytest.fixture
def success_result():
    return FetchResult(html="<html><h1>Hello</h1></html>", status_code=200, url="https://example.com")


class TestRetry:
    @pytest.mark.asyncio
    async def test_no_retry_on_success(self, success_result):
        """Successful fetch should not retry."""
        config = _make_config(retry_count=3)
        runner = TrackerRunner(config)

        mock_engine = AsyncMock()
        mock_engine.fetch.return_value = success_result
        runner._http_engine = mock_engine

        try:
            values = await runner.run_once("t1")
            assert values["title"] is not None
            assert mock_engine.fetch.call_count == 1
        finally:
            await runner.close()

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_success(self, success_result):
        """Should retry and succeed after transient failure."""
        config = _make_config(retry_count=2, retry_delay=0)
        runner = TrackerRunner(config)

        mock_engine = AsyncMock()
        mock_engine.fetch.side_effect = [
            ConnectionError("Connection refused"),
            success_result,
        ]
        runner._http_engine = mock_engine

        try:
            values = await runner.run_once("t1")
            assert values["title"] is not None
            assert mock_engine.fetch.call_count == 2
        finally:
            await runner.close()

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        """Should raise after all retries exhausted."""
        config = _make_config(retry_count=2, retry_delay=0)
        runner = TrackerRunner(config)

        mock_engine = AsyncMock()
        mock_engine.fetch.side_effect = ConnectionError("Connection refused")
        runner._http_engine = mock_engine

        try:
            with pytest.raises(ConnectionError):
                await runner.run_once("t1")
            # 1 initial + 2 retries = 3 calls
            assert mock_engine.fetch.call_count == 3
        finally:
            await runner.close()

    @pytest.mark.asyncio
    async def test_no_retry_when_count_is_zero(self):
        """With retry_count=0, failure should raise immediately."""
        config = _make_config(retry_count=0)
        runner = TrackerRunner(config)

        mock_engine = AsyncMock()
        mock_engine.fetch.side_effect = ConnectionError("fail")
        runner._http_engine = mock_engine

        try:
            with pytest.raises(ConnectionError):
                await runner.run_once("t1")
            assert mock_engine.fetch.call_count == 1
        finally:
            await runner.close()

    def test_config_defaults(self):
        """Default retry config should be no retries."""
        config = _make_config()
        tracker = config.trackers["t1"]
        assert tracker.schedule.retry_count == 0
        assert tracker.schedule.retry_delay == 1

    def test_config_with_retry(self):
        """Retry config should be settable."""
        config = _make_config(retry_count=5, retry_delay=10)
        tracker = config.trackers["t1"]
        assert tracker.schedule.retry_count == 5
        assert tracker.schedule.retry_delay == 10
