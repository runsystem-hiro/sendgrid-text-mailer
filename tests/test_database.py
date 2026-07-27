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
    assert len(database.recent_runs()) == 1
