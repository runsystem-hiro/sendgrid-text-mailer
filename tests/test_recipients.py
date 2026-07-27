from pathlib import Path

import pytest

from sendgrid_text_mailer.errors import ValidationError
from sendgrid_text_mailer.recipients import load_recipients, normalize_email


def test_normalize_email() -> None:
    assert normalize_email(" User@Example.COM ") == "user@example.com"


def test_load_recipients(tmp_path: Path) -> None:
    path = tmp_path / "recipients.csv"
    path.write_text(
        "email,last_name,first_name\nUSER@example.com,山田,太郎\n",
        encoding="utf-8",
    )
    recipients = load_recipients(path)
    assert recipients[0].email == "user@example.com"
    assert recipients[0].full_name == "山田 太郎 様"


def test_duplicate_recipient_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "recipients.csv"
    path.write_text(
        "email\nuser@example.com\nUSER@example.com\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="duplicate"):
        load_recipients(path)
