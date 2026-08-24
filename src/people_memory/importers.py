from __future__ import annotations

import csv
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

LINKEDIN_SNAPSHOT_URL = "https://api.linkedin.com/rest/memberSnapshotData"
LINKEDIN_API_VERSION = "202312"


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
    birthdate: date | None = None
    birthday_md: str | None = None
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


def _connection_record_from_row(row: dict[str, str]) -> ContactRecord | None:
    """Shared by the CSV export and the live API — both use the same column names
    (First Name, Last Name, Company, Position, Connected On, URL, Email Address)."""
    first = _first(row, "First Name") or ""
    last = _first(row, "Last Name") or ""
    full_name = f"{first} {last}".strip()
    if not full_name:
        return None
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
    return ContactRecord(
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


def parse_linkedin_csv(path: Path) -> list[ContactRecord]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    start = next((i for i, line in enumerate(lines) if "First Name" in line), 0)
    records: list[ContactRecord] = []
    for row in csv.DictReader(lines[start:]):
        record = _connection_record_from_row(row)
        if record is not None:
            records.append(record)
    return records


def fetch_linkedin_connections(access_token: str, *, timeout: float = 30.0) -> list[ContactRecord]:
    """Fetch 1st-degree connections live via LinkedIn's Member Data Portability API
    (Member Snapshot API, domain=CONNECTIONS). Requires an OAuth token with the
    r_dma_portability_self_serve (or r_dma_portability_3rd_party) scope — see
    https://learn.microsoft.com/en-us/linkedin/dma/member-data-portability/.

    The Snapshot API paginates via `start`/`count`, advertised as a `rel=next` entry
    in the response's `paging.links` — this follows that chain until exhausted,
    aggregating every page's elements.

    Raises RuntimeError (with LinkedIn's own message) if the domain isn't collated
    yet — common right after a member first consents, LinkedIn processes it async.
    That case is indistinguishable, by message text alone, from LinkedIn's own documented
    end-of-pagination signal (a 404 is the expected way this endpoint says "no more pages" —
    see the Member Snapshot API pagination guidance): both come back as a 404 whose body says
    "No data found for this domain and memberId." So a 404 is only fatal on the very FIRST
    request (nothing collected yet); once at least one page has come back with real data, the
    same 404 just means pagination is exhausted, not that the domain vanished.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Linkedin-Version": LINKEDIN_API_VERSION,
        "Content-Type": "application/json",
    }
    url: str | None = f"{LINKEDIN_SNAPSHOT_URL}?q=criteria&domain=CONNECTIONS"
    records: list[ContactRecord] = []
    while url:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and records:
                # End of pagination, not a real error — see the docstring above.
                break
            raw_body = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw_body)
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"LinkedIn API error {exc.code}: non-JSON response ({raw_body[:200]!r})"
                ) from exc
            raise RuntimeError(
                f"LinkedIn API error {exc.code}: {body.get('message', body)}"
            ) from exc

        for element in payload.get("elements", []):
            for row in element.get("snapshotData", []):
                record = _connection_record_from_row(row)
                if record is not None:
                    records.append(record)

        url = None
        for link in payload.get("paging", {}).get("links", []):
            if link.get("rel") == "next" and link.get("href"):
                url = urllib.parse.urljoin(LINKEDIN_SNAPSHOT_URL, link["href"])
                break

    return records


def parse_birthday(raw: str | None) -> tuple[date | None, str | None]:
    """Split a contact-export birthday into a full date and a month-day.

    Google writes a year-less birthday as `--05-14`, which is most of them: people fill in the day
    they celebrate and leave the year out. Dropping those loses the only field the whole reason to
    have birthdays depends on, so keep them as `MM-DD` in `birthday_md` instead of forcing a fake
    year. Returns `(birthdate, birthday_md)`, at most one of which is set.
    """
    if not raw:
        return None, None
    value = raw.strip()
    if not value:
        return None, None
    match = re.fullmatch(r"-{2}(\d{2})-(\d{2})", value)
    if match:
        return None, f"{match.group(1)}-{match.group(2)}"
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value, pattern).date(), None
        except ValueError:
            continue
    match = re.fullmatch(r"(\d{2})-(\d{2})", value)
    if match:
        return None, value
    return None, None


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
            birthdate, birthday_md = parse_birthday(
                _first(row, "Birthday", "Event 1 - Value")
            )
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
                    birthdate=birthdate,
                    birthday_md=birthday_md,
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
