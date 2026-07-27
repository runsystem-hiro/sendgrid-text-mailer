from pathlib import Path

from sendgrid_text_mailer.database import DeliveryDatabase
from sendgrid_text_mailer.models import Campaign, Recipient, RenderedMessage
from sendgrid_text_mailer.service import PreparedCampaign, filter_send_targets


def test_filter_send_targets(tmp_path: Path) -> None:
    campaign = Campaign(
        campaign_id="campaign-1",
        name="Test",
        directory=tmp_path,
        recipients_file=tmp_path / "recipients.csv",
        subject_file=tmp_path / "subject.txt",
        body_file=tmp_path / "body.txt",
        max_send_count=10,
        send_interval_seconds=0,
    )
    messages = [
        RenderedMessage(Recipient("sent@example.com"), "Subject", "Body"),
        RenderedMessage(Recipient("stop@example.com"), "Subject", "Body"),
        RenderedMessage(Recipient("new@example.com"), "Subject", "Body"),
    ]
    prepared = PreparedCampaign(campaign=campaign, messages=messages)
    database = DeliveryDatabase(tmp_path / "mailer.sqlite3")
    database.start_run("run-1", campaign.campaign_id, "send", 1)
    database.record_delivery(
        run_id="run-1",
        campaign_id=campaign.campaign_id,
        email="sent@example.com",
        status="sent",
    )
    database.finish_run("run-1", sent=1, failed=0, skipped=0)

    targets, skipped = filter_send_targets(
        prepared,
        database=database,
        unsubscribed={"stop@example.com"},
    )

    assert [item.recipient.email for item in targets] == ["new@example.com"]
    assert [status for _, status in skipped] == [
        "skipped_already_sent",
        "skipped_unsubscribed",
    ]
