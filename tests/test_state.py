"""Tests for the SQLite state store."""

import time
from pathlib import Path

import pytest

from webtracker.state.store import StateStore


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    s = StateStore(tmp_path / "test.db")
    yield s
    s.close()


class TestStateStore:
    def test_get_set_values(self, store: StateStore):
        store.set_values("tracker1", {"price": "99.99", "title": "Widget"})
        values = store.get_values("tracker1")
        assert values == {"price": "99.99", "title": "Widget"}

    def test_get_values_empty(self, store: StateStore):
        values = store.get_values("nonexistent")
        assert values == {}

    def test_update_values(self, store: StateStore):
        store.set_values("tracker1", {"price": "99.99"})
        store.set_values("tracker1", {"price": "79.99"})
        values = store.get_values("tracker1")
        assert values == {"price": "79.99"}

    def test_notification_cooldown(self, store: StateStore):
        assert not store.is_in_cooldown("t1", 0, 300)
        store.record_notification("t1", 0, "ntfy", "test message")
        assert store.is_in_cooldown("t1", 0, 300)
        assert not store.is_in_cooldown("t1", 0, 0)  # 0 cooldown = never in cooldown

    def test_error_tracking(self, store: StateStore):
        assert store.consecutive_error_count("t1") == 0
        store.record_error("t1", "Connection timeout")
        store.record_error("t1", "Connection timeout again")
        assert store.consecutive_error_count("t1") == 2

    def test_clear_errors(self, store: StateStore):
        store.record_error("t1", "error 1")
        store.record_error("t1", "error 2")
        store.clear_errors("t1")
        assert store.consecutive_error_count("t1") == 0

    def test_history(self, store: StateStore):
        store.set_values("t1", {"price": "100"})
        store.set_values("t1", {"price": "90"})
        store.set_values("t1", {"price": "80"})
        history = store.get_history("t1", field="price")
        assert len(history) == 3
        # Most recent first
        assert history[0]["value"] == "80"
        assert history[2]["value"] == "100"

    def test_notification_history(self, store: StateStore):
        store.record_notification("t1", 0, "ntfy", "msg1")
        store.record_notification("t2", 0, "telegram", "msg2")
        all_history = store.get_notification_history()
        assert len(all_history) == 2

        t1_history = store.get_notification_history(tracker_id="t1")
        assert len(t1_history) == 1
        assert t1_history[0]["channel"] == "ntfy"
