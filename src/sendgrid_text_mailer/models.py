"""Domain models used by the mailer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AppConfig:
    api_key: str
    from_email: str
    from_name: str
    unsubscribe_group_id: int
    database_path: Path


@dataclass(frozen=True, slots=True)
class Campaign:
    campaign_id: str
    name: str
    directory: Path
    recipients_file: Path
    subject_file: Path
    body_file: Path
    max_send_count: int
    send_interval_seconds: float


@dataclass(frozen=True, slots=True)
class Recipient:
    email: str
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        last_name = self.fields.get("last_name", "").strip()
        first_name = self.fields.get("first_name", "").strip()
        name = " ".join(part for part in (last_name, first_name) if part)
        return f"{name} 様" if name else "お客様"

    def template_context(self) -> dict[str, Any]:
        return {**self.fields, "email": self.email, "full_name": self.full_name}


@dataclass(frozen=True, slots=True)
class RenderedMessage:
    recipient: Recipient
    subject: str
    body: str


@dataclass(frozen=True, slots=True)
class SendResult:
    status_code: int
    message_id: str | None
