"""Console progress reporting for campaign delivery."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from typing import Any, Literal

ProgressEvent = Literal["progress", "failure", "complete", "interrupted"]


@dataclass(frozen=True, slots=True)
class DeliveryProgress:
    """A privacy-safe snapshot of delivery progress."""

    total: int
    completed: int
    sent: int
    failed: int
    elapsed_seconds: float
    event: ProgressEvent


class ConsoleProgressReporter:
    """Render delivery progress without writing recipient data to the console."""

    def __init__(
        self,
        *,
        send_interval_seconds: float,
        stream: Any | None = None,
        interactive: bool | None = None,
        checkpoint_interval: int = 10,
    ) -> None:
        self.send_interval_seconds = send_interval_seconds
        self.stream = stream or sys.stdout
        self.interactive = self.stream.isatty() if interactive is None else interactive
        self.checkpoint_interval = checkpoint_interval
        self._live_line = False

    def __call__(self, progress: DeliveryProgress) -> None:
        line = self._format_progress(progress)
        if progress.event == "interrupted":
            self._clear_live_line()
            self._write_line(
                "Interrupted: "
                f"Sent: {progress.sent} | Failed: {progress.failed} | "
                f"Not attempted: {progress.total - progress.completed}"
            )
            return

        if progress.event == "failure":
            self._clear_live_line()
            self._write_line(f"Failure recorded. {line}")
            return

        is_checkpoint = (
            progress.completed % self.checkpoint_interval == 0
            or progress.completed == progress.total
            or progress.event == "complete"
        )
        if self.interactive and not is_checkpoint:
            self.stream.write(f"\r{line}")
            self.stream.flush()
            self._live_line = True
        elif is_checkpoint:
            self._clear_live_line()
            self._write_line(line)

    def _format_progress(self, progress: DeliveryProgress) -> str:
        return (
            f"Sending: {progress.completed} / {progress.total} | "
            f"Sent: {progress.sent} | Failed: {progress.failed} | "
            f"ETA: {self._format_duration(self._estimate_remaining(progress))}"
        )

    def _estimate_remaining(self, progress: DeliveryProgress) -> float:
        remaining = progress.total - progress.completed
        if remaining <= 0:
            return 0.0

        completed_intervals = max(progress.completed - 1, 0)
        request_time = max(
            0.0,
            (progress.elapsed_seconds - completed_intervals * self.send_interval_seconds)
            / progress.completed,
        )
        return remaining * (request_time + self.send_interval_seconds)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        rounded = math.ceil(max(seconds, 0.0))
        minutes, remaining_seconds = divmod(rounded, 60)
        return f"{minutes}m {remaining_seconds}s" if minutes else f"{remaining_seconds}s"

    def _clear_live_line(self) -> None:
        if self._live_line:
            self.stream.write("\r" + " " * 120 + "\r")
            self.stream.flush()
            self._live_line = False

    def _write_line(self, line: str) -> None:
        self.stream.write(f"{line}\n")
        self.stream.flush()
