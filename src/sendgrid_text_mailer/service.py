"""Application orchestration for validation, preview, test, and sending."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import load_campaign
from .database import DeliveryDatabase
from .errors import SendInterrupted, ValidationError
from .mailer import SendGridGateway, prepare_attachments
from .models import AppConfig, Campaign, PreparedAttachment, RenderedMessage
from .progress import DeliveryProgress
from .recipients import load_recipients, normalize_email
from .template import render_messages


@dataclass(frozen=True, slots=True)
class PreparedCampaign:
    campaign: Campaign
    messages: list[RenderedMessage]
    attachments: tuple[PreparedAttachment, ...] = ()


@dataclass(slots=True)
class DeliveryPlan:
    database: DeliveryDatabase
    gateway: SendGridGateway
    targets: list[RenderedMessage]
    skipped_items: list[tuple[RenderedMessage, str]]
    suppression_count: int


def prepare_campaign(campaign_dir: Path) -> PreparedCampaign:
    campaign = load_campaign(campaign_dir)
    recipients = load_recipients(campaign.recipients_file)
    messages = render_messages(campaign, recipients)
    if len(messages) > campaign.max_send_count:
        raise ValidationError(
            f"Recipient count {len(messages)} exceeds max_send_count ({campaign.max_send_count})."
        )
    attachments = prepare_attachments(campaign.attachment_files)
    return PreparedCampaign(
        campaign=campaign,
        messages=messages,
        attachments=attachments,
    )


def filter_send_targets(
    prepared: PreparedCampaign,
    *,
    database: DeliveryDatabase,
    unsubscribed: set[str],
) -> tuple[list[RenderedMessage], list[tuple[RenderedMessage, str]]]:
    already_sent = database.already_sent(prepared.campaign.campaign_id)
    targets: list[RenderedMessage] = []
    skipped: list[tuple[RenderedMessage, str]] = []

    for message in prepared.messages:
        email = normalize_email(message.recipient.email)
        if email in unsubscribed:
            skipped.append((message, "skipped_unsubscribed"))
        elif email in already_sent:
            skipped.append((message, "skipped_already_sent"))
        else:
            targets.append(message)
    return targets, skipped


def prepare_delivery(
    prepared: PreparedCampaign,
    *,
    config: AppConfig,
) -> DeliveryPlan:
    """Retrieve suppressions and calculate the exact production delivery targets."""
    database = DeliveryDatabase(config.database_path)
    gateway = SendGridGateway(config)
    unsubscribed = gateway.get_unsubscribed_emails()
    targets, skipped_items = filter_send_targets(
        prepared, database=database, unsubscribed=unsubscribed
    )
    return DeliveryPlan(
        database=database,
        gateway=gateway,
        targets=targets,
        skipped_items=skipped_items,
        suppression_count=len(unsubscribed),
    )


def send_campaign(
    prepared: PreparedCampaign,
    *,
    config: AppConfig,
    mode: str,
    test_address: str | None = None,
    delivery_plan: DeliveryPlan | None = None,
    progress_callback: Callable[[DeliveryProgress], None] | None = None,
) -> tuple[str, int, int, int]:
    if mode == "test":
        database = DeliveryDatabase(config.database_path)
        gateway = SendGridGateway(config)
        gateway.get_unsubscribed_emails()
        if not test_address:
            raise ValidationError("A test recipient address is required.")
        source = prepared.messages[0]
        test_message = RenderedMessage(
            recipient=source.recipient.__class__(
                email=normalize_email(test_address), fields=source.recipient.fields
            ),
            subject=f"[TEST] {source.subject}",
            body=source.body,
        )
        targets = [test_message]
        skipped_items: list[tuple[RenderedMessage, str]] = []
    else:
        plan = delivery_plan or prepare_delivery(prepared, config=config)
        database = plan.database
        gateway = plan.gateway
        targets = plan.targets
        skipped_items = plan.skipped_items

    run_id = str(uuid.uuid4())
    database.start_run(
        run_id,
        prepared.campaign.campaign_id,
        mode,
        len(targets) + len(skipped_items),
    )
    for message, status in skipped_items:
        database.record_delivery(
            run_id=run_id,
            campaign_id=prepared.campaign.campaign_id,
            email=message.recipient.email,
            status=status,
        )

    sent = 0
    failed = 0
    started_at = time.monotonic()
    try:
        for index, message in enumerate(targets):
            try:
                result = gateway.send(message, prepared.attachments)
            except Exception as exc:
                failed += 1
                database.record_delivery(
                    run_id=run_id,
                    campaign_id=prepared.campaign.campaign_id,
                    email=message.recipient.email,
                    status="failed",
                    error_message=str(exc),
                )
                event = "failure"
            else:
                sent += 1
                database.record_delivery(
                    run_id=run_id,
                    campaign_id=prepared.campaign.campaign_id,
                    email=message.recipient.email,
                    status="sent",
                    response_status=result.status_code,
                    message_id=result.message_id,
                )
                event = "complete" if index == len(targets) - 1 else "progress"
            if progress_callback:
                progress_callback(
                    DeliveryProgress(
                        total=len(targets),
                        completed=index + 1,
                        sent=sent,
                        failed=failed,
                        elapsed_seconds=time.monotonic() - started_at,
                        event=event,
                    )
                )
            if index < len(targets) - 1 and prepared.campaign.send_interval_seconds:
                time.sleep(prepared.campaign.send_interval_seconds)
    except KeyboardInterrupt as exc:
        if progress_callback:
            progress_callback(
                DeliveryProgress(
                    total=len(targets),
                    completed=sent + failed,
                    sent=sent,
                    failed=failed,
                    elapsed_seconds=time.monotonic() - started_at,
                    event="interrupted",
                )
            )
        database.finish_run(
            run_id,
            sent=sent,
            failed=failed,
            skipped=len(skipped_items),
            status="interrupted",
        )
        raise SendInterrupted("Sending was interrupted by the operator.") from exc
    except BaseException:
        # A forced termination can leave the run as "running". Do not label it complete.
        raise
    else:
        database.finish_run(
            run_id,
            sent=sent,
            failed=failed,
            skipped=len(skipped_items),
        )
    return run_id, sent, failed, len(skipped_items)
