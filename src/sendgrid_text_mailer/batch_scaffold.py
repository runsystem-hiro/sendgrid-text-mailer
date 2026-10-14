"""Create one reviewed campaign per sender from a recipient assignment CSV."""

from __future__ import annotations

import csv
import re
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .config import validate_sender_settings, validate_unsubscribe_url
from .errors import ValidationError
from .scaffold import CampaignScaffold, create_campaign_scaffold
from .template import template_fields
from .template_sync import write_template_snapshot

_CAMPAIGN_SUFFIX = re.compile(r"[^a-z0-9._-]+")
_CAMPAIGN_ID_PREFIX = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def batch_manifest_path(output_dir: Path, campaign_id_prefix: str) -> Path:
    """Return the non-recipient summary file path for a batch generation."""
    return (output_dir / f"{campaign_id_prefix}-manifest.csv").resolve()


@dataclass(frozen=True, slots=True)
class BatchCampaignScaffold:
    """A generated campaign and its recipient count."""

    scaffold: CampaignScaffold
    recipient_count: int
    from_name: str
    from_email: str


def create_sender_campaigns_from_template_dir(
    *, template_dir: Path, output_dir: Path
) -> list[BatchCampaignScaffold]:
    """Create campaigns using common settings and standard files in a template directory."""
    config_path = template_dir / "campaign.toml"
    if not config_path.is_file():
        raise ValidationError(f"Template configuration not found: {config_path}")
    try:
        with config_path.open("rb") as file:
            raw = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise ValidationError(f"Invalid TOML in {config_path}: {exc}") from exc

    return create_sender_campaigns(
        campaign_id_prefix=_required_config_string(raw, "campaign_id_prefix"),
        name_prefix=_required_config_string(raw, "name"),
        recipients_file=template_dir / "all.csv",
        sender_list_file=template_dir / "sender-list.csv",
        subject_template_file=template_dir / "subject.txt",
        body_template_file=template_dir / "body.txt",
        signature_template_file=None,
        signature_file_column="signature_file",
        signature_root=template_dir,
        template_source_dir=template_dir,
        from_name_column="from_name",
        sender_id_column="sender_id",
        reply_to_list=_config_reply_to_list(raw),
        unsubscribe_group_id=_required_config_int(raw, "unsubscribe_group_id"),
        unsubscribe_url=_optional_config_string(raw, "unsubscribe_url"),
        output_dir=output_dir,
        max_send_count=_required_config_int(raw, "max_send_count"),
        send_interval_seconds=_config_interval(raw),
    )


def create_sender_campaigns(
    *,
    campaign_id_prefix: str,
    name_prefix: str,
    recipients_file: Path,
    sender_list_file: Path,
    subject_template_file: Path,
    body_template_file: Path,
    signature_template_file: Path | None,
    from_name_column: str,
    sender_id_column: str,
    reply_to_list: tuple[str, ...],
    unsubscribe_group_id: int,
    unsubscribe_url: str | None,
    output_dir: Path,
    max_send_count: int,
    send_interval_seconds: float,
    signature_file_column: str | None = None,
    signature_root: Path | None = None,
    template_source_dir: Path | None = None,
) -> list[BatchCampaignScaffold]:
    """Generate isolated campaigns after fully validating source files.

    ``sender_id`` in the recipient CSV must exactly match ``from_name`` in the
    sender list.  This deliberately rejects guesswork around Japanese names.
    """
    subject_template = _read_text(subject_template_file, "Subject")
    body_template = _read_text(body_template_file, "Body")
    if "\n" in subject_template or "\r" in subject_template:
        raise ValidationError("Subject template must contain exactly one line.")
    if "{signature}" in body_template and not (signature_template_file or signature_file_column):
        raise ValidationError("Body template uses {signature}; specify --signature-template-file.")

    recipients, recipient_columns = _read_csv(recipients_file, "Recipient")
    senders, sender_columns = _read_csv(sender_list_file, "Sender list")
    _require_columns(recipient_columns, {"email", sender_id_column}, "Recipient CSV")
    required_sender_columns = {from_name_column, "from_email"}
    if signature_file_column:
        required_sender_columns.add(signature_file_column)
    _require_columns(sender_columns, required_sender_columns, "Sender list CSV")

    sender_map: dict[str, dict[str, str]] = {}
    for row_number, sender in enumerate(senders, start=2):
        sender_name = sender[from_name_column].strip()
        sender_email = sender["from_email"].strip()
        if not sender_name or not sender_email:
            raise ValidationError(
                f"Sender list line {row_number}: sender name and email are required."
            )
        if sender_name in sender_map:
            raise ValidationError(
                f"Sender list contains a duplicate sender name at line {row_number}."
            )
        try:
            validate_sender_settings(
                from_email=sender_email,
                from_name=sender_name,
                reply_to_list=reply_to_list,
                unsubscribe_group_id=unsubscribe_group_id,
            )
        except Exception as exc:
            raise ValidationError(f"Sender list line {row_number}: {exc}") from exc
        sender_map[sender_name] = sender

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row_number, recipient in enumerate(recipients, start=2):
        sender_id = recipient[sender_id_column].strip()
        if not sender_id:
            raise ValidationError(f"Recipient CSV line {row_number}: {sender_id_column} is empty.")
        if sender_id not in sender_map:
            raise ValidationError(
                f"Recipient CSV line {row_number}: assigned sender is not in the sender list."
            )
        grouped[sender_id].append(recipient)

    if not grouped:
        raise ValidationError("Recipient CSV contains no assigned recipients.")

    campaign_id_prefix = campaign_id_prefix.strip()
    name_prefix = name_prefix.strip()
    if not campaign_id_prefix or not name_prefix:
        raise ValidationError("campaign_id_prefix and name_prefix must not be empty.")
    if not _CAMPAIGN_ID_PREFIX.fullmatch(campaign_id_prefix):
        raise ValidationError(
            "campaign_id_prefix must contain only lowercase letters, numbers, '.', '_' or '-'."
        )
    if max_send_count < 1:
        raise ValidationError("max_send_count must be at least 1.")
    if send_interval_seconds < 0:
        raise ValidationError("send_interval_seconds must not be negative.")
    if unsubscribe_url:
        validate_unsubscribe_url(unsubscribe_url)

    manifest_path = batch_manifest_path(output_dir, campaign_id_prefix)
    if manifest_path.exists():
        raise ValidationError(f"Batch manifest already exists: {manifest_path}")
    uses_signature = "signature" in template_fields(body_template)
    sender_signature_files = _sender_signature_files(
        grouped=grouped,
        sender_map=sender_map,
        signature_template_file=signature_template_file,
        signature_file_column=signature_file_column,
        signature_root=signature_root,
    )

    plans: list[tuple[str, dict[str, str], list[dict[str, str]], Path]] = []
    used_suffixes: set[str] = set()
    for sender_name in sorted(grouped):
        sender = sender_map[sender_name]
        suffix = _campaign_suffix(sender["from_email"], used_suffixes)
        directory = (output_dir / f"{campaign_id_prefix}-{suffix}").resolve()
        plans.append((sender_name, sender, grouped[sender_name], directory))

    existing = [directory for _, _, _, directory in plans if directory.exists()]
    if existing:
        raise ValidationError(f"Output directory already exists: {existing[0]}")

    generated: list[BatchCampaignScaffold] = []
    for sender_name, sender, assigned_recipients, directory in plans:
        context = {
            **{
                key.strip(): value.strip()
                for key, value in sender.items()
                if key and key.strip() != "signature"
            },
            "from_name": sender[from_name_column].strip(),
            "from_email": sender["from_email"].strip(),
            "sender_id": sender_name,
        }
        subject = _replace_sender_placeholders(subject_template, context)
        body = _replace_sender_placeholders(body_template, context)

        # Validate all remaining recipient placeholders before files are created.
        sender_signature = _read_text(sender_signature_files[sender_name], "Signature")
        body_for_validation = body.replace("{signature}", sender_signature)
        remaining_fields = template_fields(subject) | template_fields(body_for_validation)
        available_fields = (
            set(recipient_columns)
            | set(sender_columns)
            | {
                "full_name",
                "recipient_block",
                "unsubscribe_url",
            }
        )
        unsupported = sorted(remaining_fields - available_fields)
        if unsupported:
            raise ValidationError(
                "Template contains fields unavailable in the recipient CSV: "
                + ", ".join(unsupported)
            )

        scaffold = create_campaign_scaffold(
            campaign_id=directory.name,
            name=name_prefix,
            recipients_file=recipients_file,
            from_email=context["from_email"],
            from_name=context["from_name"],
            reply_to_list=reply_to_list,
            unsubscribe_group_id=unsubscribe_group_id,
            unsubscribe_url=unsubscribe_url,
            output_dir=directory,
            max_send_count=max_send_count,
            send_interval_seconds=send_interval_seconds,
        )
        recipients_path = scaffold.directory / "recipients.csv"
        _write_csv(recipients_path, recipient_columns, assigned_recipients)
        if uses_signature:
            (scaffold.directory / "signature.txt").write_text(
                sender_signature + "\n", encoding="utf-8"
            )
        config_text = scaffold.config_file.read_text(encoding="utf-8")
        scaffold.config_file.write_text(
            re.sub(
                r'^recipients_file = ".*"$',
                'recipients_file = "recipients.csv"',
                config_text,
                flags=re.M,
            ),
            encoding="utf-8",
        )
        scaffold.subject_file.write_text(subject + "\n", encoding="utf-8")
        scaffold.body_file.write_text(body.rstrip("\r\n") + "\n", encoding="utf-8")
        if template_source_dir:
            write_template_snapshot(
                campaign_dir=scaffold.directory,
                template_dir=template_source_dir,
            )
        generated.append(
            BatchCampaignScaffold(
                scaffold=scaffold,
                recipient_count=len(assigned_recipients),
                from_name=context["from_name"],
                from_email=context["from_email"],
            )
        )
    signature_status = "not_used"
    if uses_signature:
        signature_status = "copied_from_master" if signature_file_column else "requires_replacement"
    _write_manifest(manifest_path, generated, signature_status=signature_status)
    return generated


def _read_text(path: Path, label: str) -> str:
    if not path.is_file():
        raise ValidationError(f"{label} template not found: {path}")
    try:
        value = path.read_text(encoding="utf-8-sig").rstrip("\r\n")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{label} template must be UTF-8 encoded: {path}") from exc
    if not value.strip():
        raise ValidationError(f"{label} template is empty: {path}")
    template_fields(value)
    return value


def _sender_signature_files(
    *,
    grouped: dict[str, list[dict[str, str]]],
    sender_map: dict[str, dict[str, str]],
    signature_template_file: Path | None,
    signature_file_column: str | None,
    signature_root: Path | None,
) -> dict[str, Path]:
    if signature_template_file is None and (not signature_file_column or signature_root is None):
        return {sender_name: Path() for sender_name in grouped}
    if not signature_file_column:
        assert signature_template_file is not None
        return {sender_name: signature_template_file for sender_name in grouped}

    root = (signature_root or signature_template_file.parent).resolve()
    files: dict[str, Path] = {}
    for sender_name in grouped:
        value = sender_map[sender_name][signature_file_column].strip()
        if not value:
            raise ValidationError(f"Sender {sender_name}: {signature_file_column} is empty.")
        path = (root / value).resolve()
        if root not in path.parents or not path.is_file():
            raise ValidationError(
                f"Sender {sender_name}: signature file is missing or outside "
                "the template directory."
            )
        files[sender_name] = path
    return files


def _required_config_string(raw: dict[str, object], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"Template configuration {name} must be a non-empty string.")
    return value.strip()


def _optional_config_string(raw: dict[str, object], name: str) -> str | None:
    value = raw.get(name, "")
    if not isinstance(value, str):
        raise ValidationError(f"Template configuration {name} must be a string.")
    return value.strip() or None


def _required_config_int(raw: dict[str, object], name: str) -> int:
    value = raw.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationError(f"Template configuration {name} must be an integer.")
    return value


def _config_reply_to_list(raw: dict[str, object]) -> tuple[str, ...]:
    value = raw.get("reply_to_list", [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValidationError(
            "Template configuration reply_to_list must be an email address array."
        )
    return tuple(value)


def _config_interval(raw: dict[str, object]) -> float:
    value = raw.get("send_interval_seconds", 1.0)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValidationError("Template configuration send_interval_seconds must be a number.")
    return float(value)


def _read_csv(path: Path, label: str) -> tuple[list[dict[str, str]], list[str]]:
    if not path.is_file():
        raise ValidationError(f"{label} CSV not found: {path}")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None:
                raise ValidationError(f"{label} CSV has no header: {path}")
            columns = [column.strip() for column in reader.fieldnames if column and column.strip()]
            return [dict(row) for row in reader], columns
    except UnicodeDecodeError as exc:
        raise ValidationError(f"{label} CSV must be UTF-8 encoded: {path}") from exc


def _require_columns(columns: list[str], required: set[str], label: str) -> None:
    missing = sorted(required - set(columns))
    if missing:
        raise ValidationError(f"{label} is missing required columns: {', '.join(missing)}")


def _replace_sender_placeholders(template: str, context: dict[str, str]) -> str:
    result = template
    for key, value in context.items():
        result = result.replace("{" + key + "}", value)
    return result


def _campaign_suffix(email: str, used_suffixes: set[str]) -> str:
    local_part, separator, _ = email.strip().lower().partition("@")
    if not separator:
        raise ValidationError("Sender email must contain '@'.")
    base = _CAMPAIGN_SUFFIX.sub("-", local_part).strip("-.")
    if not base:
        raise ValidationError("Sender email cannot be converted to a campaign ID suffix.")
    suffix = base
    number = 2
    while suffix in used_suffixes:
        suffix = f"{base}-{number}"
        number += 1
    used_suffixes.add(suffix)
    return suffix


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_manifest(
    path: Path,
    generated: list[BatchCampaignScaffold],
    *,
    signature_status: str,
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["campaign_id", "from_name", "from_email", "recipient_count", "signature_status"]
        )
        for item in generated:
            writer.writerow(
                [
                    item.scaffold.directory.name,
                    item.from_name,
                    item.from_email,
                    item.recipient_count,
                    signature_status,
                ]
            )
