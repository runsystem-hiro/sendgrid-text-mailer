from pathlib import Path
from types import SimpleNamespace

import pytest

from sendgrid_text_mailer.database import DeliveryDatabase
from sendgrid_text_mailer.errors import SendInterrupted
from sendgrid_text_mailer.models import (
    AppConfig,
    Campaign,
    PreparedAttachment,
    Recipient,
    RenderedMessage,
)
from sendgrid_text_mailer.progress import DeliveryProgress
from sendgrid_text_mailer.service import PreparedCampaign, filter_send_targets, send_campaign


def test_filter_send_targets(tmp_path: Path) -> None:
    campaign = Campaign(
        campaign_id="campaign-1",
        name="Test",
        directory=tmp_path,
        recipients_file=tmp_path / "recipients.csv",
        subject_file=tmp_path / "subject.txt",
        body_file=tmp_path / "body.txt",
        unsubscribe_url="https://example.com/unsubscribe?group_id=12345",
        max_send_count=10,
        send_interval_seconds=0,
    )
    messages = [
        RenderedMessage(Recipient("sent@example.com"), "Subject", "Body"),
        RenderedMessage(Recipient("stop@example.com"), "Subject", "Body"),
        RenderedMessage(Recipient("new@example.com"), "Subject", "Body"),
    ]
    prepared = PreparedCampaign(campaign=campaign, messages=messages, attachments=())
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


def test_send_campaign_passes_prepared_attachments_to_test_and_send(
    monkeypatch, tmp_path: Path
) -> None:
    campaign = Campaign(
        campaign_id="campaign-1",
        name="Test",
        directory=tmp_path,
        recipients_file=tmp_path / "recipients.csv",
        subject_file=tmp_path / "subject.txt",
        body_file=tmp_path / "body.txt",
        unsubscribe_url="",
        max_send_count=10,
        send_interval_seconds=0,
    )
    attachment = PreparedAttachment(
        filename="guide.pdf", mime_type="application/pdf", encoded_content="cGRm"
    )
    prepared = PreparedCampaign(
        campaign=campaign,
        messages=[RenderedMessage(Recipient("source@example.com"), "Subject", "Body")],
        attachments=(attachment,),
    )
    config = AppConfig(
        api_key="test-key",
        from_email="sender@example.com",
        from_name="Example Sender",
        unsubscribe_group_id=12345,
        database_path=tmp_path / "mailer.sqlite3",
    )
    sent: list[tuple[RenderedMessage, tuple[PreparedAttachment, ...]]] = []

    class FakeGateway:
        def __init__(self, _config: AppConfig) -> None:
            pass

        def get_unsubscribed_emails(self) -> set[str]:
            return set()

        def send(
            self,
            message: RenderedMessage,
            attachments: tuple[PreparedAttachment, ...] = (),
        ) -> SimpleNamespace:
            sent.append((message, attachments))
            return SimpleNamespace(status_code=202, message_id="message-id")

    monkeypatch.setattr("sendgrid_text_mailer.service.SendGridGateway", FakeGateway)

    send_campaign(prepared, config=config, mode="test", test_address="test@example.com")
    send_campaign(prepared, config=config, mode="send")

    assert [(message.subject, attachments) for message, attachments in sent] == [
        ("[TEST] Subject", (attachment,)),
        ("Subject", (attachment,)),
    ]


def test_send_campaign_reports_progress_and_failures(monkeypatch, tmp_path: Path) -> None:
    campaign = Campaign(
        campaign_id="campaign-1",
        name="Test",
        directory=tmp_path,
        recipients_file=tmp_path / "recipients.csv",
        subject_file=tmp_path / "subject.txt",
        body_file=tmp_path / "body.txt",
        unsubscribe_url="",
        max_send_count=10,
        send_interval_seconds=0,
    )
    prepared = PreparedCampaign(
        campaign=campaign,
        messages=[
            RenderedMessage(Recipient("one@example.com"), "Subject", "Body"),
            RenderedMessage(Recipient("two@example.com"), "Subject", "Body"),
            RenderedMessage(Recipient("three@example.com"), "Subject", "Body"),
        ],
        attachments=(),
    )
    config = AppConfig(
        api_key="test-key",
        from_email="sender@example.com",
        from_name="Example Sender",
        unsubscribe_group_id=12345,
        database_path=tmp_path / "mailer.sqlite3",
    )
    calls = 0

    class FakeGateway:
        def __init__(self, _config: AppConfig) -> None:
            pass

        def get_unsubscribed_emails(self) -> set[str]:
            return set()

        def send(self, _message: RenderedMessage, _attachments: tuple[PreparedAttachment, ...]):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("temporary SendGrid failure")
            return SimpleNamespace(status_code=202, message_id="message-id")

    monkeypatch.setattr("sendgrid_text_mailer.service.SendGridGateway", FakeGateway)
    progress: list[DeliveryProgress] = []

    run_id, sent, failed, skipped = send_campaign(
        prepared,
        config=config,
        mode="send",
        progress_callback=progress.append,
    )

    assert (sent, failed, skipped) == (2, 1, 0)
    assert [(item.completed, item.event) for item in progress] == [
        (1, "progress"),
        (2, "failure"),
        (3, "complete"),
    ]
    assert DeliveryDatabase(config.database_path).recent_runs()[0]["run_id"] == run_id
    assert DeliveryDatabase(config.database_path).recent_runs()[0]["status"] == "completed"


def test_send_campaign_records_keyboard_interrupt(monkeypatch, tmp_path: Path) -> None:
    campaign = Campaign(
        campaign_id="campaign-1",
        name="Test",
        directory=tmp_path,
        recipients_file=tmp_path / "recipients.csv",
        subject_file=tmp_path / "subject.txt",
        body_file=tmp_path / "body.txt",
        unsubscribe_url="",
        max_send_count=10,
        send_interval_seconds=0,
    )
    prepared = PreparedCampaign(
        campaign=campaign,
        messages=[
            RenderedMessage(Recipient("one@example.com"), "Subject", "Body"),
            RenderedMessage(Recipient("two@example.com"), "Subject", "Body"),
        ],
        attachments=(),
    )
    config = AppConfig(
        api_key="test-key",
        from_email="sender@example.com",
        from_name="Example Sender",
        unsubscribe_group_id=12345,
        database_path=tmp_path / "mailer.sqlite3",
    )
    calls = 0

    class FakeGateway:
        def __init__(self, _config: AppConfig) -> None:
            pass

        def get_unsubscribed_emails(self) -> set[str]:
            return set()

        def send(self, _message: RenderedMessage, _attachments: tuple[PreparedAttachment, ...]):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt
            return SimpleNamespace(status_code=202, message_id="message-id")

    monkeypatch.setattr("sendgrid_text_mailer.service.SendGridGateway", FakeGateway)
    progress: list[DeliveryProgress] = []

    with pytest.raises(SendInterrupted):
        send_campaign(prepared, config=config, mode="send", progress_callback=progress.append)

    assert [(item.completed, item.event) for item in progress] == [
        (1, "progress"),
        (1, "interrupted"),
    ]
    run = DeliveryDatabase(config.database_path).recent_runs()[0]
    assert (run["status"], run["sent_count"], run["failed_count"]) == ("interrupted", 1, 0)
