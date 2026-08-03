from pathlib import Path

import pytest

from people_memory.importers import (
    normalize_email,
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
