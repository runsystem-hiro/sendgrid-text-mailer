"""Campaign scaffold generation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .config import validate_unsubscribe_url
from .errors import ValidationError

_CAMPAIGN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class CampaignScaffold:
    directory: Path
    config_file: Path
    subject_file: Path
    body_file: Path


def create_campaign_scaffold(
    *,
    campaign_id: str,
    name: str,
    recipients_file: Path,
    unsubscribe_url: str,
    output_dir: Path | None = None,
    max_send_count: int = 500,
    send_interval_seconds: float = 1.0,
) -> CampaignScaffold:
    campaign_id = campaign_id.strip()
    name = name.strip()

    if not _CAMPAIGN_ID_PATTERN.fullmatch(campaign_id):
        raise ValidationError(
            "campaign_id must contain only lowercase letters, numbers, '.', '_' or '-'."
        )
    if not name:
        raise ValidationError("Campaign name must not be empty.")
    if max_send_count < 1:
        raise ValidationError("max_send_count must be at least 1.")
    if send_interval_seconds < 0:
        raise ValidationError("send_interval_seconds must not be negative.")

    validate_unsubscribe_url(unsubscribe_url)

    directory = output_dir or Path("campaigns") / campaign_id
    directory = directory.resolve()

    if directory.exists():
        raise ValidationError(f"Output directory already exists: {directory}")

    recipients_file = recipients_file.resolve()
    if not recipients_file.is_file():
        raise ValidationError(f"Recipients CSV does not exist: {recipients_file}")

    directory.mkdir(parents=True)

    relative_recipients = Path(
        os.path.relpath(
            recipients_file,
            start=directory,
        )
    )

    config_file = directory / "campaign.toml"
    subject_file = directory / "subject.txt"
    body_file = directory / "body.txt"

    config_file.write_text(
        "\n".join(
            [
                f'campaign_id = "{campaign_id}"',
                f'name = "{_escape_toml(name)}"',
                f'recipients_file = "{relative_recipients.as_posix()}"',
                f'unsubscribe_url = "{_escape_toml(unsubscribe_url)}"',
                f"max_send_count = {max_send_count}",
                f"send_interval_seconds = {send_interval_seconds}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    subject_file.write_text(
        "【ご案内】件名を入力してください\n",
        encoding="utf-8",
    )

    body_file.write_text(
        "\n".join(
            [
                "{recipient_block}",
                "",
                "平素よりお世話になっております。",
                "",
                "本文を入力してください。",
                "",
                "▼ 配信停止はこちらから",
                "{unsubscribe_url}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return CampaignScaffold(
        directory=directory,
        config_file=config_file,
        subject_file=subject_file,
        body_file=body_file,
    )


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
