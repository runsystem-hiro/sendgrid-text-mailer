"""Recipient CSV loading and validation."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from .errors import ValidationError
from .models import Recipient

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_email(value: str) -> str:
    return value.strip().lower()


def load_recipients(path: Path) -> list[Recipient]:
    """Load recipients from UTF-8 CSV, rejecting invalid or duplicated addresses."""
    if not path.is_file():
        raise ValidationError(f"Recipients file not found: {path}")

    recipients: list[Recipient] = []
    seen: set[str] = set()
    errors: list[str] = []

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None or "email" not in reader.fieldnames:
                raise ValidationError("Recipient CSV must contain an 'email' header.")

            for line_number, row in enumerate(reader, start=2):
                email = normalize_email(row.get("email", ""))
                if not email:
                    errors.append(f"line {line_number}: email is empty")
                    continue
                if not EMAIL_PATTERN.fullmatch(email):
                    errors.append(f"line {line_number}: invalid email address: {email}")
                    continue
                if email in seen:
                    errors.append(f"line {line_number}: duplicate email address: {email}")
                    continue

                seen.add(email)
                fields = {
                    key.strip(): (value or "").strip()
                    for key, value in row.items()
                    if key and key.strip() != "email"
                }
                recipients.append(Recipient(email=email, fields=fields))
    except UnicodeDecodeError as exc:
        raise ValidationError(f"Recipient CSV must be UTF-8 encoded: {path}") from exc

    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise ValidationError(f"Recipient CSV validation failed:\n{joined}")
    if not recipients:
        raise ValidationError("Recipient CSV contains no valid recipients.")
    return recipients
