from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DailyAttendance:
    date: str
    label: str
    come_time: str
    leave_time: str


@dataclass(slots=True)
class WeeklySummary:
    week_minutes: int
    today_minutes: int
    balance_minutes: int
    expected_minutes: int

    @property
    def balance_text(self) -> str:
        sign = "+" if self.balance_minutes > 0 else ""
        hours, minutes = divmod(abs(self.balance_minutes), 60)
        prefix = sign if self.balance_minutes >= 0 else "-"
        return f"{prefix}{hours}:{minutes:02d}"
