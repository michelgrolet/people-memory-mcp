import io
import json
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from people_memory.importers import (
    fetch_linkedin_connections,
    normalize_email,
    parse_birthday,
    parse_google_csv,
    parse_linkedin_csv,
    parse_whatsapp_export,
)


def test_normalize_email() -> None:
    assert normalize_email(" Ada@Example.COM ") == "ada@example.com"
    assert normalize_email("not-an-email") is None


def test_parse_linkedin_export(tmp_path: Path) -> None:
    export = tmp_path / "Connections.csv"
    export.write_text(
        "Notes:\nFirst Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        "Ada,Lovelace,https://linkedin.com/in/ada,ADA@example.com,Analytical Engine,"
        "Mathematician,03 Aug 2026\n",
        encoding="utf-8",
    )
    records = parse_linkedin_csv(export)
    assert len(records) == 1
    assert records[0].full_name == "Ada Lovelace"
    assert records[0].emails == ["ada@example.com"]
    assert records[0].organization == "Analytical Engine"
    assert records[0].connected_on.isoformat() == "2026-08-03"


def test_parse_google_export(tmp_path: Path) -> None:
    export = tmp_path / "contacts.csv"
    export.write_text(
        "Name,Given Name,Family Name,E-mail 1 - Value,Phone 1 - Value,Organization 1 - Name\n"
        "Grace Hopper,Grace,Hopper,grace@example.com,+12025550123,US Navy\n",
        encoding="utf-8",
    )
    records = parse_google_csv(export)
    assert records[0].full_name == "Grace Hopper"
    assert records[0].phones == ["+12025550123"]
    assert records[0].source == "google"


def test_parse_google_export_reads_birthdays(tmp_path: Path) -> None:
    """Google writes most birthdays without a year, as `--MM-DD`. Both shapes must survive."""
    export = tmp_path / "contacts.csv"
    export.write_text(
        "Name,E-mail 1 - Value,Birthday\n"
        "Grace Hopper,grace@example.com,1906-12-09\n"
        "Ada Lovelace,ada@example.com,--12-10\n"
        "Alan Turing,alan@example.com,\n",
        encoding="utf-8",
    )
    grace, ada, alan = parse_google_csv(export)
    assert grace.birthdate.isoformat() == "1906-12-09"
    assert grace.birthday_md is None
    assert ada.birthdate is None
    assert ada.birthday_md == "12-10"
    assert alan.birthdate is None and alan.birthday_md is None


def test_parse_birthday_shapes() -> None:
    assert parse_birthday("1906-12-09") == (date(1906, 12, 9), None)
    assert parse_birthday("12/09/1906") == (date(1906, 12, 9), None)
    assert parse_birthday("--12-10") == (None, "12-10")
    assert parse_birthday("12-10") == (None, "12-10")
    # Nothing usable rather than a guess: a lone year would have to invent a day and a month.
    assert parse_birthday("1906") == (None, None)
    assert parse_birthday("  ") == (None, None)
    assert parse_birthday(None) == (None, None)


def test_parse_whatsapp_export(tmp_path: Path) -> None:
    export = tmp_path / "chat.txt"
    export.write_text(
        "03/08/2026, 10:00 - Me: Hello\n"
        "03/08/2026, 10:01 - Alan Turing: Hi\n"
        "04/08/2026, 12:30 - Alan Turing: Lunch?\n",
        encoding="utf-8",
    )
    records, interactions = parse_whatsapp_export(export, "Me", "dmy")
    assert [record.full_name for record in records] == ["Alan Turing"]
    assert len(interactions["Alan Turing"]) == 2


def test_parse_whatsapp_ios_and_twelve_hour_time(tmp_path: Path) -> None:
    export = tmp_path / "chat.txt"
    export.write_text(
        "[8/13/26, 9:14:03 PM] Me: Hello\n"
        "[8/13/26, 9:15:07 PM] Katherine Johnson: Hi\n",
        encoding="utf-8",
    )
    records, interactions = parse_whatsapp_export(export, "Me")
    assert [record.full_name for record in records] == ["Katherine Johnson"]
    assert interactions["Katherine Johnson"][0].isoformat() == "2026-08-13"


def test_ambiguous_whatsapp_date_requires_user_choice(tmp_path: Path) -> None:
    export = tmp_path / "chat.txt"
    export.write_text("03/08/2026, 10:01 - Alan Turing: Hi\n", encoding="utf-8")
    with pytest.raises(ValueError, match="--date-order"):
        parse_whatsapp_export(export, "Me")


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _snapshot_page(rows: list[dict], next_href: str | None = None) -> dict:
    page = {"elements": [{"snapshotDomain": "CONNECTIONS", "snapshotData": rows}]}
    if next_href:
        page["paging"] = {"links": [{"rel": "next", "href": next_href}]}
    return page


def test_fetch_linkedin_connections_maps_same_fields_as_csv() -> None:
    payload = {
        "elements": [
            {
                "snapshotDomain": "CONNECTIONS",
                "snapshotData": [
                    {
                        "First Name": "Ada",
                        "Last Name": "Lovelace",
                        "URL": "https://linkedin.com/in/ada",
                        "Email Address": "ADA@example.com",
                        "Company": "Analytical Engine",
                        "Position": "Mathematician",
                        "Connected On": "03 Aug 2026",
                    }
                ],
            }
        ]
    }
    with patch(
        "people_memory.importers.urllib.request.urlopen",
        return_value=_FakeResponse(payload),
    ) as mock_urlopen:
        records = fetch_linkedin_connections("fake-token")
    assert len(records) == 1
    assert records[0].full_name == "Ada Lovelace"
    assert records[0].emails == ["ada@example.com"]
    assert records[0].organization == "Analytical Engine"
    assert records[0].connected_on.isoformat() == "2026-08-03"
    assert records[0].source == "linkedin"
    request = mock_urlopen.call_args[0][0]
    assert request.get_header("Authorization") == "Bearer fake-token"
    assert request.get_header("Linkedin-version") == "202312"
    assert "domain=CONNECTIONS" in request.full_url


def test_fetch_linkedin_connections_skips_rows_without_a_name() -> None:
    payload = {"elements": [{"snapshotData": [{"Company": "Ghost Corp"}]}]}
    with patch(
        "people_memory.importers.urllib.request.urlopen", return_value=_FakeResponse(payload)
    ):
        records = fetch_linkedin_connections("fake-token")
    assert records == []


def test_fetch_linkedin_connections_follows_pagination_links() -> None:
    page_one = _snapshot_page(
        [{"First Name": "Ada", "Last Name": "Lovelace"}],
        next_href="/rest/memberSnapshotData?q=criteria&domain=CONNECTIONS&start=1",
    )
    page_two = _snapshot_page([{"First Name": "Alan", "Last Name": "Turing"}])
    responses = [_FakeResponse(page_one), _FakeResponse(page_two)]
    with patch(
        "people_memory.importers.urllib.request.urlopen", side_effect=responses
    ) as mock_urlopen:
        records = fetch_linkedin_connections("fake-token")
    assert [record.full_name for record in records] == ["Ada Lovelace", "Alan Turing"]
    assert mock_urlopen.call_count == 2
    second_request = mock_urlopen.call_args_list[1][0][0]
    assert second_request.full_url == (
        "https://api.linkedin.com/rest/memberSnapshotData"
        "?q=criteria&domain=CONNECTIONS&start=1"
    )


def test_fetch_linkedin_connections_stops_when_no_next_link() -> None:
    payload = _snapshot_page([{"First Name": "Ada", "Last Name": "Lovelace"}])
    with patch(
        "people_memory.importers.urllib.request.urlopen",
        return_value=_FakeResponse(payload),
    ) as mock_urlopen:
        records = fetch_linkedin_connections("fake-token")
    assert len(records) == 1
    assert mock_urlopen.call_count == 1


def test_fetch_linkedin_connections_raises_readable_error_when_not_collated_yet() -> None:
    error_body = json.dumps({"message": "No data found for this domain and memberId."}).encode()
    http_error = urllib.error.HTTPError(
        url="https://api.linkedin.com/rest/memberSnapshotData",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=io.BytesIO(error_body),
    )
    with (
        patch("people_memory.importers.urllib.request.urlopen", side_effect=http_error),
        pytest.raises(RuntimeError, match="404.*No data found"),
    ):
        fetch_linkedin_connections("fake-token")


def test_fetch_linkedin_connections_raises_readable_error_on_non_json_body() -> None:
    http_error = urllib.error.HTTPError(
        url="https://api.linkedin.com/rest/memberSnapshotData",
        code=502,
        msg="Bad Gateway",
        hdrs=None,
        fp=io.BytesIO(b"<html><body>502 Bad Gateway</body></html>"),
    )
    with (
        patch("people_memory.importers.urllib.request.urlopen", side_effect=http_error),
        pytest.raises(RuntimeError, match="502.*non-JSON response"),
    ):
        fetch_linkedin_connections("fake-token")
