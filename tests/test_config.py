from pathlib import Path

import pytest

from sendgrid_text_mailer.config import (
    MAX_ATTACHMENT_FILE_BYTES,
    load_app_config,
    load_campaign,
)
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


def write_pdf(path: Path, content: bytes = b"%PDF-1.7\nexample") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_load_campaign_accepts_one_or_more_pdf_attachments(tmp_path: Path) -> None:
    write_pdf(tmp_path / "attachments" / "guide.pdf")
    write_pdf(tmp_path / "attachments" / "application.PDF")
    write_campaign(tmp_path)
    with (tmp_path / "campaign.toml").open("a", encoding="utf-8") as file:
        file.write('\nattachments = ["attachments/guide.pdf", "attachments/application.PDF"]\n')

    campaign = load_campaign(tmp_path)

    assert campaign.attachment_files == (
        (tmp_path / "attachments" / "guide.pdf").resolve(),
        (tmp_path / "attachments" / "application.PDF").resolve(),
    )


@pytest.mark.parametrize(
    ("attachments", "files", "error"),
    [
        ('attachments = "attachments/guide.pdf"', {}, "must be an array"),
        ('attachments = ["attachments/guide.txt"]', {"attachments/guide.txt": b"text"}, "PDF"),
        ('attachments = ["attachments/missing.pdf"]', {}, "not found"),
        ('attachments = ["attachments/empty.pdf"]', {"attachments/empty.pdf": b""}, "empty"),
        (
            'attachments = ["attachments/guide.pdf", "attachments/guide.pdf"]',
            {"attachments/guide.pdf": b"%PDF-1.7"},
            "more than once",
        ),
        (
            'attachments = ["attachments/invalid.pdf"]',
            {"attachments/invalid.pdf": b"not a PDF"},
            "not a valid PDF",
        ),
    ],
)
def test_load_campaign_rejects_invalid_attachments(
    tmp_path: Path,
    attachments: str,
    files: dict[str, bytes],
    error: str,
) -> None:
    for relative_path, content in files.items():
        write_pdf(tmp_path / relative_path, content)
    write_campaign(tmp_path)
    with (tmp_path / "campaign.toml").open("a", encoding="utf-8") as file:
        file.write(f"\n{attachments}\n")

    with pytest.raises(ConfigurationError, match=error):
        load_campaign(tmp_path)


def test_load_campaign_rejects_attachment_larger_than_file_limit(tmp_path: Path) -> None:
    write_pdf(tmp_path / "attachments" / "large.pdf", b"%PDF-" + b"x" * MAX_ATTACHMENT_FILE_BYTES)
    write_campaign(tmp_path)
    with (tmp_path / "campaign.toml").open("a", encoding="utf-8") as file:
        file.write('\nattachments = ["attachments/large.pdf"]\n')

    with pytest.raises(ConfigurationError, match="per-file limit"):
        load_campaign(tmp_path)


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
