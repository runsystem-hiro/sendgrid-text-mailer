from pathlib import Path

import pytest

from sendgrid_text_mailer.config import load_app_config, load_campaign
from sendgrid_text_mailer.errors import ConfigurationError


def write_campaign(tmp_path: Path, unsubscribe_url: str | None = None) -> None:
    lines = [
        'campaign_id = "test"',
        'name = "Test"',
        'recipients_file = "recipients.csv"',
    ]
    if unsubscribe_url:
        lines.append(f'unsubscribe_url = "{unsubscribe_url}"')
    (tmp_path / "campaign.toml").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def test_load_campaign_accepts_external_unsubscribe_url(tmp_path: Path) -> None:
    write_campaign(tmp_path, "https://example.com/unsubscribe?group_id=12345")

    campaign = load_campaign(tmp_path)

    assert campaign.unsubscribe_url == "https://example.com/unsubscribe?group_id=12345"


def test_load_campaign_rejects_relative_unsubscribe_url(tmp_path: Path) -> None:
    write_campaign(tmp_path, "/unsubscribe")

    with pytest.raises(ConfigurationError, match="absolute HTTP or HTTPS URL"):
        load_campaign(tmp_path)


def test_load_campaign_allows_manual_unsubscribe_handling(tmp_path: Path) -> None:
    write_campaign(tmp_path)

    campaign = load_campaign(tmp_path)

    assert campaign.unsubscribe_url == ""


def test_load_app_config_parses_reply_to_list(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENDGRID_API_KEY", "test-key")
    monkeypatch.setenv("SENDGRID_FROM_EMAIL", "sender@example.com")
    monkeypatch.setenv("SENDGRID_FROM_NAME", "Example Sender")
    monkeypatch.setenv("SENDGRID_UNSUBSCRIBE_GROUP_ID", "12345")
    monkeypatch.setenv("MAILER_DATABASE_PATH", str(tmp_path / "mailer.sqlite3"))
    monkeypatch.setenv(
        "SENDGRID_REPLY_TO_LIST", " Kurosawa@example.com , hiro@example.com ",
    )

    config = load_app_config()

    assert config is not None
    assert config.reply_to_list == ("kurosawa@example.com", "hiro@example.com")


def test_load_app_config_rejects_duplicate_reply_to_address(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENDGRID_API_KEY", "test-key")
    monkeypatch.setenv("SENDGRID_FROM_EMAIL", "sender@example.com")
    monkeypatch.setenv("SENDGRID_FROM_NAME", "Example Sender")
    monkeypatch.setenv("SENDGRID_UNSUBSCRIBE_GROUP_ID", "12345")
    monkeypatch.setenv("MAILER_DATABASE_PATH", str(tmp_path / "mailer.sqlite3"))
    monkeypatch.setenv(
        "SENDGRID_REPLY_TO_LIST", "kurosawa@example.com,KUROSAWA@example.com",
    )

    with pytest.raises(ConfigurationError, match="duplicate email address"):
        load_app_config()
