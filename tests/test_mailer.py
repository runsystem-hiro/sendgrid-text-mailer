from pathlib import Path
from types import SimpleNamespace

from sendgrid_text_mailer.mailer import SendGridGateway
from sendgrid_text_mailer.models import AppConfig, Recipient, RenderedMessage


def config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        api_key="test-key",
        from_email="sender@example.com",
        from_name="Example Sender",
        unsubscribe_group_id=12345,
        database_path=tmp_path / "mailer.sqlite3",
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
