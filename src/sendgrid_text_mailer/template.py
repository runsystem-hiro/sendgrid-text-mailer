"""Plain-text subject and body template handling."""

from __future__ import annotations

from string import Formatter

from .errors import ValidationError
from .models import Campaign, Recipient, RenderedMessage

SIGNATURE_TEMPLATE_EXAMPLE = """株式会社ランシステム
システム第２営業部 システム外販課
山田太郎 mail: taro@mail.com
ランシステム: https://www.runsystem.co.jp/
サイバーテレワーク: https://www.cyber-telework.jp/"""


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

    if "signature" in template_fields(body_template):
        if campaign.signature_file is None:
            raise ValidationError("body.txt uses {signature} but signature.txt is not present.")
        signature_template = _read_template("Signature", campaign.signature_file)
        if signature_template == SIGNATURE_TEMPLATE_EXAMPLE:
            raise ValidationError(
                "signature.txt is still the template example. "
                "Replace it with the sender's approved signature before validation."
            )
        if campaign.from_name and _compact(campaign.from_name) not in _compact(signature_template):
            raise ValidationError(
                "signature.txt does not contain the campaign from_name. "
                "Replace it with the sender's approved signature before validation."
            )
        body_template = body_template.replace("{signature}", signature_template)

    required_fields = template_fields(subject_template) | template_fields(body_template)
    if "unsubscribe_url" in required_fields and not campaign.unsubscribe_url:
        raise ValidationError(
            "unsubscribe_url is used in a template but is not set in campaign.toml."
        )
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


def _compact(value: str) -> str:
    return "".join(value.split())
