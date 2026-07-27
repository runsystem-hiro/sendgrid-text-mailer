"""Command-line interface."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import load_app_config
from .database import DeliveryDatabase
from .errors import MailerError, ValidationError
from .service import prepare_campaign, send_campaign


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sendgrid-text-mailer",
        description="Safely send personalized plain-text email through SendGrid.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command, help_text in (
        ("validate", "Validate campaign files without contacting SendGrid."),
        ("preview", "Render and display sample messages without sending."),
    ):
        subparser = subparsers.add_parser(command, help=help_text)
        subparser.add_argument("--campaign", type=Path, required=True)
        if command == "preview":
            subparser.add_argument("--limit", type=int, default=3)

    test_parser = subparsers.add_parser("test", help="Send one test message.")
    test_parser.add_argument("--campaign", type=Path, required=True)
    test_parser.add_argument("--to", required=True)
    test_parser.add_argument("--confirm", required=True, choices=["TEST"])

    send_parser = subparsers.add_parser("send", help="Send the campaign.")
    send_parser.add_argument("--campaign", type=Path, required=True)
    send_parser.add_argument("--confirm", required=True, choices=["SEND"])

    history_parser = subparsers.add_parser("history", help="Show recent delivery runs.")
    history_parser.add_argument("--limit", type=int, default=20)

    return parser


def _print_summary(prepared) -> None:
    campaign = prepared.campaign
    print(f"Campaign ID : {campaign.campaign_id}")
    print(f"Name        : {campaign.name}")
    print(f"Recipients  : {len(prepared.messages)}")
    print(f"Maximum     : {campaign.max_send_count}")
    print(f"Interval    : {campaign.send_interval_seconds:.2f} seconds")


def command_validate(args: argparse.Namespace) -> int:
    prepared = prepare_campaign(args.campaign)
    _print_summary(prepared)
    print("Validation successful.")
    return 0


def command_preview(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        raise ValidationError("--limit must be greater than zero.")
    prepared = prepare_campaign(args.campaign)
    _print_summary(prepared)
    for index, message in enumerate(prepared.messages[: args.limit], start=1):
        print("\n" + "=" * 72)
        print(f"Preview {index}/{min(args.limit, len(prepared.messages))}")
        print(f"To      : {message.recipient.email}")
        print(f"Subject : {message.subject}")
        print("-" * 72)
        print(message.body)
    return 0


def command_test(args: argparse.Namespace) -> int:
    prepared = prepare_campaign(args.campaign)
    config = load_app_config()
    assert config is not None
    run_id, sent, failed, skipped = send_campaign(
        prepared,
        config=config,
        mode="test",
        test_address=args.to,
    )
    print(f"Run ID  : {run_id}")
    print(f"Sent    : {sent}")
    print(f"Failed  : {failed}")
    print(f"Skipped : {skipped}")
    return 1 if failed else 0


def command_send(args: argparse.Namespace) -> int:
    prepared = prepare_campaign(args.campaign)
    config = load_app_config()
    assert config is not None
    _print_summary(prepared)
    run_id, sent, failed, skipped = send_campaign(prepared, config=config, mode="send")
    print(f"Run ID  : {run_id}")
    print(f"Sent    : {sent}")
    print(f"Failed  : {failed}")
    print(f"Skipped : {skipped}")
    return 1 if failed else 0


def command_history(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        raise ValidationError("--limit must be greater than zero.")
    load_dotenv()
    database_path = Path(
        os.getenv("MAILER_DATABASE_PATH", "data/sendgrid-text-mailer.sqlite3")
    )
    rows = DeliveryDatabase(database_path).recent_runs(args.limit)
    if not rows:
        print("No delivery history found.")
        return 0
    print("STARTED_AT                MODE  CAMPAIGN                 TOTAL SENT FAIL SKIP RUN_ID")
    for row in rows:
        print(
            f"{row['started_at']:<25} {row['mode']:<5} "
            f"{row['campaign_id'][:24]:<24} {row['total_count']:>5} "
            f"{row['sent_count']:>4} {row['failed_count']:>4} "
            f"{row['skipped_count']:>4} {row['run_id']}"
        )
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "validate": command_validate,
        "preview": command_preview,
        "test": command_test,
        "send": command_send,
        "history": command_history,
    }
    try:
        exit_code = handlers[args.command](args)
    except MailerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        exit_code = 2
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
