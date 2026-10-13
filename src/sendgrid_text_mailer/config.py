"""Configuration loading for environment variables and campaign files."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from .errors import ConfigurationError
from .models import AppConfig, Campaign, RuntimeConfig
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


def _load_reply_to_list(raw: object, *, field_name: str) -> tuple[str, ...]:
    """Validate reply addresses declared in campaign.toml."""
    if not isinstance(raw, list | tuple):
        raise ConfigurationError(f"{field_name} must be an array of email addresses.")
    addresses: list[str] = []
    seen: set[str] = set()
    for value in raw:
        if not isinstance(value, str):
            raise ConfigurationError(f"{field_name} must contain only email address strings.")
        address = normalize_email(value)
        if not address:
            raise ConfigurationError(f"{field_name} must not contain empty email addresses.")
        if not EMAIL_PATTERN.fullmatch(address):
            raise ConfigurationError(f"{field_name} contains an invalid email address: {address}")
        if address in seen:
            raise ConfigurationError(f"{field_name} contains a duplicate email address: {address}")
        seen.add(address)
        addresses.append(address)
    return tuple(addresses)


def load_app_config(*, require_credentials: bool = True) -> RuntimeConfig | None:
    """Load runtime settings from .env and the process environment."""
    load_dotenv()
    if not require_credentials:
        return None

    database_path = Path(os.getenv("MAILER_DATABASE_PATH", str(DEFAULT_DATABASE_PATH)))
    return RuntimeConfig(
        api_key=_required_env("SENDGRID_API_KEY"),
        database_path=database_path,
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

    campaign_id = _required_toml_string(raw, "campaign_id")
    name = _required_toml_string(raw, "name")
    recipients_raw = _required_toml_string(raw, "recipients_file")
    from_email, from_name, reply_to_list, unsubscribe_group_id = validate_sender_settings(
        from_email=_required_toml_string(raw, "from_email"),
        from_name=_required_toml_string(raw, "from_name"),
        reply_to_list=raw.get("reply_to_list"),
        unsubscribe_group_id=raw.get("unsubscribe_group_id"),
    )
    unsubscribe_url = str(raw.get("unsubscribe_url", "")).strip()
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
        from_email=from_email,
        from_name=from_name,
        reply_to_list=reply_to_list,
        unsubscribe_group_id=unsubscribe_group_id,
    )


def delivery_config(runtime: RuntimeConfig, campaign: Campaign) -> AppConfig:
    """Combine machine-only credentials with the campaign's sender settings."""
    return AppConfig(
        api_key=runtime.api_key,
        from_email=campaign.from_email,
        from_name=campaign.from_name,
        unsubscribe_group_id=campaign.unsubscribe_group_id,
        database_path=runtime.database_path,
        reply_to_list=campaign.reply_to_list,
    )


def _required_toml_string(raw: dict[str, object], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{name} is required in campaign.toml.")
    return value.strip()


def validate_sender_settings(
    *,
    from_email: str,
    from_name: str,
    reply_to_list: object,
    unsubscribe_group_id: object,
) -> tuple[str, str, tuple[str, ...], int]:
    """Validate sender settings shared by campaign loading and scaffolding."""
    email = normalize_email(from_email)
    if not EMAIL_PATTERN.fullmatch(email):
        raise ConfigurationError(f"from_email is invalid: {email}")
    name = from_name.strip()
    if not name:
        raise ConfigurationError("from_name must not be empty.")
    replies = _load_reply_to_list(reply_to_list, field_name="reply_to_list")
    if (
        not isinstance(unsubscribe_group_id, int)
        or isinstance(unsubscribe_group_id, bool)
        or unsubscribe_group_id <= 0
    ):
        raise ConfigurationError("unsubscribe_group_id must be a positive integer.")
    return email, name, replies, unsubscribe_group_id


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
