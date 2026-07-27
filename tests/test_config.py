from pathlib import Path

import pytest

from sendgrid_text_mailer.config import load_campaign
from sendgrid_text_mailer.errors import ConfigurationError


def write_campaign(tmp_path: Path, unsubscribe_url: str) -> None:
    (tmp_path / "campaign.toml").write_text(
        "\n".join(
            [
                'campaign_id = "test"',
                'name = "Test"',
                'recipients_file = "recipients.csv"',
                f'unsubscribe_url = "{unsubscribe_url}"',
            ]
        ),
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
