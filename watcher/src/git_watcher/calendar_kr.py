"""한국 근무일 달력: 주말·공휴일(대체공휴일 포함)을 뺀 날."""

from calendar import monthrange
from datetime import date, timedelta

import holidays

SATURDAY = 5


def holiday_name(day: date) -> str | None:
    return holidays.KR(years=day.year).get(day)


def day_kind(day: date) -> str:
    """'근무일' / '주말' / 공휴일 이름."""
    name = holiday_name(day)
    if name:
        return name
    return "주말" if day.weekday() >= SATURDAY else "근무일"


def is_workday(day: date) -> bool:
    return day_kind(day) == "근무일"


def month_days(year: int, month: int) -> list[date]:
    first = date(year, month, 1)
    return [first + timedelta(days=i) for i in range(monthrange(year, month)[1])]


def first_workday(year: int, month: int) -> date:
    return next(d for d in month_days(year, month) if is_workday(d))


def previous_month(day: date) -> tuple[int, int]:
    last = day.replace(day=1) - timedelta(days=1)
    return last.year, last.month
