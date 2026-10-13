"""SQLite persistence for runs and recipient delivery state."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    total_count INTEGER NOT NULL,
    sent_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL,
    recipient_email TEXT NOT NULL,
    status TEXT NOT NULL,
    response_status INTEGER,
    message_id TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_deliveries_campaign_email_status
ON deliveries(campaign_id, recipient_email, status);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class DeliveryDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(SCHEMA)
            self._migrate_runs_status(connection)
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _migrate_runs_status(connection: sqlite3.Connection) -> None:
        columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(runs)")}
        if "status" not in columns:
            connection.execute("ALTER TABLE runs ADD COLUMN status TEXT NOT NULL DEFAULT 'running'")
            connection.execute(
                """
                UPDATE runs
                SET status = CASE WHEN completed_at IS NULL THEN 'running' ELSE 'completed' END
                """
            )

    def already_sent(self, campaign_id: str) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT deliveries.recipient_email
                FROM deliveries
                JOIN runs ON runs.run_id = deliveries.run_id
                WHERE deliveries.campaign_id = ?
                  AND deliveries.status = 'sent'
                  AND runs.mode = 'send'
                """,
                (campaign_id,),
            )
            return {str(row["recipient_email"]) for row in rows}

    def start_run(self, run_id: str, campaign_id: str, mode: str, total_count: int) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO runs(run_id, campaign_id, mode, started_at, total_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, campaign_id, mode, now_iso(), total_count),
            )

    def record_delivery(
        self,
        *,
        run_id: str,
        campaign_id: str,
        email: str,
        status: str,
        response_status: int | None = None,
        message_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO deliveries(
                    run_id, campaign_id, recipient_email, status,
                    response_status, message_id, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    campaign_id,
                    email,
                    status,
                    response_status,
                    message_id,
                    error_message,
                    now_iso(),
                ),
            )

    def finish_run(
        self,
        run_id: str,
        *,
        sent: int,
        failed: int,
        skipped: int,
        status: str = "completed",
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE runs
                SET completed_at = ?, status = ?, sent_count = ?, failed_count = ?,
                    skipped_count = ?
                WHERE run_id = ?
                """,
                (now_iso(), status, sent, failed, skipped, run_id),
            )

    def recent_runs(
        self, limit: int = 20, *, campaign_id: str | None = None
    ) -> list[sqlite3.Row]:
        with self.connect() as connection:
            query = """
                SELECT run_id, campaign_id, mode, started_at, completed_at, status,
                       total_count, sent_count, failed_count, skipped_count
                FROM runs
            """
            parameters: tuple[str | int, ...] = ()
            if campaign_id:
                query += "WHERE campaign_id IN (?, ?)\n"
                parameters = (campaign_id, f"test-{campaign_id}")
            query += "ORDER BY started_at DESC\nLIMIT ?"
            return list(
                connection.execute(
                    query,
                    (*parameters, limit),
                )
            )

    def message_id_rows(self, campaign_id: str, mode: str) -> list[sqlite3.Row]:
        """Read successful delivery message IDs without changing delivery history."""
        if mode not in {"send", "test"}:
            raise ValueError("mode must be 'send' or 'test'")
        tracking_campaign_id = f"test-{campaign_id}" if mode == "test" else campaign_id
        database_uri = f"{self.path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(database_uri, uri=True) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            return list(
                connection.execute(
                    """
                    SELECT deliveries.campaign_id, deliveries.recipient_email, deliveries.message_id
                    FROM deliveries
                    JOIN runs ON runs.run_id = deliveries.run_id
                    WHERE deliveries.campaign_id = ?
                      AND deliveries.status = 'sent'
                      AND deliveries.message_id IS NOT NULL
                      AND runs.mode = ?
                    ORDER BY deliveries.created_at, deliveries.id
                    """,
                    (tracking_campaign_id, mode),
                )
            )
