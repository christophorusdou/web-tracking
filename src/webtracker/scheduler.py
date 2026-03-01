"""Scheduler — orchestrates tracker execution on configured intervals."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from datetime import time as dt_time

from webtracker.config import AppConfig, EngineType, ScheduleConfig, TrackerConfig
from webtracker.engine.base import Engine, FetchResult
from webtracker.engine.browser import BrowserEngine
from webtracker.engine.http import HttpEngine
from webtracker.extract.css import extract_fields
from webtracker.notify.dispatcher import NotificationDispatcher
from webtracker.rules.engine import evaluate_rules
from webtracker.state.store import StateStore

logger = logging.getLogger(__name__)


class TrackerRunner:
    """Runs all configured trackers on their schedules."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._store = StateStore(config.settings.state_db)
        self._dispatcher = NotificationDispatcher(config.notifications, self._store)
        self._http_engine = HttpEngine()
        self._browser_engine = BrowserEngine(config.settings.browser)
        self._running = False

    def _get_engine(self, tracker: TrackerConfig) -> Engine:
        if tracker.engine == EngineType.BROWSER:
            return self._browser_engine
        return self._http_engine

    async def _fetch_with_retry(self, engine: Engine, tracker: TrackerConfig) -> FetchResult:
        """Fetch a page with configurable retry and exponential backoff."""
        schedule = tracker.schedule
        last_error: Exception | None = None

        for attempt in range(schedule.retry_count + 1):
            try:
                timeout = self._config.settings.browser.default_timeout / 1000
                return await asyncio.wait_for(engine.fetch(tracker), timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(f"Fetch timed out after {timeout}s for '{tracker.name}'")
            except Exception as e:
                last_error = e
                if attempt < schedule.retry_count:
                    delay = schedule.retry_delay * (2 ** attempt)
                    logger.warning(
                        "Tracker '%s' fetch failed (attempt %d/%d), retrying in %ds: %s",
                        tracker.name, attempt + 1, schedule.retry_count + 1, delay, e,
                    )
                    await asyncio.sleep(delay)

        if last_error is None:
            raise RuntimeError("retry loop exited without setting last_error")
        raise last_error

    async def run_once(self, tracker_id: str) -> dict:
        """Run a single tracker check. Returns extracted values."""
        tracker = self._config.trackers[tracker_id]
        engine = self._get_engine(tracker)

        logger.info("Checking tracker '%s' (%s)", tracker_id, tracker.name)

        # Fetch page (with retry if configured)
        result = await self._fetch_with_retry(engine, tracker)
        logger.debug("Fetched %s (%d bytes)", result.url, len(result.html))

        # Extract values
        current_values = extract_fields(result.html, tracker.extract)
        logger.debug("Extracted values: %s", current_values)

        # Get previous values for comparison
        previous_values = self._store.get_values(tracker_id)

        # Evaluate rules
        triggered = evaluate_rules(tracker.rules, current_values, previous_values)

        # Send notifications for triggered rules
        for rule_index, rule, message in triggered:
            channels = rule.channels
            priority = rule.priority
            logger.info("Rule %d triggered for '%s': %s", rule_index, tracker_id, message)

            sent_to = await self._dispatcher.dispatch(
                tracker_id=tracker_id,
                rule_index=rule_index,
                message=message,
                channels=channels,
                priority=priority,
                title=tracker.name,
            )
            if sent_to:
                logger.info("Notified via: %s", ", ".join(sent_to))

        # Save current values as the new state
        self._store.set_values(tracker_id, current_values)
        self._store.clear_errors(tracker_id)

        return current_values

    async def _run_tracker_loop(self, tracker_id: str) -> None:
        """Run a single tracker in a loop with its configured interval."""
        tracker = self._config.trackers[tracker_id]
        schedule = tracker.schedule

        while self._running:
            try:
                # Check active hours
                if not _is_in_active_hours(schedule):
                    logger.debug("Tracker '%s' outside active hours, skipping", tracker_id)
                    await asyncio.sleep(60)
                    continue

                await self.run_once(tracker_id)

            except Exception as e:
                logger.error("Tracker '%s' failed: %s", tracker_id, e, exc_info=True)
                self._store.record_error(tracker_id, str(e))
                await self._dispatcher.notify_error(tracker_id, str(e))

            # Wait for next interval with jitter (clamped to at least half the interval)
            jitter = random.randint(-schedule.jitter, schedule.jitter) if schedule.jitter else 0
            wait_time = max(schedule.interval // 2, schedule.interval + jitter)
            logger.debug("Tracker '%s' sleeping %ds", tracker_id, wait_time)
            await asyncio.sleep(wait_time)

    async def run_all(self) -> None:
        """Run all trackers concurrently."""
        self._running = True
        logger.info("Starting %d tracker(s)...", len(self._config.trackers))

        tasks = []
        for tracker_id in self._config.trackers:
            task = asyncio.create_task(
                self._run_tracker_loop(tracker_id),
                name=f"tracker-{tracker_id}",
            )
            tasks.append(task)

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Shutting down trackers...")
        finally:
            await self.close()

    async def close(self) -> None:
        """Clean up all resources."""
        self._running = False
        await self._http_engine.close()
        await self._browser_engine.close()
        await self._dispatcher.close()
        self._store.close()

    def stop(self) -> None:
        """Signal all trackers to stop."""
        self._running = False


def _parse_time(s: str) -> dt_time:
    """Parse 'HH:MM' into a time object."""
    h, m = s.split(":")
    return dt_time(int(h), int(m))


# Cache parsed active hours to avoid re-parsing every loop iteration
_active_hours_cache: dict[str, tuple[dt_time, dt_time]] = {}


def _is_in_active_hours(schedule: ScheduleConfig) -> bool:
    """Check if the current time falls within the active hours window."""
    if not schedule.active_hours:
        return True

    if schedule.active_hours not in _active_hours_cache:
        parts = schedule.active_hours.split("-")
        if len(parts) != 2:
            return True
        _active_hours_cache[schedule.active_hours] = (_parse_time(parts[0]), _parse_time(parts[1]))

    start, end = _active_hours_cache[schedule.active_hours]
    now = datetime.now().time()

    if start <= end:
        return start <= now <= end
    else:
        # Wraps midnight (e.g., "22:00-06:00")
        return now >= start or now <= end
