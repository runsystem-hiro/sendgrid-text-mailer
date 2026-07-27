"""Configuration loading for environment variables and campaign files."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from .errors import ConfigurationError
from .models import AppConfig, Campaign

DEFAULT_DATABASE_PATH = Path("data/sendgrid-text-mailer.sqlite3")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"Required environment variable is missing: {name}")
    return value


def load_app_config(*, require_credentials: bool = True) -> AppConfig | None:
    """Load runtime settings from .env and the process environment."""
    load_dotenv()
    if not require_credentials:
        return None

    group_raw = _required_env("SENDGRID_UNSUBSCRIBE_GROUP_ID")
    try:
        group_id = int(group_raw)
    except ValueError as exc:
        raise ConfigurationError(
            "SENDGRID_UNSUBSCRIBE_GROUP_ID must be an integer."
        ) from exc
    if group_id <= 0:
        raise ConfigurationError("SENDGRID_UNSUBSCRIBE_GROUP_ID must be greater than zero.")

    database_path = Path(os.getenv("MAILER_DATABASE_PATH", str(DEFAULT_DATABASE_PATH)))
    return AppConfig(
        api_key=_required_env("SENDGRID_API_KEY"),
        from_email=_required_env("SENDGRID_FROM_EMAIL"),
        from_name=_required_env("SENDGRID_FROM_NAME"),
        unsubscribe_group_id=group_id,
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
    validate_unsubscribe_url(unsubscribe_url)

    max_send_count = raw.get("max_send_count", 500)
    send_interval = raw.get("send_interval_seconds", 1.0)
    if not isinstance(max_send_count, int) or max_send_count <= 0:
        raise ConfigurationError("max_send_count must be a positive integer.")
    if not isinstance(send_interval, int | float) or send_interval < 0:
        raise ConfigurationError("send_interval_seconds must be zero or greater.")

    recipients_path = (directory / recipients_raw).resolve()
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
    )


def validate_unsubscribe_url(value: str) -> None:
    if not value:
        raise ConfigurationError("unsubscribe_url is required in campaign.toml.")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(
            "unsubscribe_url must be an absolute HTTP or HTTPS URL."
        )
    if parsed.username or parsed.password:
        raise ConfigurationError("unsubscribe_url must not contain credentials.")
