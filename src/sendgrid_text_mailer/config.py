"""Configuration loading for environment variables and campaign files."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from .errors import ConfigurationError
from .models import AppConfig, Campaign
from .recipients import EMAIL_PATTERN, normalize_email

DEFAULT_DATABASE_PATH = Path("data/sendgrid-text-mailer.sqlite3")
MAX_ATTACHMENT_FILE_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENT_TOTAL_BYTES = 15 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES: dict[str, tuple[str, bytes]] = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
}
SAFE_ATTACHMENT_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Required environment variable is missing: {name}")
    return value


def _load_reply_to_list() -> tuple[str, ...]:
    """Load and validate optional comma-separated reply addresses."""
    raw = os.getenv("SENDGRID_REPLY_TO_LIST", "")
    if not raw.strip():
        return ()

    addresses: list[str] = []
    seen: set[str] = set()
    for value in raw.split(","):
        address = normalize_email(value)
        if not address:
            raise ConfigurationError(
                "SENDGRID_REPLY_TO_LIST must not contain empty email addresses."
            )
        if not EMAIL_PATTERN.fullmatch(address):
            raise ConfigurationError(
                f"SENDGRID_REPLY_TO_LIST contains an invalid email address: {address}"
            )
        if address in seen:
            raise ConfigurationError(
                f"SENDGRID_REPLY_TO_LIST contains a duplicate email address: {address}"
            )
        seen.add(address)
        addresses.append(address)
    return tuple(addresses)


def load_app_config(*, require_credentials: bool = True) -> AppConfig | None:
    """Load runtime settings from .env and the process environment."""
    load_dotenv()
    if not require_credentials:
        return None

    group_raw = _required_env("SENDGRID_UNSUBSCRIBE_GROUP_ID")
    try:
        group_id = int(group_raw)
    except ValueError as exc:
        raise ConfigurationError("SENDGRID_UNSUBSCRIBE_GROUP_ID must be an integer.") from exc
    if group_id <= 0:
        raise ConfigurationError("SENDGRID_UNSUBSCRIBE_GROUP_ID must be greater than zero.")

    database_path = Path(os.getenv("MAILER_DATABASE_PATH", str(DEFAULT_DATABASE_PATH)))
    return AppConfig(
        api_key=_required_env("SENDGRID_API_KEY"),
        from_email=_required_env("SENDGRID_FROM_EMAIL"),
        from_name=_required_env("SENDGRID_FROM_NAME"),
        unsubscribe_group_id=group_id,
        database_path=database_path,
        reply_to_list=_load_reply_to_list(),
    )


def load_campaign(campaign_dir: Path) -> Campaign:
    """Read and validate a campaign.toml file."""
    directory = campaign_dir.resolve()
    config_path = directory / "campaign.toml"
    if not config_path.is_file():
        raise ConfigurationError(f"Campaign configuration not found: {config_path}")

    try:
        with config_path.open("rb") as file:
            raw = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML in {config_path}: {exc}") from exc

    campaign_id = str(raw.get("campaign_id", "")).strip()
    name = str(raw.get("name", "")).strip()
    recipients_raw = str(raw.get("recipients_file", "")).strip()
    unsubscribe_url = str(raw.get("unsubscribe_url", "")).strip()
    if not campaign_id:
        raise ConfigurationError("campaign_id is required in campaign.toml.")
    if not name:
        raise ConfigurationError("name is required in campaign.toml.")
    if not recipients_raw:
        raise ConfigurationError("recipients_file is required in campaign.toml.")
    if unsubscribe_url:
        validate_unsubscribe_url(unsubscribe_url)

    max_send_count = raw.get("max_send_count", 500)
    send_interval = raw.get("send_interval_seconds", 1.0)
    if not isinstance(max_send_count, int) or max_send_count <= 0:
        raise ConfigurationError("max_send_count must be a positive integer.")
    if not isinstance(send_interval, int | float) or send_interval < 0:
        raise ConfigurationError("send_interval_seconds must be zero or greater.")

    recipients_path = (directory / recipients_raw).resolve()
    attachment_files = _load_attachment_files(directory, raw.get("attachments"))
    return Campaign(
        campaign_id=campaign_id,
        name=name,
        directory=directory,
        recipients_file=recipients_path,
        subject_file=directory / "subject.txt",
        body_file=directory / "body.txt",
        unsubscribe_url=unsubscribe_url,
        max_send_count=max_send_count,
        send_interval_seconds=float(send_interval),
        attachment_files=attachment_files,
    )


def _load_attachment_files(directory: Path, attachments_raw: object | None) -> tuple[Path, ...]:
    if attachments_raw is None:
        return ()
    if not isinstance(attachments_raw, list):
        raise ConfigurationError("attachments must be an array of PDF, PNG, or JPEG file paths.")

    attachment_files: list[Path] = []
    seen: set[Path] = set()
    total_size = 0
    for index, raw_path in enumerate(attachments_raw, start=1):
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ConfigurationError(f"attachments[{index}] must be a non-empty file path string.")
        path = (directory / raw_path).resolve()
        attachment_type = ALLOWED_ATTACHMENT_TYPES.get(path.suffix.lower())
        if attachment_type is None:
            raise ConfigurationError(f"Attachment must be a PDF, PNG, or JPEG file: {path}")
        if not SAFE_ATTACHMENT_FILENAME.fullmatch(path.name):
            raise ConfigurationError(
                "添付ファイル名にASCII以外の文字または使用できない記号が含まれています。"
                "英数字で始め、英数字・半角スペース・.・_・- のみを使うASCII名へ"
                "変更してください（例: product-catalog.pdf）: "
                f"{path.name}"
            )
        if path in seen:
            raise ConfigurationError(f"Attachment is specified more than once: {path}")
        if not path.is_file():
            raise ConfigurationError(f"Attachment file not found: {path}")
        try:
            size = path.stat().st_size
            with path.open("rb") as file:
                signature = file.read(len(attachment_type[1]))
        except OSError as exc:
            raise ConfigurationError(f"Attachment file cannot be read: {path}") from exc
        if size == 0:
            raise ConfigurationError(f"Attachment file is empty: {path}")
        if size > MAX_ATTACHMENT_FILE_BYTES:
            raise ConfigurationError(
                f"Attachment exceeds the {MAX_ATTACHMENT_FILE_BYTES // (1024 * 1024)} MB "
                f"per-file limit: {path}"
            )
        total_size += size
        if total_size > MAX_ATTACHMENT_TOTAL_BYTES:
            raise ConfigurationError(
                f"Attachments exceed the {MAX_ATTACHMENT_TOTAL_BYTES // (1024 * 1024)} MB "
                "total limit."
            )
        if signature != attachment_type[1]:
            raise ConfigurationError(f"Attachment does not match its expected file type: {path}")
        seen.add(path)
        attachment_files.append(path)
    return tuple(attachment_files)


def validate_unsubscribe_url(value: str) -> None:
    if not value:
        raise ConfigurationError("unsubscribe_url is required in campaign.toml.")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError("unsubscribe_url must be an absolute HTTP or HTTPS URL.")
    if parsed.username or parsed.password:
        raise ConfigurationError("unsubscribe_url must not contain credentials.")
