"""Plain-text subject and body template handling."""

from __future__ import annotations

from string import Formatter

from .errors import ValidationError
from .models import Campaign, Recipient, RenderedMessage


def _read_template(path_name: str, path) -> str:
    if not path.is_file():
        raise ValidationError(f"{path_name} template not found: {path}")
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{path_name} template must be UTF-8 encoded: {path}") from exc
    content = content.rstrip("\r\n")
    if not content.strip():
        raise ValidationError(f"{path_name} template is empty: {path}")
    return content


def template_fields(template: str) -> set[str]:
    fields: set[str] = set()
    try:
        for _, field_name, _, _ in Formatter().parse(template):
            if field_name:
                fields.add(field_name)
    except ValueError as exc:
        raise ValidationError(f"Invalid template syntax: {exc}") from exc
    return fields


def render_messages(campaign: Campaign, recipients: list[Recipient]) -> list[RenderedMessage]:
    subject_template = _read_template("Subject", campaign.subject_file)
    body_template = _read_template("Body", campaign.body_file)
    if "\n" in subject_template or "\r" in subject_template:
        raise ValidationError("subject.txt must contain exactly one line.")

    required_fields = template_fields(subject_template) | template_fields(body_template)
    messages: list[RenderedMessage] = []
    errors: list[str] = []

    for recipient in recipients:
        context = {
            **recipient.template_context(),
            "unsubscribe_url": campaign.unsubscribe_url,
        }
        missing = sorted(field for field in required_fields if field not in context)
        if missing:
            errors.append(f"{recipient.email}: missing template fields: {', '.join(missing)}")
            continue
        try:
            subject = subject_template.format_map(context)
            body = body_template.format_map(context)
        except (KeyError, ValueError) as exc:
            errors.append(f"{recipient.email}: template rendering failed: {exc}")
            continue
        messages.append(RenderedMessage(recipient=recipient, subject=subject, body=body))

    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise ValidationError(f"Template validation failed:\n{joined}")
    return messages
