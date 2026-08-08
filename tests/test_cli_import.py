"""The import apply loop, with the database stubbed out.

These cover the wiring between a parsed record and the repository calls it should produce, which
is where a field gets silently dropped: the parser reads it, the repository can store it, and
nobody passes it across.
"""

from datetime import date

from people_memory.cli import _apply_import
from people_memory.importers import ContactRecord


class StubRepository:
    """Records the calls a real GraphRepository would have turned into writes."""

    def __init__(self) -> None:
        self.people: list[dict] = []
        self.facts: list[dict] = []
        self.interactions: list[tuple] = []

    def remember_person(self, **kwargs) -> dict:
        self.people.append(kwargs)
        return {"status": "created", "person": {"id": len(self.people)}}

    def add_identifier(self, *args) -> dict:
        return {"status": "added"}

    def add_fact(self, person_id, key, value, **kwargs) -> dict:
        self.facts.append({"person_id": person_id, "key": key, "value": value, **kwargs})
        return {"status": "added"}

    def record_interaction(self, *args) -> dict:
        self.interactions.append(args)
        return {"status": "added"}


def test_linkedin_connection_date_lands_in_both_value_and_date() -> None:
    """A date stored only as text cannot be filtered or sorted without parsing it back."""
    repo = StubRepository()
    record = ContactRecord(
        full_name="Ada Lovelace",
        source="linkedin",
        connected_on=date(2022, 4, 1),
    )

    _apply_import(repo, [record], {}, accept_similar_as_new=False)

    (fact,) = repo.facts
    assert fact["key"] == "linkedin_connected_on"
    assert fact["value"] == "2022-04-01"
    assert fact["fact_date"] == date(2022, 4, 1)


def test_birthdays_reach_remember_person() -> None:
    repo = StubRepository()
    records = [
        ContactRecord(full_name="Grace Hopper", source="google", birthdate=date(1906, 12, 9)),
        ContactRecord(full_name="Ada Lovelace", source="google", birthday_md="12-10"),
    ]

    _apply_import(repo, records, {}, accept_similar_as_new=False)

    grace, ada = repo.people
    assert grace["birthdate"] == date(1906, 12, 9)
    assert grace["birthday_md"] is None
    assert ada["birthdate"] is None
    assert ada["birthday_md"] == "12-10"


def test_whatsapp_latest_message_becomes_an_interaction() -> None:
    repo = StubRepository()
    record = ContactRecord(full_name="Alan Turing", source="whatsapp")
    interactions = {"Alan Turing": [date(2026, 8, 3), date(2026, 8, 4)]}

    result = _apply_import(repo, [record], interactions, accept_similar_as_new=False)

    assert result["counts"]["created"] == 1
    (call,) = repo.interactions
    assert call[1] == date(2026, 8, 4)
