import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sendgrid_text_mailer.errors import SendGridError
from sendgrid_text_mailer.mailer import SendGridGateway, prepare_attachments
from sendgrid_text_mailer.models import AppConfig, PreparedAttachment, Recipient, RenderedMessage


def config(tmp_path: Path, reply_to_list: tuple[str, ...] = ()) -> AppConfig:
    return AppConfig(
        api_key="test-key",
        from_email="sender@example.com",
        from_name="Example Sender",
        unsubscribe_group_id=12345,
        database_path=tmp_path / "mailer.sqlite3",
        reply_to_list=reply_to_list,
    )


def test_send_disables_tracking(monkeypatch, tmp_path: Path) -> None:
    gateway = SendGridGateway(config(tmp_path))
    captured = {}

    def fake_send(mail):
        captured.update(mail.get())
        return SimpleNamespace(status_code=202, body=b"", headers={"X-Message-Id": "abc"})

    monkeypatch.setattr(gateway.client, "send", fake_send)
    result = gateway.send(
        RenderedMessage(
            recipient=Recipient(email="user@example.com"),
            subject="Subject",
            body="Body",
        )
    )

    assert result.status_code == 202
    assert captured["content"] == [{"type": "text/plain", "value": "Body"}]
    assert captured["tracking_settings"]["click_tracking"] == {
        "enable": False,
        "enable_text": False,
    }
    assert captured["tracking_settings"]["open_tracking"] == {"enable": False}
    assert "asm" not in captured
    assert "reply_to_list" not in captured


def test_send_sets_all_configured_reply_to_addresses(monkeypatch, tmp_path: Path) -> None:
    gateway = SendGridGateway(config(tmp_path, ("kurosawa@example.com", "hiro@example.com")))
    captured = {}

    def fake_send(mail):
        captured.update(mail.get())
        return SimpleNamespace(status_code=202, body=b"", headers={})

    monkeypatch.setattr(gateway.client, "send", fake_send)
    gateway.send(
        RenderedMessage(
            recipient=Recipient(email="user@example.com"),
            subject="Subject",
            body="Body",
        )
    )

    assert captured["reply_to_list"] == [
        {"email": "kurosawa@example.com"},
        {"email": "hiro@example.com"},
    ]


def test_verify_sender_accepts_verified_matching_from_address(monkeypatch, tmp_path: Path) -> None:
    gateway = SendGridGateway(config(tmp_path))

    def fake_get(*, query_params):
        assert query_params == {"limit": 1000}
        return SimpleNamespace(
            status_code=200,
            body=b'{"results": [{"id": 1, "from_email": "SENDER@example.com", "verified": true}]}',
        )

    monkeypatch.setattr(
        gateway.client,
        "client",
        SimpleNamespace(verified_senders=SimpleNamespace(get=fake_get)),
    )

    gateway.verify_sender()


def test_get_global_unsubscribed_emails_pages_and_normalizes(monkeypatch, tmp_path: Path) -> None:
    gateway = SendGridGateway(config(tmp_path))
    first_page = [
        {"email": "FIRST@example.com"},
        *({"email": f"user-{index}@example.com"} for index in range(1, 500)),
    ]
    calls: list[dict[str, int]] = []

    def fake_get(*, query_params):
        calls.append(query_params)
        if query_params["offset"] == 0:
            return SimpleNamespace(status_code=200, body=json.dumps(first_page).encode())
        return SimpleNamespace(status_code=200, body=b'[{"email": "LAST@example.com"}]')

    monkeypatch.setattr(
        gateway.client,
        "client",
        SimpleNamespace(suppression=SimpleNamespace(unsubscribes=SimpleNamespace(get=fake_get))),
    )

    assert gateway.get_global_unsubscribed_emails() == {
        "first@example.com",
        *(f"user-{index}@example.com" for index in range(1, 500)),
        "last@example.com",
    }
    assert calls == [{"limit": 500, "offset": 0}, {"limit": 500, "offset": 500}]


def test_get_global_unsubscribed_emails_fails_closed_on_non_success(
    monkeypatch, tmp_path: Path
) -> None:
    gateway = SendGridGateway(config(tmp_path))

    def fake_get(*, query_params):
        assert query_params == {"limit": 500, "offset": 0}
        return SimpleNamespace(status_code=403, body=b"forbidden")

    monkeypatch.setattr(
        gateway.client,
        "client",
        SimpleNamespace(suppression=SimpleNamespace(unsubscribes=SimpleNamespace(get=fake_get))),
    )

    with pytest.raises(SendGridError, match="global unsubscribe list: HTTP 403"):
        gateway.get_global_unsubscribed_emails()


def test_verify_sender_rejects_unverified_matching_from_address(
    monkeypatch, tmp_path: Path
) -> None:
    gateway = SendGridGateway(config(tmp_path))

    def fake_get(*, query_params):
        return SimpleNamespace(
            status_code=200,
            body=b'{"results": [{"id": 1, "from_email": "sender@example.com", "verified": false}]}',
        )

    monkeypatch.setattr(
        gateway.client,
        "client",
        SimpleNamespace(verified_senders=SimpleNamespace(get=fake_get)),
    )

    with pytest.raises(SendGridError, match="not a verified SendGrid sender"):
        gateway.verify_sender()


def test_send_adds_allowed_attachments_without_changing_plain_text(
    monkeypatch, tmp_path: Path
) -> None:
    gateway = SendGridGateway(config(tmp_path))
    captured = {}

    def fake_send(mail):
        captured.update(mail.get())
        return SimpleNamespace(status_code=202, body=b"", headers={})

    monkeypatch.setattr(gateway.client, "send", fake_send)
    gateway.send(
        RenderedMessage(Recipient(email="user@example.com"), "Subject", "Body"),
        (
            PreparedAttachment(
                filename="guide.pdf", mime_type="application/pdf", encoded_content="cGRm"
            ),
            PreparedAttachment(
                filename="product.png", mime_type="image/png", encoded_content="cG5n"
            ),
            PreparedAttachment(
                filename="photo.jpeg", mime_type="image/jpeg", encoded_content="anBlZw=="
            ),
        ),
    )

    assert captured["content"] == [{"type": "text/plain", "value": "Body"}]
    assert captured["attachments"] == [
        {
            "content": "cGRm",
            "filename": "guide.pdf",
            "type": "application/pdf",
            "disposition": "attachment",
        },
        {
            "content": "cG5n",
            "filename": "product.png",
            "type": "image/png",
            "disposition": "attachment",
        },
        {
            "content": "anBlZw==",
            "filename": "photo.jpeg",
            "type": "image/jpeg",
            "disposition": "attachment",
        },
    ]


def test_prepare_attachments_encodes_each_file_once(tmp_path: Path) -> None:
    pdf = tmp_path / "guide.pdf"
    pdf.write_bytes(b"%PDF-1.7\nexample")

    attachments = prepare_attachments((pdf,))

    assert attachments == (
        PreparedAttachment(
            filename="guide.pdf",
            mime_type="application/pdf",
            encoded_content="JVBERi0xLjcKZXhhbXBsZQ==",
        ),
    )
