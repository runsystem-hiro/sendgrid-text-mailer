import argparse
from pathlib import Path

from sendgrid_text_mailer import __version__
from sendgrid_text_mailer.database import DeliveryDatabase


def test_version() -> None:
    assert __version__ == "0.6.0"


def test_campaign_create_parser() -> None:
    from sendgrid_text_mailer.cli import build_parser

    args = build_parser().parse_args(
        [
            "campaign",
            "create",
            "--campaign-id",
            "sample-1",
            "--name",
            "Sample",
            "--recipients-file",
            "data/recipients.csv",
            "--from-email",
            "sender@example.com",
            "--from-name",
            "Example Sender",
            "--reply-to",
            "reply@example.com",
            "--unsubscribe-group-id",
            "12345",
        ]
    )

    assert args.command == "campaign"
    assert args.campaign_command == "create"
    assert args.campaign_id == "sample-1"
    assert args.unsubscribe_url is None
    assert args.from_email == "sender@example.com"
    assert args.reply_to == ["reply@example.com"]


def test_campaign_create_from_template_parser() -> None:
    from sendgrid_text_mailer.cli import build_parser

    args = build_parser().parse_args(
        [
            "campaign",
            "create-from-template",
            "--campaign-id-prefix",
            "expo-thanks-2026",
            "--name-prefix",
            "Expo Thanks",
            "--recipients-file",
            "data/all.csv",
            "--sender-list-file",
            "data/senders.csv",
            "--subject-template-file",
            "data/subject.txt",
            "--body-template-file",
            "data/body.txt",
            "--unsubscribe-group-id",
            "12345",
            "--max-send-count",
            "100",
        ]
    )

    assert args.campaign_command == "create-from-template"
    assert args.sender_id_column == "sender_id"
    assert args.from_name_column == "from_name"
    assert args.max_send_count == 100


def test_campaign_create_from_template_dir_parser() -> None:
    from sendgrid_text_mailer.cli import build_parser

    args = build_parser().parse_args(
        ["campaign", "create-from-template-dir", "--template-dir", "data/thanksmail-template"]
    )

    assert args.campaign_command == "create-from-template-dir"
    assert args.template_dir.as_posix() == "data/thanksmail-template"


def test_history_parser_accepts_campaign_id() -> None:
    from sendgrid_text_mailer.cli import build_parser

    args = build_parser().parse_args(["history", "--campaign-id", "campaign-1", "--limit", "5"])

    assert args.campaign_id == "campaign-1"
    assert args.limit == 5


def test_history_export_parser_uses_safe_defaults() -> None:
    from sendgrid_text_mailer.cli import build_parser

    args = build_parser().parse_args(["history", "export", "--campaign-id", "campaign-1"])

    assert args.history_command == "export"
    assert args.campaign_id == "campaign-1"
    assert args.mode == "send"
    assert args.output is None
    assert args.force is False


def test_history_shows_privacy_safe_exclusion_reason_counts(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    database_path = tmp_path / "mailer.sqlite3"
    database = DeliveryDatabase(database_path)
    database.start_run("run-1", "campaign-1", "send", 3)
    for email, status in (
        ("group@example.com", "skipped_unsubscribed_group"),
        ("global@example.com", "skipped_unsubscribed_global"),
        ("both@example.com", "skipped_unsubscribed_both"),
    ):
        database.record_delivery(
            run_id="run-1", campaign_id="campaign-1", email=email, status=status
        )
    database.finish_run("run-1", sent=0, failed=0, skipped=3)

    monkeypatch.setattr("sendgrid_text_mailer.cli._history_database_path", lambda: database_path)
    from sendgrid_text_mailer.cli import command_history

    args = argparse.Namespace(history_command=None, limit=20, campaign_id=None)
    assert command_history(args) == 0
    output = capsys.readouterr().out

    assert "GROUP GLOBAL BOTH LEGACY" in output
    assert "group@example.com" not in output
    assert "global@example.com" not in output
    assert "both@example.com" not in output
