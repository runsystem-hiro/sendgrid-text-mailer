import sqlite3
from pathlib import Path

from sendgrid_text_mailer.database import DeliveryDatabase


def test_already_sent(tmp_path: Path) -> None:
    database = DeliveryDatabase(tmp_path / "mailer.sqlite3")
    database.start_run("run-1", "campaign-1", "send", 1)
    database.record_delivery(
        run_id="run-1",
        campaign_id="campaign-1",
        email="user@example.com",
        status="sent",
        response_status=202,
    )
    database.finish_run("run-1", sent=1, failed=0, skipped=0)
    assert database.already_sent("campaign-1") == {"user@example.com"}
    runs = database.recent_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "completed"


def test_already_sent_ignores_legacy_test_delivery_with_a_production_campaign_id(
    tmp_path: Path,
) -> None:
    database = DeliveryDatabase(tmp_path / "mailer.sqlite3")
    database.start_run("test-run", "campaign-1", "test", 1)
    database.record_delivery(
        run_id="test-run",
        campaign_id="campaign-1",
        email="test@example.com",
        status="sent",
        response_status=202,
    )
    database.finish_run("test-run", sent=1, failed=0, skipped=0)

    assert database.already_sent("campaign-1") == set()


def test_recent_runs_filters_a_campaign_and_its_test_runs(tmp_path: Path) -> None:
    database = DeliveryDatabase(tmp_path / "mailer.sqlite3")
    for run_id, campaign_id, mode in (
        ("send-run", "campaign-1", "send"),
        ("test-run", "test-campaign-1", "test"),
        ("other-run", "campaign-2", "send"),
    ):
        database.start_run(run_id, campaign_id, mode, 1)

    runs = database.recent_runs(campaign_id="campaign-1")

    assert {str(run["run_id"]) for run in runs} == {"send-run", "test-run"}


def test_message_id_rows_separates_send_and_test_modes(tmp_path: Path) -> None:
    database = DeliveryDatabase(tmp_path / "mailer.sqlite3")
    for run_id, campaign_id, mode, email, message_id in (
        ("send-run", "campaign-1", "send", "send@example.com", "send-message-id"),
        ("test-run", "test-campaign-1", "test", "test@example.com", "test-message-id"),
    ):
        database.start_run(run_id, campaign_id, mode, 1)
        database.record_delivery(
            run_id=run_id,
            campaign_id=campaign_id,
            email=email,
            status="sent",
            response_status=202,
            message_id=message_id,
        )
        database.finish_run(run_id, sent=1, failed=0, skipped=0)

    assert [dict(row) for row in database.message_id_rows("campaign-1", "send")] == [
        {
            "campaign_id": "campaign-1",
            "recipient_email": "send@example.com",
            "message_id": "send-message-id",
        }
    ]
    assert [dict(row) for row in database.message_id_rows("campaign-1", "test")] == [
        {
            "campaign_id": "test-campaign-1",
            "recipient_email": "test@example.com",
            "message_id": "test-message-id",
        }
    ]


def test_existing_database_is_migrated_with_run_status(tmp_path: Path) -> None:
    path = tmp_path / "mailer.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                total_count INTEGER NOT NULL,
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            INSERT INTO runs(
                run_id, campaign_id, mode, started_at, completed_at, total_count,
                sent_count, failed_count, skipped_count
            ) VALUES ('run-1', 'campaign-1', 'send', '2026-10-08T00:00:00+00:00',
                      '2026-10-08T00:01:00+00:00', 1, 1, 0, 0)
            """
        )

    run = DeliveryDatabase(path).recent_runs()[0]

    assert run["status"] == "completed"
