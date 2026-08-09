"""Dates a person only half remembers.

Most real facts about people carry an incomplete date. Someone joined a company "in 2015", a
relationship ended "in 2023", a school year was "2019-2020". A `date` column cannot hold any of
that: storing it means inventing a month and a day, and inventing data to satisfy a column type is
worse than admitting the day is unknown.

So `facts.date`, `affiliations.since`/`until` and `edges.since`/`until` are ISO-8601 prefixes stored
as text: `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`. The prefix property is what makes this work rather than
being a cop-out — ISO prefixes sort and compare correctly as plain strings, so `order by since`,
`where until >= '2024'` and the `until >= since` check constraints all behave. What you give up is
arithmetic: subtracting two of them needs an explicit cast, and it can only be as precise as the
coarser operand.

A range like `2019-2020` is not a date and does not belong here; it belongs in a text `value`
alongside the fact it describes.
"""

from __future__ import annotations

import re
from datetime import date, datetime

# Kept identical to the `partial_date` domain's constraint in the migrations. Postgres and Python
# must agree on what is storable, or one of them rejects what the other just accepted.
PARTIAL_DATE_PATTERN = r"^\d{4}(-\d{2}(-\d{2})?)?$"
_PARTIAL_DATE_RE = re.compile(PARTIAL_DATE_PATTERN)


def normalize_partial_date(value: date | str | None) -> str | None:
    """Return an ISO-8601 prefix, or raise ValueError explaining what is wrong with the input.

    Accepts a `date`/`datetime` (rendered in full), or a string already shaped as `YYYY`,
    `YYYY-MM`, or `YYYY-MM-DD`. Rejects everything else rather than guessing: a caller passing
    `01 Apr 2022` or `2019-2020` has a parsing problem, and silently storing NULL would hide it.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return None
    if not _PARTIAL_DATE_RE.match(text):
        raise ValueError(
            f"{text!r} is not a date. Use YYYY, YYYY-MM, or YYYY-MM-DD, "
            "and put anything else (a range, a season, 'ongoing') in a text field."
        )

    # Shaped right but still not a real date: month 13, or the 30th of February.
    parts = [int(part) for part in text.split("-")]
    probe = [parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1]
    try:
        date(*probe)
    except ValueError as exc:
        raise ValueError(f"{text!r} is not a real date: {exc}") from exc
    return text
