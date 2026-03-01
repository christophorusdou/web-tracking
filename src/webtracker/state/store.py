"""SQLite state store for tracking values, notification history, and errors."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


class StateStore:
    """Manages persistent state in SQLite: last values, notification cooldowns, errors."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = sqlite3.connect(
            str(self.db_path), timeout=10
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()

    def __enter__(self) -> StateStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tracker_state (
                tracker_id   TEXT PRIMARY KEY,
                values_json  TEXT NOT NULL DEFAULT '{}',
                updated_at   REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notification_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tracker_id   TEXT NOT NULL,
                rule_index   INTEGER NOT NULL,
                channel      TEXT NOT NULL,
                message      TEXT NOT NULL,
                sent_at      REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS value_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tracker_id   TEXT NOT NULL,
                field_name   TEXT NOT NULL,
                value        TEXT,
                recorded_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS error_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tracker_id   TEXT NOT NULL,
                error        TEXT NOT NULL,
                occurred_at  REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_notif_tracker_rule
                ON notification_log(tracker_id, rule_index);
            CREATE INDEX IF NOT EXISTS idx_notif_sent_at
                ON notification_log(sent_at);
            CREATE INDEX IF NOT EXISTS idx_history_tracker_field
                ON value_history(tracker_id, field_name);
            CREATE INDEX IF NOT EXISTS idx_error_tracker
                ON error_log(tracker_id);
        """)
        self._conn.commit()

    # ── Values ───────────────────────────────────────────

    def get_values(self, tracker_id: str) -> dict[str, str | None]:
        """Get the last extracted values for a tracker."""
        row = self._conn.execute(
            "SELECT values_json FROM tracker_state WHERE tracker_id = ?",
            (tracker_id,),
        ).fetchone()
        if row is None:
            return {}
        return json.loads(row["values_json"])

    def set_values(self, tracker_id: str, values: dict[str, str | None]) -> None:
        """Store extracted values for a tracker."""
        now = time.time()
        self._conn.execute(
            """INSERT INTO tracker_state (tracker_id, values_json, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(tracker_id)
               DO UPDATE SET values_json = excluded.values_json,
                             updated_at = excluded.updated_at""",
            (tracker_id, json.dumps(values), now),
        )
        # Record history for each field
        for field, value in values.items():
            self._conn.execute(
                "INSERT INTO value_history (tracker_id, field_name, value, recorded_at) VALUES (?, ?, ?, ?)",
                (tracker_id, field, str(value) if value is not None else None, now),
            )
        self._conn.commit()

    # ── Notification Cooldown ────────────────────────────

    def record_notification(
        self, tracker_id: str, rule_index: int, channel: str, message: str
    ) -> None:
        """Record that a notification was sent."""
        self._conn.execute(
            "INSERT INTO notification_log (tracker_id, rule_index, channel, message, sent_at) VALUES (?, ?, ?, ?, ?)",
            (tracker_id, rule_index, channel, message, time.time()),
        )
        self._conn.commit()

    def is_in_cooldown(self, tracker_id: str, rule_index: int, cooldown_seconds: int) -> bool:
        """Check if a notification is still in cooldown period."""
        cutoff = time.time() - cooldown_seconds
        row = self._conn.execute(
            "SELECT EXISTS(SELECT 1 FROM notification_log WHERE tracker_id = ? AND rule_index = ? AND sent_at > ?) AS in_cooldown",
            (tracker_id, rule_index, cutoff),
        ).fetchone()
        return bool(row["in_cooldown"])

    # ── Errors ───────────────────────────────────────────

    def record_error(self, tracker_id: str, error: str) -> None:
        """Record a tracker error."""
        self._conn.execute(
            "INSERT INTO error_log (tracker_id, error, occurred_at) VALUES (?, ?, ?)",
            (tracker_id, error, time.time()),
        )
        self._conn.commit()

    def consecutive_error_count(self, tracker_id: str) -> int:
        """Count consecutive errors since last successful run."""
        row = self._conn.execute(
            """SELECT COUNT(*) as cnt FROM error_log
               WHERE tracker_id = ?
                 AND occurred_at > COALESCE(
                     (SELECT MAX(updated_at) FROM tracker_state WHERE tracker_id = ?), 0
                 )""",
            (tracker_id, tracker_id),
        ).fetchone()
        return row["cnt"] if row else 0

    def clear_errors(self, tracker_id: str) -> None:
        """Clear errors for a tracker (called after successful run)."""
        self._conn.execute(
            "DELETE FROM error_log WHERE tracker_id = ?",
            (tracker_id,),
        )
        self._conn.commit()

    # ── History ──────────────────────────────────────────

    def get_history(self, tracker_id: str, field: str | None = None, limit: int = 50) -> list[dict]:
        """Get value history for a tracker."""
        if field:
            rows = self._conn.execute(
                "SELECT * FROM value_history WHERE tracker_id = ? AND field_name = ? ORDER BY recorded_at DESC LIMIT ?",
                (tracker_id, field, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM value_history WHERE tracker_id = ? ORDER BY recorded_at DESC LIMIT ?",
                (tracker_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_notification_history(self, tracker_id: str | None = None, limit: int = 50) -> list[dict]:
        """Get notification history."""
        if tracker_id:
            rows = self._conn.execute(
                "SELECT * FROM notification_log WHERE tracker_id = ? ORDER BY sent_at DESC LIMIT ?",
                (tracker_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM notification_log ORDER BY sent_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def cleanup(self, max_age_days: int = 90) -> int:
        """Delete history and notification entries older than max_age_days. Returns rows deleted."""
        if self._conn is None:
            return 0
        cutoff = time.time() - (max_age_days * 86400)
        c1 = self._conn.execute(
            "DELETE FROM value_history WHERE recorded_at < ?", (cutoff,)
        ).rowcount
        c2 = self._conn.execute(
            "DELETE FROM notification_log WHERE sent_at < ?", (cutoff,)
        ).rowcount
        c3 = self._conn.execute(
            "DELETE FROM error_log WHERE occurred_at < ?", (cutoff,)
        ).rowcount
        self._conn.commit()
        return c1 + c2 + c3

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
