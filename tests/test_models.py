import pytest

from sendgrid_text_mailer.models import Recipient


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (
            {"company": "サンプル株式会社", "last_name": "山田", "first_name": "太郎"},
            "サンプル株式会社\n山田 太郎 様",
        ),
        (
            {"company": "サンプル株式会社", "last_name": "", "first_name": ""},
            "サンプル株式会社\nご担当者様",
        ),
        (
            {"company": "", "last_name": "山田", "first_name": "太郎"},
            "山田 太郎 様",
        ),
        (
            {"company": "", "last_name": "", "first_name": ""},
            "ご担当者様",
        ),
    ],
)
def test_recipient_block(fields: dict[str, str], expected: str) -> None:
    recipient = Recipient(email="user@example.com", fields=fields)
    assert recipient.recipient_block == expected


@pytest.mark.parametrize(
    ("last_name", "first_name", "expected"),
    [
        ("山田", "", "山田 様"),
        ("", "太郎", "太郎 様"),
        ("   ", "  ", "ご担当者様"),
    ],
)
def test_full_name_partial_or_blank(
    last_name: str,
    first_name: str,
    expected: str,
) -> None:
    recipient = Recipient(
        email="user@example.com",
        fields={"last_name": last_name, "first_name": first_name},
    )
    assert recipient.full_name == expected
