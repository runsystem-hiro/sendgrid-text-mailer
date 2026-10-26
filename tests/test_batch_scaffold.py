from pathlib import Path

import pytest

from sendgrid_text_mailer.batch_scaffold import (
    create_sender_campaigns,
    create_sender_campaigns_from_template_dir,
)
from sendgrid_text_mailer.config import load_campaign
from sendgrid_text_mailer.errors import ValidationError
from sendgrid_text_mailer.service import prepare_campaign


def write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def create_templates(tmp_path: Path) -> tuple[Path, Path, Path]:
    return (
        write(tmp_path / "subject.txt", "{from_name}より {company}様へ\n"),
        write(tmp_path / "body.txt", "{recipient_block}\n\n{from_name}です。\n{signature}\n"),
        write(tmp_path / "signature.txt", "Example signature\n"),
    )


def test_create_sender_campaigns_splits_recipients_and_renders_sender_data(tmp_path: Path) -> None:
    recipients = write(
        tmp_path / "recipients.csv",
        "email,last_name,first_name,company,sender_id\n"
        "one@example.com,One,User,Example One,Alice Sales\n"
        "two@example.com,Two,User,Example Two,Bob Sales\n",
    )
    senders = write(
        tmp_path / "senders.csv",
        "from_name,from_email\nAlice Sales,alice@example.com\nBob Sales,bob@example.com\n",
    )
    subject, body, signature = create_templates(tmp_path)

    created = create_sender_campaigns(
        campaign_id_prefix="expo-thanks-2026",
        name_prefix="Expo Thanks",
        recipients_file=recipients,
        sender_list_file=senders,
        subject_template_file=subject,
        body_template_file=body,
        signature_template_file=signature,
        from_name_column="from_name",
        sender_id_column="sender_id",
        reply_to_list=(),
        unsubscribe_group_id=12345,
        unsubscribe_url=None,
        output_dir=tmp_path / "campaigns",
        max_send_count=1,
        send_interval_seconds=0,
    )

    assert len(created) == 2
    assert sorted(item.recipient_count for item in created) == [1, 1]
    assert {item.scaffold.directory.name for item in created} == {
        "expo-thanks-2026-alice",
        "expo-thanks-2026-bob",
    }
    for item in created:
        (item.scaffold.directory / "signature.txt").write_text(
            f"Approved signature\n{item.from_name}\n", encoding="utf-8"
        )
    prepared = [prepare_campaign(item.scaffold.directory) for item in created]
    assert {item.campaign.name for item in prepared} == {"Expo Thanks"}
    assert {item.campaign.from_email for item in prepared} == {
        "alice@example.com",
        "bob@example.com",
    }
    assert {item.messages[0].subject for item in prepared} == {
        "Alice Salesより Example One様へ",
        "Bob Salesより Example Two様へ",
    }
    assert all("{signature}" not in item.messages[0].body for item in prepared)
    assert all(item.campaign.signature_file is not None for item in prepared)
    assert {item.messages[0].body.splitlines()[-1] for item in prepared} == {
        "Alice Sales",
        "Bob Sales",
    }
    manifest = tmp_path / "campaigns" / "expo-thanks-2026-manifest.csv"
    assert manifest.is_file()
    assert "requires_replacement" in manifest.read_text(encoding="utf-8-sig")


def test_create_sender_campaigns_rejects_unlisted_assignment_before_creating_files(
    tmp_path: Path,
) -> None:
    recipients = write(
        tmp_path / "recipients.csv",
        "email,sender_id\nuser@example.com,Unknown Sender\n",
    )
    senders = write(
        tmp_path / "senders.csv",
        "from_name,from_email\nKnown Sender,known@example.com\n",
    )
    subject, body, signature = create_templates(tmp_path)

    with pytest.raises(ValidationError, match="not in the sender list"):
        create_sender_campaigns(
            campaign_id_prefix="expo-thanks-2026",
            name_prefix="Expo Thanks",
            recipients_file=recipients,
            sender_list_file=senders,
            subject_template_file=subject,
            body_template_file=body,
            signature_template_file=signature,
            from_name_column="from_name",
            sender_id_column="sender_id",
            reply_to_list=(),
            unsubscribe_group_id=12345,
            unsubscribe_url=None,
            output_dir=tmp_path / "campaigns",
            max_send_count=1,
            send_interval_seconds=0,
        )

    assert not (tmp_path / "campaigns").exists()


def test_create_sender_campaigns_uses_sender_reply_to_or_template_fallback(tmp_path: Path) -> None:
    recipients = write(
        tmp_path / "recipients.csv",
        "email,sender_id,company\n"
        "user-one@example.com,Alice Sales,Example One\n"
        "user-two@example.com,Bob Sales,Example Two\n",
    )
    senders = write(
        tmp_path / "senders.csv",
        "from_name,from_email,reply_to_list\n"
        "Alice Sales,alice@example.com,alice@example.com;team@example.com\n"
        "Bob Sales,bob@example.com,\n",
    )
    subject, body, signature = create_templates(tmp_path)

    created = create_sender_campaigns(
        campaign_id_prefix="expo-thanks-2026",
        name_prefix="Expo Thanks",
        recipients_file=recipients,
        sender_list_file=senders,
        subject_template_file=subject,
        body_template_file=body,
        signature_template_file=signature,
        from_name_column="from_name",
        sender_id_column="sender_id",
        reply_to_list=("shared@example.com",),
        unsubscribe_group_id=12345,
        unsubscribe_url=None,
        output_dir=tmp_path / "campaigns",
        max_send_count=1,
        send_interval_seconds=0,
    )

    campaigns = {item.from_email: load_campaign(item.scaffold.directory) for item in created}
    assert campaigns["alice@example.com"].reply_to_list == (
        "alice@example.com",
        "team@example.com",
    )
    assert campaigns["bob@example.com"].reply_to_list == ("shared@example.com",)


def test_create_sender_campaigns_from_template_dir_uses_signature_master(tmp_path: Path) -> None:
    template_dir = tmp_path / "template"
    signatures_dir = template_dir / "signatures"
    signatures_dir.mkdir(parents=True)
    write(
        template_dir / "campaign.toml",
        'campaign_id_prefix = "expo-thanks"\n'
        'name = "Expo Thanks"\n'
        "reply_to_list = []\n"
        "unsubscribe_group_id = 12345\n"
        "max_send_count = 1\n",
    )
    write(
        template_dir / "all.csv",
        "email,company,sender_id\nuser@example.com,Example,Alice Sales\n",
    )
    write(
        template_dir / "sender-list.csv",
        "from_name,from_email,signature_file\nAlice Sales,alice@example.com,signatures/alice.txt\n",
    )
    write(template_dir / "subject.txt", "{from_name}より\n")
    write(template_dir / "body.txt", "{recipient_block}\n{signature}\n")
    write(signatures_dir / "alice.txt", "Approved signature\nAlice Sales\n")

    created = create_sender_campaigns_from_template_dir(
        template_dir=template_dir,
        output_dir=tmp_path / "campaigns",
    )

    prepared = prepare_campaign(created[0].scaffold.directory)
    assert prepared.messages[0].body.endswith("Approved signature\nAlice Sales")
    manifest = tmp_path / "campaigns" / "expo-thanks-manifest.csv"
    assert "copied_from_master" in manifest.read_text(encoding="utf-8-sig")
    write(template_dir / "body.txt", "Template updated\n{signature}\n")

    with pytest.raises(ValidationError, match="Template inputs changed"):
        prepare_campaign(created[0].scaffold.directory)
