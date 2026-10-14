from dataclasses import replace
from pathlib import Path

import pytest

from sendgrid_text_mailer.errors import ValidationError
from sendgrid_text_mailer.models import Campaign, Recipient
from sendgrid_text_mailer.template import SIGNATURE_TEMPLATE_EXAMPLE, render_messages


def campaign(
    tmp_path: Path,
    subject: str,
    body: str,
    unsubscribe_url: str = "https://example.com/unsubscribe?group_id=12345",
) -> Campaign:
    subject_path = tmp_path / "subject.txt"
    body_path = tmp_path / "body.txt"
    subject_path.write_text(subject, encoding="utf-8")
    body_path.write_text(body, encoding="utf-8")
    return Campaign(
        campaign_id="test",
        name="Test",
        directory=tmp_path,
        recipients_file=tmp_path / "recipients.csv",
        subject_file=subject_path,
        body_file=body_path,
        unsubscribe_url=unsubscribe_url,
        max_send_count=10,
        send_interval_seconds=0,
    )


def test_render_message(tmp_path: Path) -> None:
    item = campaign(tmp_path, "{company}様へのご案内", "{recipient_block}\n本文")
    recipient = Recipient(
        email="user@example.com",
        fields={"company": "サンプル株式会社", "last_name": "山田", "first_name": "太郎"},
    )
    message = render_messages(item, [recipient])[0]
    assert message.subject == "サンプル株式会社様へのご案内"
    assert message.body.startswith("サンプル株式会社\n山田 太郎 様")


def test_multiline_subject_is_rejected(tmp_path: Path) -> None:
    item = campaign(tmp_path, "line1\nline2", "body")
    with pytest.raises(ValidationError, match="one line"):
        render_messages(item, [Recipient(email="user@example.com")])


def test_render_unsubscribe_url(tmp_path: Path) -> None:
    item = campaign(tmp_path, "Subject", "配信停止: {unsubscribe_url}")
    message = render_messages(item, [Recipient(email="user@example.com")])[0]
    assert message.body == "配信停止: https://example.com/unsubscribe?group_id=12345"


def test_unsubscribe_url_requires_campaign_setting(tmp_path: Path) -> None:
    item = campaign(tmp_path, "Subject", "配信停止: {unsubscribe_url}", unsubscribe_url="")

    with pytest.raises(ValidationError, match="not set in campaign.toml"):
        render_messages(item, [Recipient(email="user@example.com")])


def test_signature_file_is_rendered_when_used_by_body(tmp_path: Path) -> None:
    item = campaign(tmp_path, "Subject", "{recipient_block}\n{signature}")
    signature_path = tmp_path / "signature.txt"
    signature_path.write_text("営業部\n{from_name}\n", encoding="utf-8")
    item = replace(item, signature_file=signature_path)
    recipient = Recipient(email="user@example.com", fields={"from_name": "営業 太郎"})

    message = render_messages(item, [recipient])[0]

    assert message.body.endswith("営業部\n営業 太郎")


def test_signature_placeholder_requires_signature_file(tmp_path: Path) -> None:
    item = campaign(tmp_path, "Subject", "{signature}")

    with pytest.raises(ValidationError, match="signature.txt is not present"):
        render_messages(item, [Recipient(email="user@example.com")])


def test_signature_template_example_requires_replacement(tmp_path: Path) -> None:
    item = campaign(tmp_path, "Subject", "{signature}")
    signature_path = tmp_path / "signature.txt"
    signature_path.write_text(SIGNATURE_TEMPLATE_EXAMPLE + "\n", encoding="utf-8")
    item = replace(item, signature_file=signature_path)

    with pytest.raises(ValidationError, match="still the template example"):
        render_messages(item, [Recipient(email="user@example.com")])


def test_signature_requires_campaign_sender_name(tmp_path: Path) -> None:
    item = campaign(tmp_path, "Subject", "{signature}")
    signature_path = tmp_path / "signature.txt"
    signature_path.write_text("株式会社サンプル\n営業部\n", encoding="utf-8")
    item = replace(item, signature_file=signature_path, from_name="山田 太郎")

    with pytest.raises(ValidationError, match="does not contain the campaign from_name"):
        render_messages(item, [Recipient(email="user@example.com")])
