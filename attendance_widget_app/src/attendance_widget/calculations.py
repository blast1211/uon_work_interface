from __future__ import annotations

from datetime import date, datetime, timedelta

from attendance_widget.models import DailyAttendance, WeeklySummary


OFF_DAY_LABELS = {"\uD734\uC77C", "\uC720\uAE09\uD734\uBB34", "\uC2DC\uAC04\uC678\uC778\uC815"}
HALF_DAY_LABELS = {"\uC624\uC804\uBC18\uCC28", "\uC624\uD6C4\uBC18\uCC28"}


def parse_hhmm(value: str) -> int:
    cleaned = (value or "").strip()
    if len(cleaned) < 4:
        raise ValueError(f"Invalid HHMM value: {value!r}")
    return int(cleaned[:2]) * 60 + int(cleaned[2:4])


def worked_minutes(come_time: str, leave_time: str) -> int:
    return parse_hhmm(leave_time) - parse_hhmm(come_time)


def target_minutes_for_label(label: str, weekday_target: int, halfday_target: int) -> int:
    if label in OFF_DAY_LABELS:
        return 0
    if label in HALF_DAY_LABELS:
        return halfday_target
    return weekday_target


def normalize_times(attendance: DailyAttendance, default_start: str, default_end: str) -> tuple[str, str]:
    come_time = attendance.come_time or default_start
    leave_time = attendance.leave_time or default_end
    return come_time, leave_time


def week_date_strings(target_day: date) -> list[str]:
    monday = target_day - timedelta(days=target_day.weekday())
    return [
        (monday + timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range(5)
    ]


def build_weekly_summary(
    today: DailyAttendance | None,
    week_rows: list[DailyAttendance],
    target_day: date,
    weekday_target: int,
    halfday_target: int,
    default_start: str,
    default_end: str,
) -> WeeklySummary:
    valid_dates = set(week_date_strings(target_day))
    today_date = target_day.strftime("%Y%m%d")

    rows_by_date = {
        row.date: row
        for row in week_rows
        if row.date in valid_dates and row.date != today_date
    }
    if today and today.date == today_date:
        rows_by_date[today_date] = today

    total_worked_minutes = 0
    total_expected_minutes = 0
    today_minutes = 0
    now_hhmm = datetime.now().strftime("%H%M")

    for day_key in sorted(valid_dates):
        row = rows_by_date.get(day_key)
        if row is None:
            continue

        expected = target_minutes_for_label(row.label, weekday_target, halfday_target)

        if day_key == today_date and row.come_time and not row.leave_time:
            worked = max(0, worked_minutes(row.come_time, now_hhmm))
        else:
            come_time, leave_time = normalize_times(row, default_start, default_end)
            worked = worked_minutes(come_time, leave_time)

        total_worked_minutes += worked
        total_expected_minutes += expected

        if day_key == today_date:
            today_minutes = worked

    return WeeklySummary(
        week_minutes=total_worked_minutes,
        today_minutes=today_minutes,
        balance_minutes=total_worked_minutes - total_expected_minutes,
        expected_minutes=total_expected_minutes,
    )
