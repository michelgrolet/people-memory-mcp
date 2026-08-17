import os
from datetime import date

import pytest
from psycopg.errors import ReadOnlySqlTransaction

from people_memory.config import Settings
from people_memory.db import Database
from people_memory.repository import GraphRepository

pytestmark = pytest.mark.integration


def _repo() -> GraphRepository:
    url = os.environ.get("PEOPLE_MEMORY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PEOPLE_MEMORY_TEST_DATABASE_URL is not set")
    settings = Settings(
        database_url=url,
        api_token=None,
        enable_raw_sql=True,
        default_source="test",
        cors_origins=(),
    )
    return GraphRepository(Database(settings))


def test_people_memory_end_to_end() -> None:
    repo = _repo()
    with repo.db.connection() as conn:
        conn.execute(
            "truncate deleted_records, interactions, facts, edges, affiliations, identifiers, "
            "orgs, people restart identity cascade"
        )

    ada = repo.remember_person(
        full_name="Ada Lovelace",
        email="ada@example.com",
        current_org="Analytical Engine",
        current_role="Mathematician",
        linkedin_url="https://www.linkedin.com/in/ada-lovelace",
        city="London",
        confirmed_new=True,
        source="test",
    )
    grace = repo.remember_person(
        full_name="Grace Hopper",
        email="grace@example.com",
        current_org="US Navy",
        current_role="Computer scientist",
        confirmed_new=True,
        source="test",
    )
    assert ada["status"] == "created"
    assert grace["status"] == "created"

    extra = repo.add_identifier(ada["person"]["id"], "email", "ada.work@example.com", "test")
    assert extra["status"] == "created"
    assert repo.get_person(ada["person"]["id"])["linkedin_url"].endswith("ada-lovelace")
    collision = repo.remember_person(
        full_name="A Different Person",
        email="ada@example.com",
        confirmed_new=True,
        source="test",
    )
    assert collision["status"] == "needs_confirmation"

    edge = repo.connect_people(ada["person"]["id"], grace["person"]["id"], "knows", source="test")
    assert edge["kind"] == "knows"
    reverse = repo.connect_people(
        grace["person"]["id"], ada["person"]["id"], "knows", strength=3, source="test"
    )
    assert reverse["a_id"] == ada["person"]["id"]
    assert repo.status()["relationships"] == 1
    repo.add_fact(ada["person"]["id"], "favorite_language", "Python", source="test")
    repo.record_interaction(
        ada["person"]["id"], date(2026, 8, 3), "coffee", "Discussed compilers", "test"
    )

    found = repo.get_person(ada["person"]["id"])
    assert found["full_name"] == "Ada Lovelace"
    assert found["facts"][0]["value"] == "Python"
    assert found["interactions"][0]["channel"] == "coffee"
    assert repo.search_people("Analytical")[0]["full_name"] == "Ada Lovelace"
    assert repo.status()["people"] == 2

    with pytest.raises(ReadOnlySqlTransaction):
        repo.read_query(f"select delete_person({grace['person']['id']})")
    assert repo.get_person(grace["person"]["id"])

    paths = repo.find_intro_path("US Navy", "Ada Lovelace", 3)
    assert paths[0]["target_person"] == "Grace Hopper"

    assert repo.delete_person(ada["person"]["id"])
    assert repo.status()["people"] == 1
    archived = repo.read_query("select record_type, record_id from deleted_records")
    assert archived == [{"record_type": "person", "record_id": ada["person"]["id"]}]


def test_resolve_person_single_fuzzy_match_needs_confirmation() -> None:
    repo = _repo()
    with repo.db.connection() as conn:
        conn.execute(
            "truncate deleted_records, interactions, facts, edges, affiliations, identifiers, "
            "orgs, people restart identity cascade"
        )
    created = repo.remember_person(
        full_name="Wren Halloway", confirmed_new=True, source="test"
    )
    assert created["status"] == "created"

    # Exact name still resolves straight away.
    exact = repo.resolve_person("Wren Halloway")
    assert exact["status"] == "resolved"
    assert exact["person"]["full_name"] == "Wren Halloway"

    # A partial/fuzzy query matching exactly one row must NOT silently resolve:
    # it should ask for confirmation, even though there is only one candidate.
    fuzzy = repo.resolve_person("Wren")
    assert fuzzy["status"] == "needs_confirmation"
    assert [c["full_name"] for c in fuzzy["candidates"]] == ["Wren Halloway"]


def test_remember_person_resolves_similarity_from_extensions_schema() -> None:
    repo = _repo()
    with repo.db.connection() as conn:
        conn.execute(
            "truncate deleted_records, interactions, facts, edges, affiliations, identifiers, "
            "orgs, people restart identity cascade"
        )
    try:
        created = repo.remember_person(
            full_name="Aster Vale", confirmed_new=True, source="test"
        )
        assert created["status"] == "created"

        similar = repo.remember_person(full_name="Aster Vail", source="test")
        assert similar["status"] == "needs_confirmation"
        assert [candidate["full_name"] for candidate in similar["candidates"]] == ["Aster Vale"]
    finally:
        with repo.db.connection() as conn:
            conn.execute(
                "truncate deleted_records, interactions, facts, edges, affiliations, identifiers, "
                "orgs, people restart identity cascade"
            )


def test_add_fact_exact_repeat_is_idempotent() -> None:
    repo = _repo()
    with repo.db.connection() as conn:
        conn.execute(
            "truncate deleted_records, interactions, facts, edges, affiliations, identifiers, "
            "orgs, people restart identity cascade"
        )
    person = repo.remember_person(full_name="Katherine Johnson", confirmed_new=True, source="test")
    person_id = person["person"]["id"]

    first = repo.add_fact(
        person_id, "linkedin_connected_on", "2024-05-12", source="linkedin", confidence="observed"
    )
    second = repo.add_fact(
        person_id, "linkedin_connected_on", "2024-05-12", source="linkedin", confidence="observed"
    )

    assert first["id"] == second["id"]
    rows = repo.read_query(
        f"select count(*) as n from facts where person_id = {person_id} "
        "and key = 'linkedin_connected_on'"
    )
    assert rows[0]["n"] == 1


def test_add_fact_same_value_different_date_is_not_deduped() -> None:
    repo = _repo()
    with repo.db.connection() as conn:
        conn.execute(
            "truncate deleted_records, interactions, facts, edges, affiliations, identifiers, "
            "orgs, people restart identity cascade"
        )
    person = repo.remember_person(full_name="Dorothy Vaughan", confirmed_new=True, source="test")
    person_id = person["person"]["id"]

    first = repo.add_fact(
        person_id, "weight_kg", "70", fact_date=date(2026, 1, 1), source="test"
    )
    second = repo.add_fact(
        person_id, "weight_kg", "70", fact_date=date(2026, 2, 1), source="test"
    )

    assert first["id"] != second["id"]
    rows = repo.read_query(
        f"select count(*) as n from facts where person_id = {person_id} and key = 'weight_kg'"
    )
    assert rows[0]["n"] == 2

    # Re-adding the exact same (value, date) pair a second time is still a no-op.
    repeat = repo.add_fact(
        person_id, "weight_kg", "70", fact_date=date(2026, 2, 1), source="test"
    )
    assert repeat["id"] == second["id"]
    rows = repo.read_query(
        f"select count(*) as n from facts where person_id = {person_id} and key = 'weight_kg'"
    )
    assert rows[0]["n"] == 2


def test_identifier_case_does_not_create_a_second_unresolvable_person() -> None:
    """The bug this guards: storage was case-sensitive while lookup was not.

    Writing lowercased `email` and nothing else, so `linkedin.com/in/x` and `LinkedIn.com/in/X`
    were two rows the `(kind, value)` primary key could not see as one. That is worse than a
    duplicate: the next lookup lowercases, matches both, and the person becomes two candidates
    that no tool in the product can collapse again.
    """
    repo = _repo()
    with repo.db.connection() as conn:
        conn.execute(
            "truncate deleted_records, interactions, facts, edges, affiliations, identifiers, "
            "orgs, people restart identity cascade"
        )

    created = repo.remember_person(
        full_name="Wren Halloway",
        email="Wren.Halloway@Example.com",
        linkedin_url="https://www.LinkedIn.com/in/Wren-Halloway",
        confirmed_new=True,
        source="test",
    )
    assert created["status"] == "created"

    with repo.db.connection() as conn:
        stored = [
            row["value"]
            for row in conn.execute("select value from identifiers order by value").fetchall()
        ]
    assert stored == [value.lower() for value in stored], stored

    # Same person, typed in every other casing: still one person, never a second row.
    for email, linkedin in (
        ("wren.halloway@example.com", "https://www.linkedin.com/in/wren-halloway"),
        ("WREN.HALLOWAY@EXAMPLE.COM", "https://www.LINKEDIN.com/in/WREN-HALLOWAY"),
    ):
        again = repo.remember_person(
            full_name="Wren Halloway", email=email, linkedin_url=linkedin, source="test"
        )
        assert again["status"] == "updated", again
        assert again["person"]["id"] == created["person"]["id"]

    added = repo.add_identifier(created["person"]["id"], "github", "WrenH", "test")
    assert added["status"] == "created"
    repeat = repo.add_identifier(created["person"]["id"], "github", "wrenh", "test")
    assert repeat["status"] != "created", repeat

    with repo.db.connection() as conn:
        assert conn.execute("select count(*) as n from people").fetchone()["n"] == 1
        assert conn.execute("select count(*) as n from identifiers").fetchone()["n"] == 3
