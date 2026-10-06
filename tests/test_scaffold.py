from pathlib import Path

from sendgrid_text_mailer.scaffold import create_campaign_scaffold


def create_recipients_file(tmp_path: Path) -> Path:
    recipients_file = tmp_path / "recipients.csv"
    recipients_file.write_text("email\nuser@example.com\n", encoding="utf-8")
    return recipients_file


def test_create_campaign_defaults_to_reply_based_unsubscribe(tmp_path: Path) -> None:
    scaffold = create_campaign_scaffold(
        campaign_id="reply-unsubscribe",
        name="Reply Unsubscribe",
        recipients_file=create_recipients_file(tmp_path),
        output_dir=tmp_path / "campaign",
    )

    assert "unsubscribe_url" not in scaffold.config_file.read_text(encoding="utf-8")
    assert "本メールに「配信停止」とご返信ください。" in scaffold.body_file.read_text(
        encoding="utf-8"
    )


def test_create_campaign_includes_external_unsubscribe_url_when_requested(tmp_path: Path) -> None:
    scaffold = create_campaign_scaffold(
        campaign_id="external-unsubscribe",
        name="External Unsubscribe",
        recipients_file=create_recipients_file(tmp_path),
        unsubscribe_url="https://example.com/unsubscribe",
        output_dir=tmp_path / "campaign",
    )

    assert 'unsubscribe_url = "https://example.com/unsubscribe"' in scaffold.config_file.read_text(
        encoding="utf-8"
    )
    assert "{unsubscribe_url}" in scaffold.body_file.read_text(encoding="utf-8")
