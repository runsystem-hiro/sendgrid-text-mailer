"""Detect generated campaigns that are stale against their source template directory."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .errors import ValidationError

TEMPLATE_SYNC_FILENAME = ".template-source.json"
_SOURCE_FILENAMES = ("campaign.toml", "all.csv", "sender-list.csv", "subject.txt", "body.txt")


def write_template_snapshot(*, campaign_dir: Path, template_dir: Path) -> None:
    """Store a relative template path and fingerprint in a generated campaign."""
    source = template_dir.resolve()
    snapshot = {
        "template_dir": os.path.relpath(source, start=campaign_dir.resolve()),
        "fingerprint": template_fingerprint(source),
    }
    (campaign_dir / TEMPLATE_SYNC_FILENAME).write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_template_snapshot(campaign_dir: Path) -> None:
    """Reject a generated campaign when any template input changed after generation."""
    snapshot_path = campaign_dir / TEMPLATE_SYNC_FILENAME
    if not snapshot_path.is_file():
        return
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        relative_dir = snapshot["template_dir"]
        expected_fingerprint = snapshot["fingerprint"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValidationError(f"Invalid template sync metadata: {snapshot_path}") from exc
    if not isinstance(relative_dir, str) or not isinstance(expected_fingerprint, str):
        raise ValidationError(f"Invalid template sync metadata: {snapshot_path}")

    template_dir = (campaign_dir / relative_dir).resolve()
    if not template_dir.is_dir():
        raise ValidationError(
            f"Template directory for this campaign is not available: {template_dir}. "
            "Regenerate the campaign."
        )
    if template_fingerprint(template_dir) != expected_fingerprint:
        raise ValidationError(
            "Template inputs changed after this campaign was generated. "
            "Regenerate the campaign before validation or sending."
        )


def template_fingerprint(template_dir: Path) -> str:
    """Hash all common template inputs and all managed signature masters."""
    files = [template_dir / name for name in _SOURCE_FILENAMES]
    signatures_dir = template_dir / "signatures"
    if signatures_dir.is_dir():
        files.extend(sorted(path for path in signatures_dir.rglob("*.txt") if path.is_file()))

    digest = hashlib.sha256()
    for path in files:
        if not path.is_file():
            raise ValidationError(f"Template input file not found: {path}")
        relative_path = path.relative_to(template_dir).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
