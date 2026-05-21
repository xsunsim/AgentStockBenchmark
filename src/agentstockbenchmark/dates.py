from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterator


COMPACT_DATE_RE = re.compile(r"^\d{8}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(value: str | dt.date | dt.datetime) -> dt.date:
    """Parse CLI date input.

    YYYYMMDD is the canonical persisted format. YYYY-MM-DD is accepted at the
    boundary for operator convenience only.
    """
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value

    text = str(value).strip()
    if text == "today":
        return dt.date.today()
    if COMPACT_DATE_RE.fullmatch(text):
        return dt.datetime.strptime(text, "%Y%m%d").date()
    if ISO_DATE_RE.fullmatch(text):
        return dt.date.fromisoformat(text)
    raise ValueError(f"date must be YYYYMMDD or YYYY-MM-DD, got {value!r}")


def date_id(value: str | dt.date | dt.datetime) -> str:
    return parse_date(value).strftime("%Y%m%d")


def parse_date_id(value: str) -> dt.date:
    if not COMPACT_DATE_RE.fullmatch(value):
        raise ValueError(f"expected canonical date id YYYYMMDD, got {value!r}")
    return parse_date(value)


def iter_dates(start: dt.date, end: dt.date) -> Iterator[dt.date]:
    if end < start:
        raise ValueError(f"end date {date_id(end)} is before start date {date_id(start)}")

    current = start
    one_day = dt.timedelta(days=1)
    while current <= end:
        yield current
        current += one_day
