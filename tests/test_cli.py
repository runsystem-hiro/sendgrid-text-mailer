from sendgrid_text_mailer import __version__


def test_version() -> None:
    assert __version__ == "0.1.0"


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
        ]
    )

    assert args.command == "campaign"
    assert args.campaign_command == "create"
    assert args.campaign_id == "sample-1"
    assert args.unsubscribe_url is None
