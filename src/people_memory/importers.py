from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


@dataclass
class ContactRecord:
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    organization: str | None = None
    role: str | None = None
    city: str | None = None
    country: str | None = None
    linkedin_url: str | None = None
    connected_on: date | None = None
    source: str = "import"


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    email = value.strip().lower()
    return email if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) else None


def _first(row: dict[str, str], *names: str) -> str | None:
    lowered = {key.strip().lower(): (value or "").strip() for key, value in row.items() if key}
    for name in names:
        value = lowered.get(name.lower())
        if value:
            return value
    return None


def parse_linkedin_csv(path: Path) -> list[ContactRecord]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    start = next((i for i, line in enumerate(lines) if "First Name" in line), 0)
    records: list[ContactRecord] = []
    for row in csv.DictReader(lines[start:]):
        first = _first(row, "First Name") or ""
        last = _first(row, "Last Name") or ""
        full_name = f"{first} {last}".strip()
        if not full_name:
            continue
        connected = _first(row, "Connected On")
        connected_on = None
        if connected:
            for fmt in ("%d %b %Y", "%d %B %Y", "%m/%d/%Y", "%Y-%m-%d"):
                try:
                    connected_on = datetime.strptime(connected, fmt).date()
                    break
                except ValueError:
                    pass
        email = normalize_email(_first(row, "Email Address"))
        records.append(
            ContactRecord(
                full_name=full_name,
                first_name=first or None,
                last_name=last or None,
                emails=[email] if email else [],
                organization=_first(row, "Company"),
                role=_first(row, "Position"),
                linkedin_url=_first(row, "URL"),
                connected_on=connected_on,
                source="linkedin",
            )
        )
    return records


def parse_google_csv(path: Path) -> list[ContactRecord]:
    records: list[ContactRecord] = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            full_name = _first(row, "Name", "Full Name", "Given Name")
            first = _first(row, "Given Name", "First Name")
            last = _first(row, "Family Name", "Last Name")
            if not full_name:
                full_name = " ".join(value for value in (first, last) if value)
            if not full_name:
                continue
            emails = [
                email
                for key, raw in row.items()
                if key and "e-mail" in key.lower() and (email := normalize_email(raw))
            ]
            phones = [
                raw.strip()
                for key, raw in row.items()
                if key and "phone" in key.lower() and raw and raw.strip()
            ]
            records.append(
                ContactRecord(
                    full_name=full_name,
                    first_name=first,
                    last_name=last,
                    emails=list(dict.fromkeys(emails)),
                    phones=list(dict.fromkeys(phones)),
                    organization=_first(row, "Organization 1 - Name", "Organization"),
                    role=_first(row, "Organization 1 - Title", "Job Title"),
                    city=_first(row, "Address 1 - City", "City"),
                    country=_first(row, "Address 1 - Country", "Country"),
                    source="google",
                )
            )
    return records


WHATSAPP_LINE = re.compile(
    r"^\[?(?P<date>\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4})(?:,|\s)\s*"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)\]?\s*"
    r"(?:[-–]\s*)?(?P<name>[^:]+):\s?(?P<message>.*)$"
)


def _parse_whatsapp_date(raw: str, date_order: str | None) -> date:
    parts = [int(part) for part in re.split(r"[/.-]", raw)]
    if len(str(parts[0])) == 4:
        order = "ymd"
    elif date_order:
        order = date_order
    elif parts[0] > 12 >= parts[1]:
        order = "dmy"
    elif parts[1] > 12 >= parts[0]:
        order = "mdy"
    else:
        raise ValueError(
            f"Ambiguous WhatsApp date {raw!r}. Rerun with --date-order dmy or mdy."
        )
    positions = {letter: index for index, letter in enumerate(order)}
    year = parts[positions["y"]]
    if year < 100:
        year += 2000
    return date(year, parts[positions["m"]], parts[positions["d"]])


def parse_whatsapp_export(
    path: Path, self_name: str, date_order: str | None = None
) -> tuple[list[ContactRecord], dict[str, list[date]]]:
    names: dict[str, ContactRecord] = {}
    interactions: dict[str, list[date]] = {}
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        match = WHATSAPP_LINE.match(line)
        if not match:
            continue
        name = match.group("name").strip()
        if name.casefold() == self_name.strip().casefold():
            continue
        raw_date = match.group("date")
        parsed = _parse_whatsapp_date(raw_date, date_order)
        names.setdefault(name, ContactRecord(full_name=name, source="whatsapp"))
        interactions.setdefault(name, []).append(parsed)
    return list(names.values()), interactions


def contacts_from_rows(rows: Iterable[dict[str, str]], name_column: str) -> list[ContactRecord]:
    result = []
    for row in rows:
        name = (row.get(name_column) or "").strip()
        if name:
            result.append(ContactRecord(full_name=name, source="csv"))
    return result
