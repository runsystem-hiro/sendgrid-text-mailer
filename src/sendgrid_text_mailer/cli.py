"""Command-line interface."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from .batch_scaffold import (
    batch_manifest_path,
    create_sender_campaigns,
    create_sender_campaigns_from_template_dir,
)
from .config import delivery_config, load_app_config
from .database import DeliveryDatabase
from .errors import MailerError, SendInterrupted, ValidationError
from .models import AppConfig
from .progress import ConsoleProgressReporter
from .scaffold import create_campaign_scaffold
from .service import prepare_campaign, prepare_delivery, send_campaign

SAFE_EXPORT_CAMPAIGN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sendgrid-text-mailer",
        description="Safely send personalized plain-text email through SendGrid.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    campaign_parser = subparsers.add_parser("campaign", help="Create and manage campaign files.")
    campaign_subparsers = campaign_parser.add_subparsers(dest="campaign_command", required=True)
    create_parser = campaign_subparsers.add_parser("create", help="Create a new campaign scaffold.")
    create_parser.add_argument("--campaign-id", required=True)
    create_parser.add_argument("--name", required=True)
    create_parser.add_argument("--recipients-file", type=Path, required=True)
    create_parser.add_argument("--unsubscribe-url")
    create_parser.add_argument("--from-email", required=True)
    create_parser.add_argument("--from-name", required=True)
    create_parser.add_argument("--reply-to", action="append", default=[])
    create_parser.add_argument("--unsubscribe-group-id", type=int, required=True)
    create_parser.add_argument("--output", type=Path)
    create_parser.add_argument("--max-send-count", type=int, default=500)
    create_parser.add_argument("--send-interval-seconds", type=float, default=1.0)
    from_template_parser = campaign_subparsers.add_parser(
        "create-from-template",
        help="Create one campaign per assigned sender from CSV and text templates.",
    )
    from_template_parser.add_argument("--campaign-id-prefix", required=True)
    from_template_parser.add_argument("--name-prefix", required=True)
    from_template_parser.add_argument("--recipients-file", type=Path, required=True)
    from_template_parser.add_argument("--sender-list-file", type=Path, required=True)
    from_template_parser.add_argument("--subject-template-file", type=Path, required=True)
    from_template_parser.add_argument("--body-template-file", type=Path, required=True)
    from_template_parser.add_argument("--signature-template-file", type=Path)
    from_template_parser.add_argument("--sender-id-column", default="sender_id")
    from_template_parser.add_argument("--from-name-column", default="from_name")
    from_template_parser.add_argument("--reply-to", action="append", default=[])
    from_template_parser.add_argument("--unsubscribe-group-id", type=int, required=True)
    from_template_parser.add_argument("--unsubscribe-url")
    from_template_parser.add_argument("--output", type=Path, default=Path("campaigns"))
    from_template_parser.add_argument("--max-send-count", type=int, required=True)
    from_template_parser.add_argument("--send-interval-seconds", type=float, default=1.0)
    from_template_dir_parser = campaign_subparsers.add_parser(
        "create-from-template-dir",
        help="Create campaigns using common settings in a template directory campaign.toml.",
    )
    from_template_dir_parser.add_argument("--template-dir", type=Path, required=True)
    from_template_dir_parser.add_argument("--output", type=Path, default=Path("campaigns"))

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
    history_parser.add_argument(
        "--campaign-id",
        help="Filter by a campaign.toml campaign_id, including its test runs.",
    )
    history_subparsers = history_parser.add_subparsers(dest="history_command")
    export_parser = history_subparsers.add_parser(
        "export", help="Export successful SendGrid message IDs to CSV."
    )
    export_parser.add_argument("--campaign-id", required=True)
    export_parser.add_argument("--mode", choices=["send", "test"], default="send")
    export_parser.add_argument("--output", type=Path)
    export_parser.add_argument("--force", action="store_true")

    return parser


def _print_summary(prepared) -> None:
    campaign = prepared.campaign
    print(f"Campaign ID : {campaign.campaign_id}")
    print(f"Name        : {campaign.name}")
    print(f"Recipients  : {len(prepared.messages)}")
    print(f"Maximum     : {campaign.max_send_count}")
    print(f"Interval    : {campaign.send_interval_seconds:.2f} seconds")
    if campaign.attachment_files:
        print("Attachments:")
        for path in campaign.attachment_files:
            print(f"  - {path.name} ({path.stat().st_size / (1024 * 1024):.1f} MB)")


def command_campaign(args: argparse.Namespace) -> int:
    if args.campaign_command == "create-from-template-dir":
        generated = create_sender_campaigns_from_template_dir(
            template_dir=args.template_dir,
            output_dir=args.output,
        )
        config_path = args.template_dir / "campaign.toml"
        print(f"Template config    : {config_path}")
        print(f"Campaigns created : {len(generated)}")
        print(f"Recipients        : {sum(item.recipient_count for item in generated)}")
        print("Next step         : replace each signature.txt, then validate and preview.")
        return 0
    if args.campaign_command == "create-from-template":
        generated = create_sender_campaigns(
            campaign_id_prefix=args.campaign_id_prefix,
            name_prefix=args.name_prefix,
            recipients_file=args.recipients_file,
            sender_list_file=args.sender_list_file,
            subject_template_file=args.subject_template_file,
            body_template_file=args.body_template_file,
            signature_template_file=args.signature_template_file,
            from_name_column=args.from_name_column,
            sender_id_column=args.sender_id_column,
            reply_to_list=tuple(args.reply_to),
            unsubscribe_group_id=args.unsubscribe_group_id,
            unsubscribe_url=args.unsubscribe_url,
            output_dir=args.output,
            max_send_count=args.max_send_count,
            send_interval_seconds=args.send_interval_seconds,
            signature_file_column=None,
            signature_root=None,
            template_source_dir=None,
        )
        print(f"Campaigns created: {len(generated)}")
        print(f"Recipients        : {sum(item.recipient_count for item in generated)}")
        print(f"Batch manifest    : {batch_manifest_path(args.output, args.campaign_id_prefix)}")
        for item in generated:
            print(f"  - {item.scaffold.directory} ({item.recipient_count} recipients)")
        print("Next step         : validate and preview every generated campaign before sending.")
        return 0
    if args.campaign_command != "create":
        raise ValidationError(f"Unknown campaign command: {args.campaign_command}")
    scaffold = create_campaign_scaffold(
        campaign_id=args.campaign_id,
        name=args.name,
        recipients_file=args.recipients_file,
        unsubscribe_url=args.unsubscribe_url,
        from_email=args.from_email,
        from_name=args.from_name,
        reply_to_list=tuple(args.reply_to),
        unsubscribe_group_id=args.unsubscribe_group_id,
        output_dir=args.output,
        max_send_count=args.max_send_count,
        send_interval_seconds=args.send_interval_seconds,
    )
    print(f"Campaign created: {scaffold.directory}")
    print(f"Configuration   : {scaffold.config_file}")
    print(f"Subject         : {scaffold.subject_file}")
    print(f"Body            : {scaffold.body_file}")
    print("Next step       : edit subject.txt and body.txt, then run validate.")
    return 0


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
    runtime = load_app_config()
    assert runtime is not None
    config = delivery_config(runtime, prepared.campaign)
    _print_delivery_settings(config)
    run_id, sent, failed, skipped = send_campaign(
        prepared,
        config=config,
        mode="test",
        test_address=args.to,
        progress_callback=ConsoleProgressReporter(
            send_interval_seconds=prepared.campaign.send_interval_seconds
        ),
    )
    print(f"Run ID  : {run_id}")
    print(f"Sent    : {sent}")
    print(f"Failed  : {failed}")
    print(f"Skipped : {skipped}")
    return 1 if failed else 0


def command_send(args: argparse.Namespace) -> int:
    prepared = prepare_campaign(args.campaign)
    runtime = load_app_config()
    assert runtime is not None
    config = delivery_config(runtime, prepared.campaign)
    _print_summary(prepared)
    _print_delivery_settings(config)
    plan = prepare_delivery(prepared, config=config)
    print("Sender      : verified (fail closed)")
    print(f"Suppressed  : {plan.suppression_count}")
    print(f"Eligible    : {len(plan.targets)}")
    print(f"Skipped     : {len(plan.skipped_items)}")
    print("Suppression : verified (fail closed)")
    run_id, sent, failed, skipped = send_campaign(
        prepared,
        config=config,
        mode="send",
        delivery_plan=plan,
        progress_callback=ConsoleProgressReporter(
            send_interval_seconds=prepared.campaign.send_interval_seconds
        ),
    )
    print(f"Run ID  : {run_id}")
    print(f"Sent    : {sent}")
    print(f"Failed  : {failed}")
    print(f"Skipped : {skipped}")
    return 1 if failed else 0


def _print_delivery_settings(config: AppConfig) -> None:
    print(f"From        : {config.from_name} <{config.from_email}>")
    if config.reply_to_list:
        print(f"Reply-To    : {', '.join(config.reply_to_list)}")
    else:
        print("Reply-To    : not set (replies go to the From address)")
    print(f"Group ID    : {config.unsubscribe_group_id}")


def _history_database_path() -> Path:
    load_dotenv()
    return Path(os.getenv("MAILER_DATABASE_PATH", "data/sendgrid-text-mailer.sqlite3"))


def _default_message_id_export_path(campaign_id: str, mode: str) -> Path:
    if not SAFE_EXPORT_CAMPAIGN_ID.fullmatch(campaign_id):
        raise ValidationError(
            "campaign_id must use only ASCII letters, digits, '.', '_', or '-' "
            "to create the default CSV filename. Use --output to choose another path."
        )
    prefix = "test-" if mode == "test" else ""
    return Path("data") / f"{prefix}{campaign_id}-ids.csv"


def command_history_export(args: argparse.Namespace) -> int:
    output_path = args.output or _default_message_id_export_path(args.campaign_id, args.mode)
    if output_path.exists() and not args.force:
        raise ValidationError(
            f"Output file already exists: {output_path}. Use --force to overwrite it."
        )

    database_path = _history_database_path()
    if not database_path.is_file():
        raise ValidationError(f"Delivery history database not found: {database_path}")
    rows = DeliveryDatabase(database_path).message_id_rows(args.campaign_id, args.mode)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["campaign_id", "recipient_email", "message_id"])
        writer.writerows(
            (row["campaign_id"], row["recipient_email"], row["message_id"]) for row in rows
        )
    print(f"Message ID CSV: {output_path}")
    print(f"Rows          : {len(rows)}")
    return 0


def command_history(args: argparse.Namespace) -> int:
    if args.history_command == "export":
        return command_history_export(args)
    if args.limit <= 0:
        raise ValidationError("--limit must be greater than zero.")
    database_path = _history_database_path()
    rows = DeliveryDatabase(database_path).recent_runs(args.limit, campaign_id=args.campaign_id)
    if not rows:
        print("No delivery history found.")
        return 0
    print(
        "STARTED_AT                MODE  STATUS       CAMPAIGN                 "
        "TOTAL SENT FAIL SKIP RUN_ID"
    )
    for row in rows:
        print(
            f"{row['started_at']:<25} {row['mode']:<5} {row['status']:<12} "
            f"{row['campaign_id'][:24]:<24} {row['total_count']:>5} "
            f"{row['sent_count']:>4} {row['failed_count']:>4} "
            f"{row['skipped_count']:>4} {row['run_id']}"
        )
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "campaign": command_campaign,
        "validate": command_validate,
        "preview": command_preview,
        "test": command_test,
        "send": command_send,
        "history": command_history,
    }
    try:
        exit_code = handlers[args.command](args)
    except SendInterrupted:
        exit_code = 130
    except MailerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        exit_code = 2
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
