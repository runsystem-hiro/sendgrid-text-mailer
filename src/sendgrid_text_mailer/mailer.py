"""SendGrid API integration."""

from __future__ import annotations

import json
from base64 import b64encode
from collections.abc import Iterable
from pathlib import Path

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    ClickTracking,
    Disposition,
    FileContent,
    FileName,
    FileType,
    From,
    Mail,
    OpenTracking,
    PlainTextContent,
    ReplyTo,
    To,
    TrackingSettings,
)

from .config import ALLOWED_ATTACHMENT_TYPES
from .errors import SendGridError
from .models import AppConfig, PreparedAttachment, RenderedMessage, SendResult
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

    def send(
        self,
        message: RenderedMessage,
        attachments: tuple[PreparedAttachment, ...] = (),
    ) -> SendResult:
        mail = Mail(
            from_email=From(self.config.from_email, self.config.from_name),
            to_emails=To(message.recipient.email),
            subject=message.subject,
            plain_text_content=PlainTextContent(message.body),
        )
        tracking = TrackingSettings()
        tracking.click_tracking = ClickTracking(enable=False, enable_text=False)
        tracking.open_tracking = OpenTracking(enable=False)
        mail.tracking_settings = tracking
        if self.config.reply_to_list:
            mail.reply_to_list = [ReplyTo(address) for address in self.config.reply_to_list]
        # The SendGrid helper prepends each attachment internally, so reverse the
        # iteration to preserve the order declared in campaign.toml.
        for attachment in reversed(attachments):
            mail.add_attachment(
                Attachment(
                    FileContent(attachment.encoded_content),
                    FileName(attachment.filename),
                    FileType(attachment.mime_type),
                    Disposition("attachment"),
                )
            )

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


def prepare_attachments(files: tuple[Path, ...]) -> tuple[PreparedAttachment, ...]:
    """Read and encode validated ordinary attachments once per campaign run."""
    prepared: list[PreparedAttachment] = []
    for path in files:
        try:
            encoded_content = b64encode(path.read_bytes()).decode("ascii")
        except OSError as exc:
            raise SendGridError(f"Attachment file cannot be read: {path}") from exc
        prepared.append(
            PreparedAttachment(
                filename=path.name,
                mime_type=ALLOWED_ATTACHMENT_TYPES[path.suffix.lower()][0],
                encoded_content=encoded_content,
            )
        )
    return tuple(prepared)


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
