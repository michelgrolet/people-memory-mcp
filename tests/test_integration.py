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
        full_name="Michel Grolet", confirmed_new=True, source="test"
    )
    assert created["status"] == "created"

    # Exact name still resolves straight away.
    exact = repo.resolve_person("Michel Grolet")
    assert exact["status"] == "resolved"
    assert exact["person"]["full_name"] == "Michel Grolet"

    # A partial/fuzzy query matching exactly one row must NOT silently resolve:
    # it should ask for confirmation, even though there is only one candidate.
    fuzzy = repo.resolve_person("Michel")
    assert fuzzy["status"] == "needs_confirmation"
    assert [c["full_name"] for c in fuzzy["candidates"]] == ["Michel Grolet"]
