from pathlib import Path

import pytest

from sendgrid_text_mailer.errors import ValidationError
from sendgrid_text_mailer.models import Campaign, Recipient
from sendgrid_text_mailer.template import render_messages


def campaign(tmp_path: Path, subject: str, body: str) -> Campaign:
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
        max_send_count=10,
        send_interval_seconds=0,
    )


def test_render_message(tmp_path: Path) -> None:
    item = campaign(tmp_path, "{company}様へのご案内", "{full_name}\n本文")
    recipient = Recipient(
        email="user@example.com",
        fields={"company": "サンプル株式会社", "last_name": "山田", "first_name": "太郎"},
    )
    message = render_messages(item, [recipient])[0]
    assert message.subject == "サンプル株式会社様へのご案内"
    assert message.body.startswith("山田 太郎 様")


def test_multiline_subject_is_rejected(tmp_path: Path) -> None:
    item = campaign(tmp_path, "line1\nline2", "body")
    with pytest.raises(ValidationError, match="one line"):
        render_messages(item, [Recipient(email="user@example.com")])
