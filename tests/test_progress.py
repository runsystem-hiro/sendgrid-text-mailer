from __future__ import annotations

from io import StringIO

from sendgrid_text_mailer.progress import ConsoleProgressReporter, DeliveryProgress


def test_interactive_progress_updates_one_line_and_keeps_checkpoints() -> None:
    stream = StringIO()
    reporter = ConsoleProgressReporter(
        send_interval_seconds=1.0,
        stream=stream,
        interactive=True,
    )

    reporter(DeliveryProgress(11, 1, 1, 0, 0.2, "progress"))
    reporter(DeliveryProgress(11, 10, 10, 0, 11.5, "progress"))

    output = stream.getvalue()
    assert output.startswith("\rSending: 1 / 11")
    assert "Sending: 10 / 11 | Sent: 10 | Failed: 0" in output
    assert output.endswith("\n")


def test_redirected_progress_only_writes_checkpoints_and_failures() -> None:
    stream = StringIO()
    reporter = ConsoleProgressReporter(
        send_interval_seconds=1.0,
        stream=stream,
        interactive=False,
    )

    reporter(DeliveryProgress(11, 1, 1, 0, 0.2, "progress"))
    reporter(DeliveryProgress(11, 2, 1, 1, 1.5, "failure"))
    reporter(DeliveryProgress(11, 10, 9, 1, 11.5, "progress"))

    output = stream.getvalue()
    assert "Sending: 1 / 11" not in output
    assert "Failure recorded. Sending: 2 / 11 | Sent: 1 | Failed: 1" in output
    assert "Sending: 10 / 11 | Sent: 9 | Failed: 1" in output


def test_interrupted_progress_never_includes_recipient_data() -> None:
    stream = StringIO()
    reporter = ConsoleProgressReporter(
        send_interval_seconds=1.0,
        stream=stream,
        interactive=False,
    )

    reporter(DeliveryProgress(150, 57, 56, 1, 65.0, "interrupted"))

    assert stream.getvalue() == "Interrupted: Sent: 56 | Failed: 1 | Not attempted: 93\n"
