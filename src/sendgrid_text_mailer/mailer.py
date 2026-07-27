"""SendGrid API integration."""

from __future__ import annotations

import json
from collections.abc import Iterable

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Asm,
    ClickTracking,
    From,
    Mail,
    OpenTracking,
    PlainTextContent,
    To,
    TrackingSettings,
)

from .errors import SendGridError
from .models import AppConfig, RenderedMessage, SendResult
from .recipients import normalize_email


class SendGridGateway:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.client = SendGridAPIClient(config.api_key)

    def get_unsubscribed_emails(self) -> set[str]:
        """Return all addresses suppressed for the configured ASM group."""
        try:
            response = (
                self.client.client.asm.groups
                ._(self.config.unsubscribe_group_id)
                .suppressions.get()
            )
        except Exception as exc:
            raise SendGridError(f"Failed to retrieve unsubscribe list: {exc}") from exc

        if response.status_code != 200:
            raise SendGridError(
                "Failed to retrieve unsubscribe list: "
                f"HTTP {response.status_code}: {_response_body(response.body)}"
            )

        try:
            payload = json.loads(response.body)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SendGridError("SendGrid returned an invalid unsubscribe response.") from exc

        if not isinstance(payload, list):
            raise SendGridError("SendGrid returned an unexpected unsubscribe response.")

        emails: set[str] = set()
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("email"), str):
                emails.add(normalize_email(item["email"]))
        return emails

    def send(self, message: RenderedMessage) -> SendResult:
        mail = Mail(
            from_email=From(self.config.from_email, self.config.from_name),
            to_emails=To(message.recipient.email),
            subject=message.subject,
            plain_text_content=PlainTextContent(message.body),
        )
        mail.asm = Asm(group_id=self.config.unsubscribe_group_id)

        tracking = TrackingSettings()
        tracking.click_tracking = ClickTracking(enable=False, enable_text=False)
        tracking.open_tracking = OpenTracking(enable=False)
        mail.tracking_settings = tracking

        try:
            response = self.client.send(mail)
        except Exception as exc:
            raise SendGridError(f"SendGrid request failed: {exc}") from exc

        if response.status_code not in {200, 201, 202}:
            raise SendGridError(
                f"SendGrid rejected the message with HTTP {response.status_code}: "
                f"{_response_body(response.body)}"
            )

        message_id = _first_header(response.headers, "X-Message-Id")
        return SendResult(status_code=response.status_code, message_id=message_id)


def _response_body(body: bytes | str | None) -> str:
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _first_header(headers: dict | Iterable | None, name: str) -> str | None:
    if not headers:
        return None
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name) or getter(name.lower())
        if value:
            return str(value)
    try:
        for key, value in headers:
            if str(key).lower() == name.lower():
                return str(value)
    except (TypeError, ValueError):
        return None
    return None
