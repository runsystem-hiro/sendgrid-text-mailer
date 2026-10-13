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
        'from_email = "sender@example.com"',
        'from_name = "Example Sender"',
        'reply_to_list = ["reply@example.com"]',
        "unsubscribe_group_id = 12345",
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


def test_load_campaign_requires_campaign_sender_settings(tmp_path: Path) -> None:
    (tmp_path / "campaign.toml").write_text(
        "\n".join(
            [
                'campaign_id = "test"',
                'name = "Test"',
                'recipients_file = "recipients.csv"',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="from_email is required"):
        load_campaign(tmp_path)


def test_load_campaign_reads_campaign_sender_settings(tmp_path: Path) -> None:
    write_campaign(tmp_path)

    campaign = load_campaign(tmp_path)

    assert campaign.from_email == "sender@example.com"
    assert campaign.from_name == "Example Sender"
    assert campaign.reply_to_list == ("reply@example.com",)
    assert campaign.unsubscribe_group_id == 12345


def write_pdf(path: Path, content: bytes = b"%PDF-1.7\nexample") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def write_png(path: Path, content: bytes = b"\x89PNG\r\n\x1a\nexample") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def write_jpeg(path: Path, content: bytes = b"\xff\xd8\xff\xe0example") -> None:
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


def test_load_campaign_accepts_pdf_png_and_jpeg_attachments(tmp_path: Path) -> None:
    write_pdf(tmp_path / "attachments" / "guide.pdf")
    write_png(tmp_path / "attachments" / "product.png")
    write_jpeg(tmp_path / "attachments" / "photo.JPEG")
    write_campaign(tmp_path)
    with (tmp_path / "campaign.toml").open("a", encoding="utf-8") as file:
        file.write(
            '\nattachments = ["attachments/guide.pdf", "attachments/product.png", '
            '"attachments/photo.JPEG"]\n'
        )

    campaign = load_campaign(tmp_path)

    assert campaign.attachment_files == (
        (tmp_path / "attachments" / "guide.pdf").resolve(),
        (tmp_path / "attachments" / "product.png").resolve(),
        (tmp_path / "attachments" / "photo.JPEG").resolve(),
    )


def test_load_campaign_rejects_non_ascii_attachment_filename(tmp_path: Path) -> None:
    write_pdf(tmp_path / "attachments" / "製品カタログ.pdf")
    write_campaign(tmp_path)
    with (tmp_path / "campaign.toml").open("a", encoding="utf-8") as file:
        file.write('\nattachments = ["attachments/製品カタログ.pdf"]\n')

    with pytest.raises(ConfigurationError) as exc_info:
        load_campaign(tmp_path)

    assert "製品カタログ.pdf" in str(exc_info.value)
    assert "ASCII名へ変更してください" in str(exc_info.value)
    assert "product-catalog.pdf" in str(exc_info.value)


@pytest.mark.parametrize(
    ("attachments", "files", "error"),
    [
        ('attachments = "attachments/guide.pdf"', {}, "must be an array"),
        (
            'attachments = ["attachments/guide.txt"]',
            {"attachments/guide.txt": b"text"},
            "PDF, PNG, or JPEG",
        ),
        (
            'attachments = ["attachments/archive.zip"]',
            {"attachments/archive.zip": b"PK"},
            "PDF, PNG, or JPEG",
        ),
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
            "does not match its expected file type",
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
    monkeypatch.setenv("MAILER_DATABASE_PATH", str(tmp_path / "mailer.sqlite3"))

    config = load_app_config()

    assert config is not None
    assert config.api_key == "test-key"
    assert config.database_path == tmp_path / "mailer.sqlite3"


def test_load_campaign_rejects_duplicate_reply_to_address(tmp_path: Path) -> None:
    write_campaign(tmp_path)
    config_path = tmp_path / "campaign.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            'reply_to_list = ["reply@example.com"]',
            'reply_to_list = ["reply@example.com", "REPLY@example.com"]',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="duplicate email address"):
        load_campaign(tmp_path)
